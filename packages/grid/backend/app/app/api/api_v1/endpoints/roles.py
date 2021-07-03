# stdlib
from typing import Any
from typing import Optional

# third party
from fastapi import APIRouter
from fastapi import Body
from fastapi import Depends
from fastapi.responses import JSONResponse
from nacl.encoding import HexEncoder
from nacl.signing import SigningKey

# syft absolute
from syft.core.node.common.action.exception_action import ExceptionMessage
from syft.core.node.common.tables.utils import model_to_json

# syft
from syft.grid.messages.role_messages import CreateRoleMessage
from syft.grid.messages.role_messages import DeleteRoleMessage
from syft.grid.messages.role_messages import GetRoleMessage
from syft.grid.messages.role_messages import GetRolesMessage
from syft.grid.messages.role_messages import UpdateRoleMessage

# grid absolute
from app.api import deps
from app.core.node import domain

router = APIRouter()


@router.post("", status_code=201, response_class=JSONResponse)
def create_role_route(
    current_user: Any = Depends(deps.get_current_user),
    name: str = Body(False, example="Researcher"),
    can_triage_requests: bool = Body(False, example="false"),
    can_edit_settings: bool = Body(False, example="false"),
    can_create_users: bool = Body(False, example="false"),
    can_create_groups: bool = Body(False, example="false"),
    can_edit_roles: bool = Body(False, example="false"),
    can_manage_infrastructure: bool = Body(False, example="false"),
    can_upload_data: bool = Body(False, example="false"),
):
    """Creates a new PyGrid role.

    Args:
        current_user : Current session.
        name: Role name.
        can_triage_requests: Allow role to triage requests.
        can_edit_settings: Allow role to edit settings.
        can_create_users: Allow role to create users.
        can_create_groups: Allow role to create groups.
        can_edit_roles: Allow role to edit other roles.
        can_manage_infrastructure: Allow role to manage Node's infrastructure.
        can_upload_data: Allow role to upload data.
    Returns:
        resp: JSON structure containing a log message.
    """
    # Map User Key
    user_key = SigningKey(current_user.private_key.encode(), encoder=HexEncoder)

    # Build Syft Message
    msg = CreateRoleMessage(
        address=domain.address,
        name=name,
        can_triage_requests=can_triage_requests,
        can_edit_settings=can_edit_settings,
        can_create_users=can_create_users,
        can_create_groups=can_create_groups,
        can_edit_roles=can_edit_roles,
        can_manage_infrastructure=can_manage_infrastructure,
        can_upload_data=can_upload_data,
        reply_to=domain.address,
    ).sign(signing_key=user_key)

    # Process syft message
    reply = domain.recv_immediate_msg_with_reply(msg=msg).message

    # Handle Response types
    resp = {}
    if isinstance(reply, ExceptionMessage):
        resp = {"error": reply.exception_msg}
    else:
        resp = {"message": reply.resp_msg}

    return resp


@router.get("", status_code=200, response_class=JSONResponse)
def get_all_roles_route(
    current_user: Any = Depends(deps.get_current_user),
):
    """Retrieves all registered roles

    Args:
        current_user : Current session.
    Returns:
        resp: JSON structure containing registered roles.
    """
    # Map User Key
    user_key = SigningKey(current_user.private_key.encode(), encoder=HexEncoder)

    # Build Syft Message
    msg = GetRolesMessage(address=domain.address, reply_to=domain.address).sign(
        signing_key=user_key
    )

    # Process syft message
    reply = domain.recv_immediate_msg_with_reply(msg=msg).message

    # Handle Response types
    resp = {}
    if isinstance(reply, ExceptionMessage):
        resp = {"error": reply.exception_msg}
    else:
        resp = [role.upcast() for role in reply.content]

    return resp


@router.get("/{role_id}", status_code=200, response_class=JSONResponse)
def get_specific_role_route(
    role_id: int,
    current_user: Any = Depends(deps.get_current_user),
):
    """Retrieves role by its ID.

    Args:
        current_user : Current session.
        role_id: Target role id.
    Returns:
        resp: JSON structure containing target role.
    """

    # Map User Key
    user_key = SigningKey(current_user.private_key.encode(), encoder=HexEncoder)

    # Build Syft Message
    msg = GetRoleMessage(
        address=domain.address, role_id=role_id, reply_to=domain.address
    ).sign(signing_key=user_key)

    # Process syft message
    reply = domain.recv_immediate_msg_with_reply(msg=msg).message

    # Handle Response types
    resp = {}
    if isinstance(reply, ExceptionMessage):
        resp = {"error": reply.exception_msg}
    else:
        resp = reply.content.upcast()

    return resp


@router.put("/{role_id}", status_code=200, response_class=JSONResponse)
def update_use_route(
    role_id: int,
    current_user: Any = Depends(deps.get_current_user),
    name: str = Body(..., example="Researcher"),
    can_triage_requests: bool = Body(..., example="false"),
    can_edit_settings: bool = Body(..., example="false"),
    can_create_users: bool = Body(..., example="false"),
    can_create_groups: bool = Body(..., example="false"),
    can_edit_roles: bool = Body(..., example="false"),
    can_manage_infrastructure: bool = Body(..., example="false"),
    can_upload_data: bool = Body(..., example="false"),
):
    """Changes role attributes

    Args:
        current_user : Current session.
        role_id: Target role id.
        name: New role name.
        can_triage_requests: Update triage requests policy.
        can_edit_settings: Update edit settings policy.
        can_create_users: Update create users policy.
        can_create_groups: Update create groups policy.
        can_edit_roles: Update edit roles policy.
        can_manage_infrastructure: Update Node's infrastructure management policy.
        can_upload_data: Update upload data policy.
    Returns:
        resp: JSON structure containing a log message.
    """
    # Map User Key
    user_key = SigningKey(current_user.private_key.encode(), encoder=HexEncoder)

    # Build Syft Message
    msg = UpdateRoleMessage(
        address=domain.address,
        role_id=role_id,
        name=name,
        can_triage_requests=can_triage_requests,
        can_edit_settings=can_edit_settings,
        can_create_users=can_create_users,
        can_create_groups=can_create_groups,
        can_edit_roles=can_edit_roles,
        can_manage_infrastructure=can_manage_infrastructure,
        can_upload_data=can_upload_data,
        reply_to=domain.address,
    ).sign(signing_key=user_key)

    # Process syft message
    reply = domain.recv_immediate_msg_with_reply(msg=msg).message

    # Handle Response types
    resp = {}
    if isinstance(reply, ExceptionMessage):
        resp = {"error": reply.exception_msg}
    else:
        resp = {"message": reply.resp_msg}

    return resp


@router.delete("/{role_id}", status_code=200, response_class=JSONResponse)
def delete_user_role(
    role_id: int,
    current_user: Any = Depends(deps.get_current_user),
):
    """Deletes a user

    Args:
        role_id: Target role_id.
        current_user : Current session.
    Returns:
        resp: JSON structure containing a log message
    """
    # Map User Key
    user_key = SigningKey(current_user.private_key.encode(), encoder=HexEncoder)

    # Build Syft Message
    msg = DeleteRoleMessage(
        address=domain.address, role_id=role_id, reply_to=domain.address
    ).sign(signing_key=user_key)

    # Process syft message
    reply = domain.recv_immediate_msg_with_reply(msg=msg).message

    # Handle Response types
    resp = {}
    if isinstance(reply, ExceptionMessage):
        resp = {"error": reply.exception_msg}
    else:
        resp = {"message": reply.resp_msg}

    return resp
