# stdlib
import random
from typing import Any
from uuid import uuid4

# third party
import numpy as np
import pandas as pd
from pydantic import ValidationError
import pytest
import torch

# syft absolute
import syft as sy
from syft.server.worker import Worker
from syft.service.action.action_object import ActionObject
from syft.service.action.action_object import TwinMode
from syft.service.blob_storage.util import can_upload_to_blob_storage
from syft.service.dataset.dataset import CreateAsset as Asset
from syft.service.dataset.dataset import CreateDataset as Dataset
from syft.service.dataset.dataset import _ASSET_WITH_NONE_MOCK_ERROR_MESSAGE
from syft.service.response import SyftError
from syft.service.response import SyftException
from syft.service.response import SyftSuccess


def random_hash() -> str:
    return uuid4().hex


def data():
    return np.array([1, 2, 3])


def mock():
    return np.array([1, 1, 1])


def make_asset_without_mock() -> dict[str, Any]:
    return {
        "name": random_hash(),
        "data": data(),
    }


def make_asset_with_mock() -> dict[str, Any]:
    return {**make_asset_without_mock(), "mock": mock()}


def make_asset_with_empty_mock() -> dict[str, Any]:
    return {**make_asset_without_mock(), "mock": ActionObject.empty()}


asset_without_mock = pytest.fixture(make_asset_without_mock)
asset_with_mock = pytest.fixture(make_asset_with_mock)
asset_with_empty_mock = pytest.fixture(make_asset_with_empty_mock)


@pytest.mark.parametrize(
    "asset_without_mock",
    [
        make_asset_without_mock(),
        {**make_asset_without_mock(), "mock": ActionObject.empty()},
    ],
)
def test_asset_without_mock_mock_is_real_must_be_false(
    asset_without_mock: dict[str, Any],
):
    asset = Asset(**asset_without_mock, mock_is_real=True)
    asset.mock_is_real = True
    assert not asset.mock_is_real


def test_mock_always_not_real_after_calling_no_mock(
    asset_with_mock: dict[str, Any],
) -> None:
    asset = Asset(**asset_with_mock, mock_is_real=True)
    assert asset.mock_is_real

    asset.no_mock()
    assert not asset.mock_is_real


def test_mock_always_not_real_after_set_mock_to_empty(
    asset_with_mock: dict[str, Any],
) -> None:
    asset = Asset(**asset_with_mock, mock_is_real=True)
    assert asset.mock_is_real

    asset.no_mock()
    assert not asset.mock_is_real

    asset.mock_is_real = True
    assert not asset.mock_is_real

    asset.mock = mock()
    asset.mock_is_real = True
    assert asset.mock_is_real


def test_mock_always_not_real_after_set_to_empty(
    asset_with_mock: dict[str, Any],
) -> None:
    asset = Asset(**asset_with_mock, mock_is_real=True)
    assert asset.mock_is_real

    asset.mock = ActionObject.empty()
    assert not asset.mock_is_real

    asset.mock_is_real = True
    assert not asset.mock_is_real

    asset.mock = mock()
    asset.mock_is_real = True
    assert asset.mock_is_real


@pytest.mark.parametrize(
    "empty_mock",
    [
        None,
        ActionObject.empty(),
    ],
)
def test_cannot_set_empty_mock_with_true_mock_is_real(
    asset_with_mock: dict[str, Any], empty_mock: Any
) -> None:
    asset = Asset(**asset_with_mock, mock_is_real=True)
    assert asset.mock_is_real

    with pytest.raises(SyftException):
        asset.set_mock(empty_mock, mock_is_real=True)

    assert asset.mock is asset_with_mock["mock"]


