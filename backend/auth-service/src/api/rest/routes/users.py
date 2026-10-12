import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query, status

from src.api.rest.dependencies import (
    SessionDep,
    SuperAdmin,
    UserCreator,
    UserDirectoryReader,
)
from src.constants.roles import RoleName
from src.core.services.user_notifications import send_welcome_email
from src.core.services.user_service import UserService
from src.schemas.user import PasswordReset, UserCreate, UserPage, UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=UserPage)
async def list_users(
    session: SessionDep,
    _: UserDirectoryReader,  # super admin or admin
    role: RoleName | None = None,
    is_active: bool | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> UserPage:
    users, total = await UserService(session).list(
        role=role, is_active=is_active, q=q, page=page, size=size
    )
    return UserPage(
        items=[UserRead.from_user(u) for u in users], total=total, page=page, size=size
    )


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    session: SessionDep,
    actor: UserCreator,  # super admin or admin (admins: reviewer/viewer only)
    background_tasks: BackgroundTasks,
) -> UserRead:
    user = await UserService(session).create(body, actor)
    # Runs after the response is sent; the user is already saved either way.
    background_tasks.add_task(
        send_welcome_email,
        to=user.email,
        name=user.name,
        password=body.password,
        role=user.role.name,
    )
    return UserRead.from_user(user)


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: uuid.UUID, session: SessionDep, _: UserDirectoryReader
) -> UserRead:
    return UserRead.from_user(await UserService(session).get(user_id))


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: uuid.UUID, body: UserUpdate, session: SessionDep, actor: SuperAdmin
) -> UserRead:
    return UserRead.from_user(await UserService(session).update(user_id, body, actor))


@router.put("/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    user_id: uuid.UUID, body: PasswordReset, session: SessionDep, _: SuperAdmin
) -> None:
    await UserService(session).reset_password(user_id, body.new_password)
