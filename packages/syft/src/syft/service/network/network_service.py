# stdlib
from collections.abc import Callable
import secrets
from typing import Any
from typing import cast

# third party
from result import Err
from result import Result

# relative
from ...abstract_node import AbstractNode
from ...abstract_node import NodeType
from ...client.client import HTTPConnection
from ...client.client import PythonConnection
from ...client.client import SyftClient
from ...client.client import VeilidConnection
from ...node.credentials import SyftVerifyKey
from ...node.worker_settings import WorkerSettings
from ...serde.serializable import serializable
from ...service.settings.settings import NodeSettingsV2
from ...store.document_store import BaseUIDStoreStash
from ...store.document_store import DocumentStore
from ...store.document_store import PartitionKey
from ...store.document_store import PartitionSettings
from ...store.document_store import QueryKeys
from ...types.grid_url import GridURL
from ...types.transforms import TransformContext
from ...types.transforms import keep
from ...types.transforms import transform
from ...types.transforms import transform_method
from ...types.uid import UID
from ...util.telemetry import instrument
from ..context import AuthedServiceContext
from ..data_subject.data_subject import NamePartitionKey
from ..metadata.node_metadata import NodeMetadataV3
from ..response import SyftError
from ..response import SyftSuccess
from ..service import AbstractService
from ..service import SERVICE_TO_TYPES
from ..service import TYPE_TO_SERVICE
from ..service import service_method
from ..user.user_roles import DATA_OWNER_ROLE_LEVEL
from ..user.user_roles import GUEST_ROLE_LEVEL
from ..warnings import CRUDWarning
from .node_peer import NodePeer
from .routes import HTTPNodeRoute
from .routes import NodeRoute
from .routes import PythonNodeRoute
from .routes import VeilidNodeRoute

VerifyKeyPartitionKey = PartitionKey(key="verify_key", type_=SyftVerifyKey)
NodeTypePartitionKey = PartitionKey(key="node_type", type_=NodeType)
OrderByNamePartitionKey = PartitionKey(key="name", type_=str)


@instrument
@serializable()
class NetworkStash(BaseUIDStoreStash):
    object_type = NodePeer
    settings: PartitionSettings = PartitionSettings(
        name=NodePeer.__canonical_name__, object_type=NodePeer
    )

    def __init__(self, store: DocumentStore) -> None:
        super().__init__(store=store)

    def get_by_name(
        self, credentials: SyftVerifyKey, name: str
    ) -> Result[NodePeer | None, str]:
        qks = QueryKeys(qks=[NamePartitionKey.with_obj(name)])
        return self.query_one(credentials=credentials, qks=qks)

    def update(
        self,
        credentials: SyftVerifyKey,
        peer: NodePeer,
        has_permission: bool = False,
    ) -> Result[NodePeer, str]:
        valid = self.check_type(peer, NodePeer)
        if valid.is_err():
            return Err(message=valid.err())
        return super().update(credentials, peer)

    def update_peer(
        self, credentials: SyftVerifyKey, peer: NodePeer
    ) -> Result[NodePeer, str]:
        """
        Update the selected peer and its route priorities if the peer already exists
        If the peer does not exist, simply adds it to the database.

        Args:
            credentials (SyftVerifyKey): The credentials used to authenticate the request.
            peer (NodePeer): The peer to be updated or added.

        Returns:
            Result[NodePeer, str]: The updated or added peer if the operation
            was successful, or an error message if the operation failed.
        """
        valid = self.check_type(peer, NodePeer)
        if valid.is_err():
            return SyftError(message=valid.err())
        existing: Result | NodePeer = self.get_by_uid(
            credentials=credentials, uid=peer.id
        )
        if existing.is_ok() and existing.ok():
            existing = existing.ok()
            existing.update_routes(peer.node_routes)
            result = self.update(credentials, existing)
            return result
        else:
            result = self.set(credentials, peer)
            return result

    def get_for_verify_key(
        self, credentials: SyftVerifyKey, verify_key: SyftVerifyKey
    ) -> Result[NodePeer, SyftError]:
        qks = QueryKeys(qks=[VerifyKeyPartitionKey.with_obj(verify_key)])
        return self.query_one(credentials, qks)

    def get_by_node_type(
        self, credentials: SyftVerifyKey, node_type: NodeType
    ) -> Result[list[NodePeer], SyftError]:
        qks = QueryKeys(qks=[NodeTypePartitionKey.with_obj(node_type)])
        return self.query_all(
            credentials=credentials, qks=qks, order_by=OrderByNamePartitionKey
        )