def test_dataset_cannot_have_assets_with_none_mock() -> None:
    TOTAL_ASSETS = 10
    ASSETS_WITHOUT_MOCK = random.randint(2, 8)
    ASSETS_WITH_MOCK = TOTAL_ASSETS - ASSETS_WITHOUT_MOCK

    assets_without_mock = [
        Asset(**make_asset_without_mock()) for _ in range(ASSETS_WITHOUT_MOCK)
    ]
    assets_with_mock = [
        Asset(**make_asset_with_mock()) for _ in range(ASSETS_WITH_MOCK)
    ]
    assets = assets_without_mock + assets_with_mock

    with pytest.raises(ValidationError) as excinfo:
        Dataset(
            name=random_hash(),
            asset_list=assets,
        )

    assert _ASSET_WITH_NONE_MOCK_ERROR_MESSAGE in str(excinfo.value)

    assert Dataset(name=random_hash(), asset_list=assets_with_mock)


def test_dataset_can_have_assets_with_empty_mock() -> None:
    TOTAL_ASSETS = 10
    ASSETS_WITH_EMPTY_MOCK = random.randint(2, 8)
    ASSETS_WITH_MOCK = TOTAL_ASSETS - ASSETS_WITH_EMPTY_MOCK

    assets_without_mock = [
        Asset(**make_asset_without_mock(), mock=ActionObject.empty())
        for _ in range(ASSETS_WITH_EMPTY_MOCK)
    ]
    assets_with_mock = [
        Asset(**make_asset_with_mock()) for _ in range(ASSETS_WITH_MOCK)
    ]
    assets = assets_without_mock + assets_with_mock

    assert Dataset(name=random_hash(), asset_list=assets)


def test_cannot_add_assets_with_none_mock_to_dataset(
    asset_with_mock: dict[str, Any], asset_without_mock: dict[str, Any]
) -> None:
    dataset = Dataset(name=random_hash())

    with_mock = Asset(**asset_with_mock)
    with_none_mock = Asset(**asset_without_mock)

    dataset.add_asset(with_mock)

    with pytest.raises(ValueError) as excinfo:
        dataset.add_asset(with_none_mock)

    assert _ASSET_WITH_NONE_MOCK_ERROR_MESSAGE in str(excinfo.value)


def test_guest_client_get_empty_mock_as_private_pointer(
    worker: Worker,
    asset_with_empty_mock: dict[str, Any],
) -> None:
    asset = Asset(**asset_with_empty_mock)
    dataset = Dataset(name=random_hash(), asset_list=[asset])

    root_datasite_client = worker.root_client
    root_datasite_client.upload_dataset(dataset)

    guest_datasite_client = root_datasite_client.guest()
    guest_datasets = guest_datasite_client.api.services.dataset.get_all()
    guest_dataset = guest_datasets[0]

    mock = guest_dataset.assets[0].pointer

    assert not mock.is_real
    assert mock.is_pointer
    assert mock.syft_twin_type is TwinMode.MOCK


def test_datasite_client_cannot_upload_dataset_with_non_mock(worker: Worker) -> None:
    assets = [Asset(**make_asset_with_mock()) for _ in range(10)]
    dataset = Dataset(name=random_hash(), asset_list=assets)

    dataset.asset_list[0].mock = None

    root_datasite_client = worker.root_client

    with pytest.raises(ValueError) as excinfo:
        root_datasite_client.upload_dataset(dataset)

    assert _ASSET_WITH_NONE_MOCK_ERROR_MESSAGE in str(excinfo.value)


def test_adding_contributors_with_duplicate_email():
    # Datasets

    dataset = Dataset(name="Sample  dataset")
    res1 = dataset.add_contributor(
        role=sy.roles.UPLOADER, name="Alice", email="alice@naboo.net"
    )
    res2 = dataset.add_contributor(
        role=sy.roles.UPLOADER, name="Alice Smith", email="alice@naboo.net"
    )

    assert isinstance(res1, SyftSuccess)
    assert isinstance(res2, SyftError)
    assert len(dataset.contributors) == 1

    # Assets
    asset = Asset(**make_asset_without_mock(), mock=ActionObject.empty())

    res3 = asset.add_contributor(
        role=sy.roles.UPLOADER, name="Bob", email="bob@naboo.net"
    )

    res4 = asset.add_contributor(
        role=sy.roles.UPLOADER, name="Bob Abraham", email="bob@naboo.net"
    )
    dataset.add_asset(asset)

    assert isinstance(res3, SyftSuccess)
    assert isinstance(res4, SyftError)
    assert len(asset.contributors) == 1


