# stdlib
from typing import Any
from typing import ClassVar

from syft.types.uid import UID

# relative
from ...serde.serializable import serializable
from ...types.syft_object import SYFT_OBJECT_VERSION_3
from ...types.syncable_object import SyncableSyftObject
from ...service.context import AuthedServiceContext


@serializable()
class SyftLog(SyncableSyftObject):
    __canonical_name__ = "SyftLog"
    __version__ = SYFT_OBJECT_VERSION_3

    __repr_attrs__ = ["stdout", "stderr"]
    __exclude_sync_diff_attrs__: list[str] = []
    __private_sync_attr_mocks__: ClassVar[dict[str, Any]] = {
        "stderr": "",
        "stdout": "",
    }

    stdout: str = ""
    stderr: str = ""
    job_id: UID

    def append(self, new_str: str) -> None:
        self.stdout += new_str

    def append_error(self, new_str: str) -> None:
        self.stderr += new_str

    def restart(self) -> None:
        self.stderr = ""
        self.stdout = ""
    
    def get_sync_dependencies(self, context: AuthedServiceContext, **kwargs: dict) -> list[UID]:  # type: ignore
        return [self.job_id]

    