@instrument
@serializable()
class NetworkService(AbstractService):
    store: DocumentStore
    stash: NetworkStash

    def __init__(self, store: DocumentStore) -> None:
        self.store = store
        self.stash = NetworkStash(store=store)

    # TODO: Check with MADHAVA, can we even allow guest user to introduce routes to
    # domain nodes?
    @service_method(
        path="network.exchange_credentials_with",
        name="exchange_credentials_with",
        roles=GUEST_ROLE_LEVEL,
        warning=CRUDWarning(confirmation=True),
    )
    def exchange_credentials_with(
        self,
        context: AuthedServiceContext,
        self_node_route: NodeRoute,
        remote_node_route: NodeRoute,
        remote_node_verify_key: SyftVerifyKey,
    ) -> SyftSuccess | SyftError:
        """Exchange Route With Another Node"""

        # Step 1: Validate the Route
        self_node_peer = self_node_route.validate_with_context(context=context)

        if isinstance(self_node_peer, SyftError):
            return self_node_peer

        # Step 2: Send the Node Peer to the remote node
        # Also give them their own to validate that it belongs to them
        # random challenge prevents replay attacks
        remote_client: SyftClient = remote_node_route.client_with_context(
            context=context
        )
        random_challenge = secrets.token_bytes(16)

        remote_res = remote_client.api.services.network.add_peer(
            peer=self_node_peer,
            challenge=random_challenge,
            self_node_route=remote_node_route,
            verify_key=remote_node_verify_key,
        )

        if isinstance(remote_res, SyftError):
            return remote_res

        challenge_signature, remote_node_peer = remote_res

        # Verifying if the challenge is valid
        try:
            remote_node_verify_key.verify_key.verify(
                random_challenge, challenge_signature
            )
        except Exception as e:
            return SyftError(message=str(e))

        # save the remote peer for later
        context.node = cast(AbstractNode, context.node)
        result = self.stash.update_peer(
            context.node.verify_key,
            remote_node_peer,
        )
        if result.is_err():
            return SyftError(message=str(result.err()))

        return SyftSuccess(message="Routes Exchanged")

    @service_method(path="network.add_peer", name="add_peer", roles=GUEST_ROLE_LEVEL)
    def add_peer(
        self,
        context: AuthedServiceContext,
        peer: NodePeer,
        challenge: bytes,
        self_node_route: NodeRoute,
        verify_key: SyftVerifyKey,
    ) -> list | SyftError:
        """Add a Network Node Peer"""
        # Using the verify_key of the peer to verify the signature
        # It is also our single source of truth for the peer
        if peer.verify_key != context.credentials:
            return SyftError(
                message=(
                    f"The {type(peer)}.verify_key: "
                    f"{peer.verify_key} does not match the signature of the message"
                )
            )

        context.node = cast(AbstractNode, context.node)
        if verify_key != context.node.verify_key:
            return SyftError(
                message="verify_key does not match the remote node's verify_key for add_peer"
            )

        try:
            remote_client: SyftClient = peer.client_with_context(context=context)
            random_challenge = secrets.token_bytes(16)
            remote_res = remote_client.api.services.network.ping(
                challenge=random_challenge
            )
        except Exception as e:
            return SyftError(message="Remote Peer cannot ping peer:" + str(e))

        if isinstance(remote_res, SyftError):
            return remote_res

        challenge_signature = remote_res

        # Verifying if the challenge is valid
        try:
            peer.verify_key.verify_key.verify(random_challenge, challenge_signature)
        except Exception as e:
            return SyftError(message=str(e))

        result = self.stash.update_peer(context.node.verify_key, peer)
        if result.is_err():
            return SyftError(message=str(result.err()))

        # this way they can match up who we are with who they think we are
        # Sending a signed messages for the peer to verify
        self_node_peer = self_node_route.validate_with_context(context=context)

        if isinstance(self_node_peer, SyftError):
            return self_node_peer

        # Q,TODO: Should the returned node peer also be signed
        # as the challenge is already signed
        challenge_signature = context.node.signing_key.signing_key.sign(
            challenge
        ).signature

        return [challenge_signature, self_node_peer]

    @service_method(path="network.ping", name="ping", roles=GUEST_ROLE_LEVEL)
    def ping(
        self, context: AuthedServiceContext, challenge: bytes
    ) -> bytes | SyftError:
        """To check alivesness/authenticity of a peer"""

        # # Only the root user can ping the node to check its state
        # if context.node.verify_key != context.credentials:
        #     return SyftError(message=("Only the root user can access ping endpoint"))

        # this way they can match up who we are with who they think we are
        # Sending a signed messages for the peer to verify
        context.node = cast(AbstractNode, context.node)
        challenge_signature = context.node.signing_key.signing_key.sign(
            challenge
        ).signature

        return challenge_signature

    @service_method(path="network.add_route_for", name="add_route_for")
    def add_route_for(
        self,
        context: AuthedServiceContext,
        peer: NodePeer,
        route: NodeRoute,
    ) -> SyftSuccess | SyftError:
        """Add route for the node peer

        Args:
            context (AuthedServiceContext): The authentication context.
            peer (NodePeer): The peer node to add the route for.
            route (NodeRoute): The route to be added.
        Returns:
            SyftSuccess | SyftError: A success message if the route is verified,
                otherwise an error message.
        """
        context.node = cast(AbstractNode, context.node)
        # the peer verifies the new route to the current node
        peer_client: SyftClient = peer.client_with_context(context=context)
        node_peer: NodePeer | SyftError = (
            peer_client.api.services.network.verify_route_for(route)
        )
        if isinstance(node_peer, SyftError):
            return node_peer

        existed_route: NodeRoute | None = peer.update_route(route)
        # update the peer in the store
        result = self.stash.update(context.node.verify_key, peer)
        if result.is_err():
            return SyftError(message=str(result.err()))
        if existed_route is None:
            return SyftSuccess(
                message=f"New route with id '{route.id}' added for {peer.name}"
            )
        return SyftSuccess(
            message=f"The route already exists with id {existed_route.id}, so its priority was updated"
        )

    @service_method(
        path="network.verify_route_for", name="verify_route_for", roles=GUEST_ROLE_LEVEL
    )
    def verify_route_for(
        self, context: AuthedServiceContext, route: NodeRoute
    ) -> NodePeer | SyftError:
        # get the peer asking for route verification from its verify_key
        context.node = cast(AbstractNode, context.node)
        peer: Result[NodePeer, SyftError] = self.stash.get_for_verify_key(
            context.node.verify_key,
            context.credentials,
        )
        if peer.is_err():
            return SyftError(message=peer.err())
        peer = peer.ok()

        if peer.verify_key != context.credentials:
            return SyftError(
                message=(
                    f"verify_key: {context.credentials} at route {route} "
                    f"does not match listed peer: {peer}"
                )
            )
        return peer

    @service_method(
        path="network.get_all_peers", name="get_all_peers", roles=GUEST_ROLE_LEVEL
    )
    def get_all_peers(
        self, context: AuthedServiceContext
    ) -> list[NodePeer] | SyftError:
        """Get all Peers"""
        context.node = cast(AbstractNode, context.node)
        result = self.stash.get_all(
            credentials=context.node.verify_key,
            order_by=OrderByNamePartitionKey,
        )
        if result.is_ok():
            peers = result.ok()
            return peers
        return SyftError(message=result.err())

    @service_method(
        path="network.get_peer_by_name", name="get_peer_by_name", roles=GUEST_ROLE_LEVEL
    )
    def get_peer_by_name(
        self, context: AuthedServiceContext, name: str
    ) -> NodePeer | None | SyftError:
        """Get Peer by Name"""
        context.node = cast(AbstractNode, context.node)
        result = self.stash.get_by_name(
            credentials=context.node.verify_key,
            name=name,
        )
        if result.is_ok():
            peer = result.ok()
            return peer
        return SyftError(message=str(result.err()))

    @service_method(
        path="network.get_peers_by_type",
        name="get_peers_by_type",
        roles=GUEST_ROLE_LEVEL,
    )
    def get_peers_by_type(
        self, context: AuthedServiceContext, node_type: NodeType
    ) -> list[NodePeer] | SyftError:
        context.node = cast(AbstractNode, context.node)
        result = self.stash.get_by_node_type(
            credentials=context.node.verify_key,
            node_type=node_type,
        )

        if result.is_err():
            return SyftError(message=str(result.err()))

        # Return peers or an empty list when result is None
        return result.ok() or []

    @service_method(
        path="network.delete_peer_by_id",
        name="delete_peer_by_id",
        roles=DATA_OWNER_ROLE_LEVEL,
    )
    def delete_peer_by_id(
        self, context: AuthedServiceContext, uid: UID
    ) -> SyftSuccess | SyftError:
        """Delete Node Peer"""
        result = self.stash.delete_by_uid(context.credentials, uid)
        if result.is_err():
            return SyftError(message=str(result.err()))
        return SyftSuccess(message="Node Peer Deleted")

    @service_method(
        path="network.exchange_veilid_route",
        name="exchange_veilid_route",
        roles=DATA_OWNER_ROLE_LEVEL,
    )
    def exchange_veilid_route(
        self,
        context: AuthedServiceContext,
        remote_node_route: NodeRoute,
    ) -> SyftSuccess | SyftError:
        """Exchange Route With Another Node"""
        context.node = cast(AbstractNode, context.node)
        # Step 1: Get our own Veilid Node Peer to send to the remote node
        self_node_peer: NodePeer = context.node.settings.to(NodePeer)

        veilid_service = context.node.get_service("veilidservice")
        veilid_route = veilid_service.get_veilid_route(context=context)

        if isinstance(veilid_route, SyftError):
            return veilid_route

        self_node_peer.node_routes = [veilid_route]

        # Step 2: Create a Remote Client
        remote_client: SyftClient = remote_node_route.client_with_context(
            context=context
        )

        # Step 3: Send the Node Peer to the remote node
        remote_node_peer: NodePeer | SyftError = (
            remote_client.api.services.network.add_veilid_peer(
                peer=self_node_peer,
            )
        )

        if not isinstance(remote_node_peer, NodePeer):
            return remote_node_peer

        # Step 4: Add the remote Node Peer to our stash
        result = self.stash.update_peer(context.node.verify_key, remote_node_peer)
        if result.is_err():
            return SyftError(message=str(result.err()))

        return SyftSuccess(message="Routes Exchanged")

    @service_method(
        path="network.add_veilid_peer", name="add_veilid_peer", roles=GUEST_ROLE_LEVEL
    )
    def add_veilid_peer(
        self,
        context: AuthedServiceContext,
        peer: NodePeer,
    ) -> NodePeer | SyftError:
        """Add a Veilid Node Peer"""
        context.node = cast(AbstractNode, context.node)
        # Step 1: Using the verify_key of the peer to verify the signature
        # It is also our single source of truth for the peer
        if peer.verify_key != context.credentials:
            return SyftError(
                message=(
                    f"The {type(peer)}.verify_key: "
                    f"{peer.verify_key} does not match the signature of the message"
                )
            )

        # Step 2: Save the remote peer to our stash
        result = self.stash.update_peer(context.node.verify_key, peer)
        if result.is_err():
            return SyftError(message=str(result.err()))

        # Step 3: Get our own Veilid Node Peer to send to the remote node
        self_node_peer: NodePeer = context.node.settings.to(NodePeer)

        veilid_service = context.node.get_service("veilidservice")
        veilid_route = veilid_service.get_veilid_route(context=context)

        if isinstance(veilid_route, SyftError):
            return veilid_route

        self_node_peer.node_routes = [veilid_route]

        return self_node_peer

    @service_method(
        path="network.update_route_priority_for", name="update_route_priority_for"
    )
    def update_route_priority_for(
        self,
        context: AuthedServiceContext,
        peer: NodePeer,
        route: NodeRoute,
        priority: int | None = None,
    ) -> SyftSuccess | SyftError:
        """
        Updates a route's priority for the given peer

        Args:
            context (AuthedServiceContext): The authentication context for the service.
            peer (NodePeer): The peer for which the route priority needs to be updated.
            route (NodeRoute): The route for which the priority needs to be updated.
            priority (int | None): The new priority value for the route. If not
                provided, it will be assigned the highest priority among all peers

        Returns:
            SyftSuccess | SyftError: Successful / Error response
        """
        context.node = cast(AbstractNode, context.node)
        # update the route's priority for the peer
        updated_node_route: NodeRoute | SyftError = peer.update_existed_route_priority(
            route=route, priority=priority
        )
        if isinstance(updated_node_route, SyftError):
            return updated_node_route
        new_priority: int = updated_node_route.priority
        # update the peer in the store
        result = self.stash.update(context.node.verify_key, peer)
        if result.is_err():
            return SyftError(message=str(result.err()))

        return SyftSuccess(
            message=f"Route {route.id}'s priority updated to {new_priority} for peer {peer.name}"
        )

    @service_method(path="network.delete_route_for", name="delete_route_for")
    def delete_route_for(
        self,
        context: AuthedServiceContext,
        peer: NodePeer,
        route: NodeRoute | None = None,
        route_id: UID | None = None,
    ) -> SyftSuccess | SyftError:
        """
        Delete a route for a given peer in the network. If a peer has no
        routes left, it will be removed from the stash and will no longer be a peer.

        Args:
            context (AuthedServiceContext): The authentication context for the service.
            peer (NodePeer): The peer for which the route will be deleted.
            route (NodeRoute): The route to be deleted.

        Returns:
            SyftSuccess | SyftError: Successful / Error response
        """
        context.node = cast(AbstractNode, context.node)

        if route is None and route_id is None:
            return SyftError(
                message="Either `route` or `route_id` arg must be provided"
            )
        if route and route_id and route.id != route_id:
            return SyftError(
                message="The provided route's id and route_id do not match"
            )

        if route:
            result = peer.delete_route(route=route)
            return_message = f"Route {route.id} deleted for peer {peer.name}."
        if route_id:
            result = peer.delete_route(route_id=route_id)
            return_message = f"Route {route_id} deleted for peer {peer.name}."
        if isinstance(result, SyftError):
            return result

        if len(peer.node_routes) == 0:
            # remove the peer
            result = self.stash.delete_by_uid(
                credentials=context.credentials, uid=peer.id
            )
            if result.is_ok():
                return_message += (
                    f" No routes left for peer {peer.name}, so it is deleted."
                )
            else:
                return SyftError(message=result.err())
        else:
            # update the peer with the route removed
            result = self.stash.update(context.node.verify_key, peer)
            if result.is_err():
                return SyftError(message=str(result.err()))

        return SyftSuccess(message=return_message)