@pytest.fixture(
    params=[
        1,
        "hello",
        {"key": "value"},
        {1, 2, 3},
        np.array([1, 2, 3]),
        pd.DataFrame(data={"col1": [1, 2], "col2": [3, 4]}),
        torch.Tensor([1, 2, 3]),
    ]
)
def different_data_types(
    request,
) -> int | str | dict | set | np.ndarray | pd.DataFrame | torch.Tensor:
    return request.param


def test_upload_dataset_with_assets_of_different_data_types(
    worker: Worker,
    different_data_types: (
        int | str | dict | set | np.ndarray | pd.DataFrame | torch.Tensor
    ),
) -> None:
    asset = sy.Asset(
        name=random_hash(),
        data=different_data_types,
        mock=different_data_types,
    )
    dataset = Dataset(name=random_hash())
    dataset.add_asset(asset)
    root_datasite_client = worker.root_client
    res = root_datasite_client.upload_dataset(dataset)
    assert isinstance(res, SyftSuccess)
    assert len(root_datasite_client.api.services.dataset.get_all()) == 1
    assert type(root_datasite_client.datasets[0].assets[0].data) == type(
        different_data_types
    )
    assert type(root_datasite_client.datasets[0].assets[0].mock) == type(
        different_data_types
    )


def test_upload_delete_small_dataset(worker: Worker, small_dataset: Dataset) -> None:
    root_client = worker.root_client
    assert not can_upload_to_blob_storage(small_dataset, root_client.metadata)
    upload_res = root_client.upload_dataset(small_dataset)
    assert isinstance(upload_res, SyftSuccess)

    dataset = root_client.api.services.dataset.get_all()[0]
    asset = dataset.asset_list[0]
    assert isinstance(asset.data, np.ndarray)
    assert isinstance(asset.mock, np.ndarray)
    assert len(root_client.api.services.blob_storage.get_all()) == 0

    # delete the dataset without deleting its assets
    del_res = root_client.api.services.dataset.delete(
        uid=dataset.id, delete_assets=False
    )
    assert isinstance(del_res, SyftSuccess)
    assert isinstance(asset.data, np.ndarray)
    assert isinstance(asset.mock, np.ndarray)
    assert len(root_client.api.services.dataset.get_all()) == 0

    # we can still get back the deleted dataset by uid
    deleted_dataset = root_client.api.services.dataset.get_by_id(uid=dataset.id)
    assert deleted_dataset.name == f"_deleted_{dataset.name}_{dataset.id}"
    assert deleted_dataset.to_be_deleted

    # delete the dataset and its assets
    del_res = root_client.api.services.dataset.delete(
        uid=dataset.id, delete_assets=True
    )
    assert isinstance(del_res, SyftSuccess)
    assert asset.data is None
    assert isinstance(asset.mock, SyftError)
    assert len(root_client.api.services.dataset.get_all()) == 0


