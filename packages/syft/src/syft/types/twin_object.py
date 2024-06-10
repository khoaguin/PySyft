# future
from __future__ import annotations

# stdlib
from typing import Any
from typing import ClassVar

# third party
from pydantic import field_validator
from pydantic import model_validator
from typing_extensions import Self

# relative
from ..serde.serializable import serializable
from ..service.action.action_object import ActionObject
from ..service.action.action_object import TwinMode
from ..service.action.action_types import action_types
from ..service.response import SyftError
from ..types.syft_object import SYFT_OBJECT_VERSION_2
from .syft_object import SyftObject
from .uid import UID


def to_action_object(obj: Any) -> ActionObject:
    if isinstance(obj, ActionObject):
        return obj

    if type(obj) in action_types:
        return action_types[type(obj)](syft_action_data_cache=obj)
    raise ValueError(f"{type(obj)} not in action_types")


@serializable()
class TwinObject(SyftObject):
    __canonical_name__ = "TwinObject"
    __version__ = SYFT_OBJECT_VERSION_2

    __attr_searchable__: ClassVar[list[str]] = []

    id: UID
    private_obj: ActionObject
    private_obj_id: UID = None  # type: ignore
    mock_obj: ActionObject
    mock_obj_id: UID = None  # type: ignore

    @field_validator("private_obj", mode="before")
    @classmethod
    def make_private_obj(cls, v: Any) -> ActionObject:
        return to_action_object(v)

    @model_validator(mode="after")
    def make_private_obj_id(self) -> Self:
        if self.private_obj_id is None:
            self.private_obj_id = self.private_obj.id  # type: ignore[unreachable]
        return self

    @field_validator("mock_obj", mode="before")
    @classmethod
    def make_mock_obj(cls, v: Any) -> ActionObject:
        return to_action_object(v)

    @model_validator(mode="after")
    def make_mock_obj_id(self) -> Self:
        if self.mock_obj_id is None:
            self.mock_obj_id = self.mock_obj.id  # type: ignore[unreachable]
        return self

    @property
    def private(self) -> ActionObject:
        twin_id = self.id
        private = self.private_obj
        private.syft_twin_type = TwinMode.PRIVATE
        private.id = twin_id
        return private

    @property
    def mock(self) -> ActionObject:
        twin_id = self.id
        mock = self.mock_obj
        mock.syft_twin_type = TwinMode.MOCK
        mock.id = twin_id
        return mock

    def _save_to_blob_storage(self) -> SyftError | None:
        # Set node location and verify key
        self.private_obj._set_obj_location_(
            self.syft_node_location,
            self.syft_client_verify_key,
        )
        self.mock_obj._set_obj_location_(
            self.syft_node_location,
            self.syft_client_verify_key,
        )
        mock_store_res = self.mock_obj._save_to_blob_storage()
        if isinstance(mock_store_res, SyftError):
            return mock_store_res
        return self.private_obj._save_to_blob_storage()
