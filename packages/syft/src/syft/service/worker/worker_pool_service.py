# stdlib
from typing import List
from typing import Optional
from typing import Tuple
from typing import Union

# relative
from ...serde.serializable import serializable
from ...store.document_store import DocumentStore
from ...store.linked_obj import LinkedObject
from ...types.dicttuple import DictTuple
from ...types.uid import UID
from ..context import AuthedServiceContext
from ..response import SyftError
from ..service import AbstractService
from ..service import SERVICE_TO_TYPES
from ..service import TYPE_TO_SERVICE
from ..service import service_method
from ..user.user_roles import DATA_OWNER_ROLE_LEVEL
from ..user.user_roles import DATA_SCIENTIST_ROLE_LEVEL
from .utils import DEFAULT_WORKER_POOL_NAME
from .utils import run_containers
from .utils import run_workers_in_threads
from .worker_image import SyftWorkerImage
from .worker_image_stash import SyftWorkerImageStash
from .worker_pool import ContainerSpawnStatus
from .worker_pool import WorkerOrchestrationType
from .worker_pool import WorkerPool
from .worker_pool_stash import SyftWorkerPoolStash
from .worker_service import WorkerService
from .worker_stash import WorkerStash


@serializable()
class SyftWorkerPoolService(AbstractService):
    store: DocumentStore
    stash: SyftWorkerPoolStash

    def __init__(self, store: DocumentStore) -> None:
        self.store = store
        self.stash = SyftWorkerPoolStash(store=store)
        self.image_stash = SyftWorkerImageStash(store=store)

    @service_method(
        path="worker_pool.launch",
        name="launch",
        roles=DATA_OWNER_ROLE_LEVEL,
    )
    def launch(
        self,
        context: AuthedServiceContext,
        name: str,
        image_uid: Optional[UID],
        num_workers: int,
        reg_username: Optional[str] = None,
        reg_password: Optional[str] = None,
    ) -> Union[List[ContainerSpawnStatus], SyftError]:
        """Creates a pool of workers from the given SyftWorkerImage.

        - Retrieves the image for the given UID
        - Use docker to launch containers for given image
        - For each successful container instantiation create a SyftWorker object
        - Creates a SyftWorkerPool object

        Args:
            context (AuthedServiceContext): context passed to the service
            name (str): name of the pool
            image_id (UID): UID of the SyftWorkerImage against which the pool should be created
            num_workers (int): the number of SyftWorker that needs to be created in the pool
        """

        result = self.stash.get_by_name(context.credentials, pool_name=name)

        if result.is_err():
            return SyftError(message=f"{result.err()}")

        if result.ok() is not None:
            return SyftError(message=f"Worker Pool with name: {name} already exists !!")

        if image_uid is None:
            result = self.stash.get_by_name(
                context.credentials, pool_name=DEFAULT_WORKER_POOL_NAME
            )
            default_worker_pool = result.ok()
            image_uid = default_worker_pool.image_id

        result = self.image_stash.get_by_uid(
            credentials=context.credentials, uid=image_uid
        )
        if result.is_err():
            return SyftError(
                message=f"Failed to retrieve Worker Image with id: {image_uid}. Error: {result.err()}"
            )

        worker_image: SyftWorkerImage = result.ok()

        worker_service: WorkerService = context.node.get_service("WorkerService")
        worker_stash = worker_service.stash

        worker_list, container_statuses = _create_workers_in_pool(
            context=context,
            pool_name=name,
            existing_worker_cnt=0,
            worker_cnt=num_workers,
            worker_image=worker_image,
            worker_stash=worker_stash,
            reg_username=reg_username,
            reg_password=reg_password,
        )

        worker_pool = WorkerPool(
            name=name,
            max_count=num_workers,
            image_id=worker_image.id,
            worker_list=worker_list,
            syft_node_location=context.node.id,
            syft_client_verify_key=context.credentials,
        )
        result = self.stash.set(credentials=context.credentials, obj=worker_pool)

        if result.is_err():
            return SyftError(message=f"Failed to save Worker Pool: {result.err()}")

        return container_statuses

    @service_method(
        path="worker_pool.get_all",
        name="get_all",
        roles=DATA_SCIENTIST_ROLE_LEVEL,
    )
    def get_all(
        self, context: AuthedServiceContext
    ) -> Union[DictTuple[str, WorkerPool], SyftError]:
        # TODO: During get_all, we should dynamically make a call to docker to get the status of the containers
        # and update the status of the workers in the pool.
        result = self.stash.get_all(credentials=context.credentials)
        if result.is_err():
            return SyftError(message=f"{result.err()}")
        worker_pools: List[WorkerPool] = result.ok()

        res: List[Tuple] = []
        for pool in worker_pools:
            res.append((pool.name, pool))
        return DictTuple(res)

    @service_method(
        path="worker_pool.add_workers",
        name="add_workers",
        roles=DATA_OWNER_ROLE_LEVEL,
    )
    def add_workers(
        self,
        context: AuthedServiceContext,
        number: int,
        pool_id: Optional[UID] = None,
        pool_name: Optional[str] = None,
    ) -> Union[List[ContainerSpawnStatus], SyftError]:
        if pool_id:
            result = self.stash.get_by_uid(credentials=context.credentials, uid=pool_id)
        elif pool_name:
            result = self.stash.get_by_name(
                credentials=context.credentials,
                pool_name=pool_name,
            )

        if result.is_err():
            return SyftError(message=f"{result.err()}")

        worker_pool = result.ok()

        existing_worker_cnt = len(worker_pool.worker_list)

        result = self.image_stash.get_by_uid(
            credentials=context.credentials,
            uid=worker_pool.image_id,
        )

        if result.is_err():
            return SyftError(
                message=f"Failed to retrieve image for worker pool: {worker_pool.name}"
            )

        worker_image: SyftWorkerImage = result.ok()

        worker_service: WorkerService = context.node.get_service("WorkerService")
        worker_stash = worker_service.stash

        worker_list, container_statuses = _create_workers_in_pool(
            context=context,
            pool_name=worker_pool.name,
            existing_worker_cnt=existing_worker_cnt,
            worker_cnt=number,
            worker_image=worker_image,
            worker_stash=worker_stash,
        )

        worker_pool.worker_list += worker_list
        worker_pool.max_count = existing_worker_cnt + number

        update_result = self.stash.update(
            credentials=context.credentials, obj=worker_pool
        )
        if update_result.is_err():
            return SyftError(
                message=f"Failed update worker pool: {worker_pool.name} with err: {result.err()}"
            )

        return container_statuses

    @service_method(
        path="worker_pool.filter_by_image_id",
        name="filter_by_image_id",
        roles=DATA_SCIENTIST_ROLE_LEVEL,
    )
    def filter_by_image_id(
        self, context: AuthedServiceContext, image_uid: UID
    ) -> Union[List[WorkerPool], SyftError]:
        result = self.stash.get_by_image_uid(context.credentials, image_uid)

        if result.is_err():
            return SyftError(message=f"Failed to get worker pool for uid: {image_uid}")

        return result.ok()

    def _get_worker_pool(
        self,
        context: AuthedServiceContext,
        worker_pool_id: UID,
    ) -> Union[WorkerPool, SyftError]:
        result = self.stash.get_by_uid(
            credentials=context.credentials, uid=worker_pool_id
        )

        if result.is_err():
            return SyftError(message=f"{result.err()}")

        worker_pool = result.ok()

        return (
            SyftError(message=f"worker pool with id {worker_pool_id} does not exist")
            if worker_pool is None
            else worker_pool
        )