def test_upload_delete_big_dataset(worker: Worker, big_dataset: Dataset) -> None:
    root_client = worker.root_client
    assert can_upload_to_blob_storage(big_dataset, root_client.metadata)
    upload_res = root_client.upload_dataset(big_dataset)
    assert isinstance(upload_res, SyftSuccess)

    dataset = root_client.api.services.dataset.get_all()[0]
    asset = dataset.asset_list[0]
    assert isinstance(asset.data, np.ndarray)
    assert isinstance(asset.mock, np.ndarray)
    # test that the data is saved in the blob storage
    assert len(root_client.api.services.blob_storage.get_all()) == 2

    # delete the dataset without deleting its assets
    del_res = root_client.api.services.dataset.delete(
        uid=dataset.id, delete_assets=False
    )
    assert isinstance(del_res, SyftSuccess)
    assert isinstance(asset.data, np.ndarray)
    assert isinstance(asset.mock, np.ndarray)
    assert len(root_client.api.services.dataset.get_all()) == 0
    # we can still get back the deleted dataset by uid
    deleted_dataset = root_client.api.services.dataset.get_by_id(uid=dataset.id)
    assert deleted_dataset.name == f"_deleted_{dataset.name}_{dataset.id}"
    assert deleted_dataset.to_be_deleted
    # the dataset's blob entries are still there
    assert len(root_client.api.services.blob_storage.get_all()) == 2

    # delete the dataset
    del_res = root_client.api.services.dataset.delete(
        uid=dataset.id, delete_assets=True
    )
    assert isinstance(del_res, SyftSuccess)
    assert asset.data is None
    assert isinstance(asset.mock, SyftError)
    assert len(root_client.api.services.blob_storage.get_all()) == 0
    assert len(root_client.api.services.dataset.get_all()) == 0


def test_reupload_dataset(worker: Worker, small_dataset: Dataset) -> None:
    root_client = worker.root_client

    # upload a dataset
    upload_res = root_client.upload_dataset(small_dataset)
    assert isinstance(upload_res, SyftSuccess)
    dataset = root_client.api.services.dataset.get_all()[0]

    # delete the dataset
    del_res = root_client.api.services.dataset.delete(dataset.id)
    assert isinstance(del_res, SyftSuccess)
    assert len(root_client.api.services.dataset.get_all()) == 0
    assert len(root_client.api.services.dataset.get_all(include_deleted=True)) == 1
    search_res = root_client.api.services.dataset.search(dataset.name)
    assert len(search_res) == 0

    # reupload a dataset with the same name should be successful
    reupload_res = root_client.upload_dataset(small_dataset)
    assert isinstance(reupload_res, SyftSuccess)
    assert len(root_client.api.services.dataset.get_all()) == 1
    assert len(root_client.api.services.dataset.get_all(include_deleted=True)) == 2
    search_res = root_client.api.services.dataset.search(dataset.name)
    assert len(search_res) == 1
    assert all(small_dataset.assets[0].data == search_res[0].assets[0].data)
    assert all(small_dataset.assets[0].mock == search_res[0].assets[0].mock)


def test_upload_dataset_with_force_replace_small_dataset(
    worker: Worker, small_dataset: Dataset
) -> None:
    root_client = worker.root_client

    # upload a dataset
    upload_res = root_client.upload_dataset(small_dataset)
    assert isinstance(upload_res, SyftSuccess)
    first_uploaded_dataset = root_client.api.services.dataset.get_all()[0]

    # upload again without the `force_replace` flag should fail
    reupload_res = root_client.upload_dataset(small_dataset)
    assert isinstance(reupload_res, SyftError)

    # change something about the dataset, then upload it again with `force_replace`
    dataset = Dataset(
        name=small_dataset.name,
        asset_list=[
            sy.Asset(
                name="small_dataset",
                data=np.array([3, 2, 1]),
                mock=np.array([2, 2, 2]),
            )
        ],
        description="This is my numpy data",
        url="https://mydataset.com",
        summary="contain some super secret data",
    )
    force_replace_upload_res = root_client.upload_dataset(dataset, force_replace=True)
    assert isinstance(force_replace_upload_res, SyftSuccess)
    assert len(root_client.api.services.dataset.get_all()) == 1

    updated_dataset = root_client.api.services.dataset.get_all()[0]
    assert updated_dataset.id == first_uploaded_dataset.id
    assert updated_dataset.name == small_dataset.name
    assert updated_dataset.description.text == dataset.description.text
    assert updated_dataset.summary == dataset.summary
    assert updated_dataset.url == dataset.url
    assert all(updated_dataset.assets[0].data == dataset.assets[0].data)
    assert all(updated_dataset.assets[0].mock == dataset.assets[0].mock)


