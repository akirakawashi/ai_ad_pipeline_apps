from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query

from application.services.user_service import UserService
from presentation.http.dependencies import get_user_service
from presentation.http.dto.response import (
    CreateUserRequest,
    OkResponse,
    UpdateUserRequest,
    UserResponse,
)

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=OkResponse[list[UserResponse]])
def list_users(
    include_inactive: bool = Query(
        default=False,
        description="Показывать людей, выведенных из справочника",
    ),
    service: UserService = Depends(get_user_service),
) -> OkResponse[list[UserResponse]]:
    result = service.list_users(include_inactive=include_inactive)
    return OkResponse(data=[UserResponse.model_validate(user) for user in result])


@router.post("", response_model=OkResponse[UserResponse], status_code=201)
def create_user(
    payload: CreateUserRequest,
    service: UserService = Depends(get_user_service),
) -> OkResponse[UserResponse]:
    result = service.create_user(full_name=payload.full_name)
    return OkResponse(data=UserResponse.model_validate(result))


@router.patch("/{user_id}", response_model=OkResponse[UserResponse])
def update_user(
    payload: UpdateUserRequest,
    user_id: str = Path(description="Идентификатор человека в справочнике"),
    service: UserService = Depends(get_user_service),
) -> OkResponse[UserResponse]:
    result = service.update_user(
        user_id,
        full_name=payload.full_name,
        is_active=payload.is_active,
    )
    return OkResponse(data=UserResponse.model_validate(result))
