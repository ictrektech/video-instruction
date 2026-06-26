from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.db.session import get_session
from app.schemas.common.response import ResponseDTO
from app.schemas.user import AddUserCommand, CurrentUser, LoginCommand, LoginDTO, UserDTO
from app.services import user_service

router = APIRouter()


@router.post("/login", response_model=ResponseDTO[LoginDTO])
async def login(
    command: LoginCommand, session: AsyncSession = Depends(get_session)
) -> ResponseDTO[LoginDTO]:
    dto = await user_service.login(session, command)
    return ResponseDTO.ok(dto)


@router.post("/add", response_model=ResponseDTO[UserDTO])
async def add_user(
    command: AddUserCommand, session: AsyncSession = Depends(get_session)
) -> ResponseDTO[UserDTO]:
    dto = await user_service.add_user(session, command)
    return ResponseDTO.ok(dto)


@router.get("/", response_model=ResponseDTO[UserDTO])
async def get_user(
    current_user: CurrentUser = Depends(get_current_user),
) -> ResponseDTO[UserDTO]:
    return ResponseDTO.ok(UserDTO(id=current_user.id, username=current_user.username))