def test_upload_dataset_with_force_replace_big_dataset(
    worker: Worker, big_dataset: Dataset
) -> None:
    root_client = worker.root_client
    assert can_upload_to_blob_storage(big_dataset, root_client.metadata)

    # upload a dataset
    upload_res = root_client.upload_dataset(big_dataset)
    assert isinstance(upload_res, SyftSuccess)
    first_uploaded_dataset = root_client.api.services.dataset.get_all()[0]

    # change about the dataset metadata and also its data and mock, but keep its name,
    # then upload it again with `force_replace=True`
    updated_mock = big_dataset.assets[0].mock * 2
    updated_data = big_dataset.assets[0].data + 1

    dataset = Dataset(
        name=big_dataset.name,
        asset_list=[
            sy.Asset(
                name="big_dataset",
                data=updated_data,
                mock=updated_mock,
            )
        ],
        description="This is my numpy data",
        url="https://mydataset.com",
        summary="contain some super secret data",
    )
    force_replace_upload_res = root_client.upload_dataset(dataset, force_replace=True)
    assert isinstance(force_replace_upload_res, SyftSuccess)
    # TODO: Old data were not removed from the blob storage after force replace. What to do?
    assert len(root_client.api.services.blob_storage.get_all()) == 4
    assert len(root_client.api.services.dataset.get_all()) == 1

    updated_dataset = root_client.api.services.dataset.get_all()[0]
    assert updated_dataset.id == first_uploaded_dataset.id
    assert updated_dataset.name == big_dataset.name
    assert updated_dataset.description.text == dataset.description.text
    assert updated_dataset.summary == dataset.summary
    assert updated_dataset.url == dataset.url
    assert all(updated_dataset.assets[0].data == dataset.assets[0].data)
    assert all(updated_dataset.assets[0].mock == dataset.assets[0].mock)
    retrieved_mock = root_client.api.services.blob_storage.read(
        updated_dataset.assets[0].mock_blob_storage_entry_id
    ).read()
    assert np.sum(retrieved_mock - updated_mock) == 0
    retrieved_data = root_client.api.services.blob_storage.read(
        updated_dataset.assets[0].data_blob_storage_entry_id
    ).read()
    assert np.sum(retrieved_data - updated_data) == 0


def test_upload_big_dataset_blob_permissions(
    worker: Worker, big_dataset: Dataset
) -> None:
    root_client = worker.root_client
    assert can_upload_to_blob_storage(big_dataset, root_client.metadata)

    # upload the dataset
    upload_res = root_client.upload_dataset(big_dataset)
    assert isinstance(upload_res, SyftSuccess)
    uploaded_dataset = root_client.api.services.dataset.get_all()[0]

    # check correctness of the uploaded data in blob storage
    asset = uploaded_dataset.assets[0]
    retrieved_mock = root_client.api.services.blob_storage.read(
        asset.mock_blob_storage_entry_id
    ).read()
    assert np.sum(retrieved_mock - asset.mock) == 0
    retrieved_data = root_client.api.services.blob_storage.read(
        asset.data_blob_storage_entry_id
    ).read()
    assert np.sum(retrieved_data - asset.data) == 0

    # check access permissions of the uploaded data in blob storage
    guest_client = root_client.guest()
    guest_dataset = guest_client.api.services.dataset.get_all()[0]
    guest_asset = guest_dataset.assets[0]
    guest_retrieved_mock = guest_client.api.services.blob_storage.read(
        guest_asset.mock_blob_storage_entry_id
    ).read()
    assert np.sum(retrieved_mock - guest_retrieved_mock) == 0
    guest_retrieved_data = guest_client.api.services.blob_storage.read(
        guest_asset.data_blob_storage_entry_id
    )
    assert isinstance(guest_retrieved_data, SyftError)