def _create_workers_in_pool(
    context: AuthedServiceContext,
    pool_name: str,
    existing_worker_cnt: int,
    worker_cnt: int,
    worker_image: SyftWorkerImage,
    worker_stash: WorkerStash,
    reg_username: Optional[str] = None,
    reg_password: Optional[str] = None,
) -> Tuple[List[LinkedObject], List[ContainerSpawnStatus]]:
    queue_port = context.node.queue_config.client_config.queue_port

    # Check if workers needs to be run in memory or as containers
    start_workers_in_memory = context.node.in_memory_workers

    if start_workers_in_memory:
        # Run in-memory workers in threads
        container_statuses: List[ContainerSpawnStatus] = run_workers_in_threads(
            node=context.node,
            pool_name=pool_name,
            start_idx=existing_worker_cnt,
            number=worker_cnt + existing_worker_cnt,
        )
    else:
        container_statuses: List[ContainerSpawnStatus] = run_containers(
            pool_name=pool_name,
            worker_image=worker_image,
            start_idx=existing_worker_cnt,
            number=worker_cnt + existing_worker_cnt,
            orchestration=WorkerOrchestrationType.DOCKER,
            queue_port=queue_port,
            dev_mode=context.node.dev_mode,
            username=reg_username,
            password=reg_password,
            registry_url=worker_image.image_identifier.registry_host,
        )

    linked_worker_list = []

    for container_status in container_statuses:
        worker = container_status.worker
        if worker is None:
            continue
        result = worker_stash.set(
            credentials=context.credentials,
            obj=worker,
        )

        if result.is_ok():
            worker_obj = LinkedObject.from_obj(
                obj=result.ok(),
                service_type=WorkerService,
                node_uid=context.node.id,
            )
            linked_worker_list.append(worker_obj)
        else:
            container_status.error = result.err()

    return linked_worker_list, container_statuses


TYPE_TO_SERVICE[WorkerPool] = SyftWorkerPoolService
SERVICE_TO_TYPES[SyftWorkerPoolService] = WorkerPool