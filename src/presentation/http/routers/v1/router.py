from __future__ import annotations

from fastapi import APIRouter, Depends

from presentation.http.auth import current_user
from presentation.http.routers.v1.ad_catalog import router as ad_catalog_router
from presentation.http.routers.v1.auth import router as auth_router
from presentation.http.routers.v1.cities import router as cities_router
from presentation.http.routers.v1.assignments import router as assignments_router
from presentation.http.routers.v1.geozones import router as geozones_router
from presentation.http.routers.v1.pipeline_runs import router as pipeline_runs_router
from presentation.http.routers.v1.users import router as users_router

# Вход требуется на всё сразу, а не на отдельные ручки. Раньше приложение было
# открыто, а паролем отгораживалась только правка справочников; теперь личность
# нужна везде, потому что от неё зависит и содержимое ответа (скрытые записи), и
# запись автора в историю.
#
# Список — белый по построению: закрыто всё, что подключено ниже, а исключение
# ровно одно и объявлено явно. Обратный порядок — «закрываем перечисленное» —
# означал бы, что новая ручка по умолчанию открыта, и однажды её забудут закрыть.
_authenticated = APIRouter(dependencies=[Depends(current_user)])
_authenticated.include_router(pipeline_runs_router)
_authenticated.include_router(cities_router)
_authenticated.include_router(assignments_router)
_authenticated.include_router(geozones_router)
_authenticated.include_router(ad_catalog_router)
_authenticated.include_router(users_router)

api_v1_router = APIRouter()
# Единственное исключение: сам вход. Требовать сессию от ручек, которые её
# выдают и рассказывают, как её получить, — замкнутый круг.
api_v1_router.include_router(auth_router)
api_v1_router.include_router(_authenticated)