TYPE_TO_SERVICE[NodePeer] = NetworkService
SERVICE_TO_TYPES[NetworkService].update({NodePeer})


def from_grid_url(context: TransformContext) -> TransformContext:
    if context.obj is not None and context.output is not None:
        url = context.obj.url.as_container_host()
        context.output["host_or_ip"] = url.host_or_ip
        context.output["protocol"] = url.protocol
        context.output["port"] = url.port
        context.output["private"] = False
        context.output["proxy_target_uid"] = context.obj.proxy_target_uid
        context.output["priority"] = 1

    return context


@transform(HTTPConnection, HTTPNodeRoute)
def http_connection_to_node_route() -> list[Callable]:
    return [from_grid_url]


def get_python_node_route(context: TransformContext) -> TransformContext:
    if context.output is not None and context.obj is not None:
        context.output["id"] = context.obj.node.id
        context.output["worker_settings"] = WorkerSettings.from_node(context.obj.node)
        context.output["proxy_target_uid"] = context.obj.proxy_target_uid
    return context


@transform(PythonConnection, PythonNodeRoute)
def python_connection_to_node_route() -> list[Callable]:
    return [get_python_node_route]


@transform_method(PythonNodeRoute, PythonConnection)
def node_route_to_python_connection(
    obj: Any, context: TransformContext | None = None
) -> list[Callable]:
    return PythonConnection(node=obj.node, proxy_target_uid=obj.proxy_target_uid)


