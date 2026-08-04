from __future__ import annotations

from fastapi import APIRouter, Depends, Path

from application.services.user_service import UserService
from presentation.http.dependencies import get_user_service
from presentation.http.security import allow_hidden, require_admin
from presentation.http.dto.response import (
    CreateUserRequest,
    OkResponse,
    UpdateUserRequest,
    UserResponse,
)

router = APIRouter(prefix="/users", tags=["Users"])

# Справочник людей заводится только в админ-панели: и создание, и правка под
# паролем. Раньше человека можно было создать прямо из выпадашки «Кто загрузил»,
# и справочник копил близнецов — «Иванов», «Иванов А.», «иванов», — потому что
# заводил его тот, кто в этот момент грузил видео, а не тот, кто отвечает за
# справочник. Открытым осталось только чтение: выпадашки выбирают из готового.


@router.get("", response_model=OkResponse[list[UserResponse]])
def list_users(
    include_inactive: bool = Depends(allow_hidden),
    service: UserService = Depends(get_user_service),
) -> OkResponse[list[UserResponse]]:
    result = service.list_users(include_inactive=include_inactive)
    return OkResponse(data=[UserResponse.model_validate(user) for user in result])


@router.post(
    "",
    response_model=OkResponse[UserResponse],
    status_code=201,
    dependencies=[Depends(require_admin)],
)
def create_user(
    payload: CreateUserRequest,
    service: UserService = Depends(get_user_service),
) -> OkResponse[UserResponse]:
    result = service.create_user(full_name=payload.full_name)
    return OkResponse(data=UserResponse.model_validate(result))


@router.patch(
    "/{user_id}",
    response_model=OkResponse[UserResponse],
    dependencies=[Depends(require_admin)],
)
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
