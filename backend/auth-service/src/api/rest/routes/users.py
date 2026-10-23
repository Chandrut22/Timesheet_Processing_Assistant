import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Query,
    Response,
    UploadFile,
    status,
)

from src.api.rest.dependencies import Admin, SessionDep
from src.constants.roles import RoleName
from src.core.services.importing.service import import_users, template_csv
from src.core.services.user_notifications import send_welcome_email
from src.core.services.user_service import UserService
from src.schemas.importing import ImportReport, OnDuplicate, OnError
from src.schemas.user import (
    BulkUserResult,
    BulkUserStatus,
    PasswordReset,
    UserCreate,
    UserPage,
    UserRead,
    UserUpdate,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=UserPage)
async def list_users(
    session: SessionDep,
    _: Admin,
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
    _: Admin,
    background_tasks: BackgroundTasks,
) -> UserRead:
    user = await UserService(session).create(body)
    # Runs after the response is sent; the user is already saved either way.
    background_tasks.add_task(
        send_welcome_email,
        to=user.email,
        name=user.name,
        password=body.password,
        role=user.role.name,
    )
    return UserRead.from_user(user)


@router.get(
    "/import/template",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}, "description": "Import template"}},
    summary="CSV template for importing users",
)
async def import_template(_: Admin) -> Response:
    return Response(
        content=template_csv(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="users-import-template.csv"'
        },
    )


@router.post("/import", summary="Import users from a CSV or XLSX file")
async def import_file(
    session: SessionDep,
    actor: Admin,
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File(description="A .csv or .xlsx file (first sheet)")],
    dry_run: Annotated[
        bool, Query(description="true: check only, write nothing")
    ] = True,
    on_error: Annotated[
        OnError, Query(description="abort: nothing is written if any row fails")
    ] = "abort",
    on_duplicate: Annotated[
        OnDuplicate,
        Query(description="error or skip (update is not allowed for users)"),
    ] = "error",
) -> ImportReport:
    """Admins only. Each new user gets the welcome email with their password, sent
    after the import is committed (never for a dry run)."""
    report, welcomes = await import_users(
        session,
        file,
        actor=actor,
        dry_run=dry_run,
        on_error=on_error,
        on_duplicate=on_duplicate,
    )
    for w in welcomes:
        background_tasks.add_task(
            send_welcome_email,
            to=w.email,
            name=w.name,
            password=w.password,
            role=w.role,
        )
    return report


# Declared before "/{user_id}" so "bulk" is never read as an id.
@router.post("/bulk/status", response_model=BulkUserResult)
async def bulk_user_status(
    body: BulkUserStatus, session: SessionDep, actor: Admin
) -> BulkUserResult:
    """Activate or deactivate up to 100 users (admins only). You cannot deactivate
    yourself, and the last active admin always stays; those are listed as failed and
    the rest still go through. A deactivated user can no longer sign in or refresh."""
    return await UserService(session).bulk_status(body.ids, body.is_active, actor)


@router.get("/{user_id}", response_model=UserRead)
async def get_user(user_id: uuid.UUID, session: SessionDep, _: Admin) -> UserRead:
    return UserRead.from_user(await UserService(session).get(user_id))


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: uuid.UUID, body: UserUpdate, session: SessionDep, actor: Admin
) -> UserRead:
    return UserRead.from_user(await UserService(session).update(user_id, body, actor))


@router.put("/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    user_id: uuid.UUID, body: PasswordReset, session: SessionDep, _: Admin
) -> None:
    await UserService(session).reset_password(user_id, body.new_password)