@transform_method(HTTPNodeRoute, HTTPConnection)
def node_route_to_http_connection(
    obj: Any, context: TransformContext | None = None
) -> list[Callable]:
    url = GridURL(
        protocol=obj.protocol, host_or_ip=obj.host_or_ip, port=obj.port
    ).as_container_host()
    return HTTPConnection(url=url, proxy_target_uid=obj.proxy_target_uid)


@transform_method(VeilidNodeRoute, VeilidConnection)
def node_route_to_veilid_connection(
    obj: VeilidNodeRoute, context: TransformContext | None = None
) -> list[Callable]:
    return VeilidConnection(vld_key=obj.vld_key, proxy_target_uid=obj.proxy_target_uid)


@transform_method(VeilidConnection, VeilidNodeRoute)
def veilid_connection_to_node_route(
    obj: VeilidConnection, context: TransformContext | None = None
) -> list[Callable]:
    return VeilidNodeRoute(vld_key=obj.vld_key, proxy_target_uid=obj.proxy_target_uid)


@transform(NodeMetadataV3, NodePeer)
def metadata_to_peer() -> list[Callable]:
    return [
        keep(["id", "name", "verify_key", "node_type", "admin_email"]),
    ]


@transform(NodeSettingsV2, NodePeer)
def settings_to_peer() -> list[Callable]:
    return [
        keep(["id", "name", "verify_key", "node_type", "admin_email"]),
    ]
