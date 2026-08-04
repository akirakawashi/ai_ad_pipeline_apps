from __future__ import annotations

from application.common.dto import (
    CityRefDTO,
    RouteRefDTO,
    RunAssignmentRefDTO,
    UserDTO,
)
from infrastructure.database.models import Assignment, City, PipelineRun, Route, User


def user_ref(user: User | None) -> UserDTO | None:
    if user is None:
        return None
    return UserDTO(
        id=user.users_id,
        full_name=user.full_name,
        is_active=user.is_active,
        created_at=user.created_at,
    )


def assignment_title(assignment: Assignment) -> str:
    """Единственное место, где выводится отображаемое имя задания."""
    if assignment.title:
        return assignment.title
    if assignment.created_at is None:
        return f"Задание №{assignment.sequence_number}"
    return f"Задание №{assignment.sequence_number} · {assignment.created_at:%d.%m.%Y}"


def city_ref(city: City) -> CityRefDTO:
    return CityRefDTO(id=city.cities_id, slug=city.slug, name=city.name)


def route_ref(route: Route) -> RouteRefDTO:
    return RouteRefDTO(
        id=route.routes_id,
        slug=route.slug,
        name=route.name,
        color_hex=route.color_hex,
    )


def assignment_ref(run: PipelineRun) -> RunAssignmentRefDTO | None:
    """Ссылка на задание для карточки видео. None — связь не загружена.

    Требует, чтобы связь assignment → route → city была загружена заранее:
    зовётся только при _run_to_dto(with_refs=True). Задание у съёмки есть
    всегда, поэтому None здесь — про запрос, а не про данные.
    """
    assignment = run.assignment
    if assignment is None or assignment.route is None or assignment.route.city is None:
        return None
    return RunAssignmentRefDTO(
        assignment_id=assignment.assignments_id,
        sequence_number=assignment.sequence_number,
        title=assignment_title(assignment),
        route=route_ref(assignment.route),
        city=city_ref(assignment.route.city),
    )
