"""Права и разбор claim'ов токена. Чистая логика, без I/O и без FastAPI."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class Permission(StrEnum):
    """Что человек может делать в приложении.

    Пока одно право, и это осознанно, а не заготовка впрок: до SSO вся защита
    сводилась к одной паре логин/пароль, и `require_admin` закрывал ровно один
    набор действий — правку городов, маршрутов, заданий, каталога и справочника
    людей. Разбивать этот набор, не зная, кто и на что жалуется, значит
    придумывать роли из головы.

    Дробить придётся, когда станет известно, какие группы реально приезжают из
    IC-GROUP: перечисление на то и перечисление, чтобы новое право добавлялось
    сюда и в маппинг, а не расползалось по проверкам в роутерах.
    """

    ADMIN = "admin"


@dataclass(frozen=True, slots=True)
class IdentityClaims:
    """Человек, каким его описал Keycloak. Ровно то, что пришло в токене.

    Отдельный тип, а не сырой словарь, — граница: дальше по слоям едет разобранная
    личность, и ни один сервис не начинает сам лазить по claim'ам, выбирая, какое
    поле сегодня считать именем.
    """

    subject: str
    username: str
    full_name: str
    email: str | None
    groups: tuple[str, ...]
    expires_at: datetime
    # Сырой payload — только для разведочного дампа. Права по нему не считают.
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


def permissions_for(
    groups: tuple[str, ...] | list[str],
    *,
    admin_groups: frozenset[str],
) -> frozenset[Permission]:
    """Права по группам токена. Белый список: чего нет в маппинге — не право.

    В корпоративном AD человек состоит в десятках групп: отделы, рассылки,
    доступы к сетевым шарам, забытое легаси. Оргструктура — не роли приложения, и
    совпадение имени случайной группы с чем-то осмысленным не должно никого
    повышать. Поэтому пересечение с явным списком, а не разбор входящего.

    Сравнение — точное совпадение строки. Keycloak отдаёт группу полным путём
    (`/Departments/Marketing`), а в русском AD в имени бывают пробелы и кириллица;
    `startswith` или сравнение без регистра выдали бы права владельцу похоже
    названной группы.
    """
    if not admin_groups:
        return frozenset()
    return (
        frozenset({Permission.ADMIN})
        if admin_groups.intersection(groups)
        else frozenset()
    )


def full_name_from(claims: dict[str, Any]) -> str:
    """ФИО для справочника: `given_name` + `family_name`, иначе что найдётся.

    Порядок именно такой. `name` в Keycloak собирается по шаблону realm и в
    русских инсталляциях приезжает то «Иван Обычный», то «Обычный Иван», то
    пустым, — а справочник людей показывается в выпадашках рядом с записями,
    заведёнными руками, и разнобой там виден сразу.

    Последний рубеж — `preferred_username`: человек без заполненных имени и
    фамилии в AD войти всё равно должен, пусть и покажется логином.
    """
    given = str(claims.get("given_name") or "").strip()
    family = str(claims.get("family_name") or "").strip()
    if given or family:
        return " ".join(part for part in (given, family) if part)
    name = str(claims.get("name") or "").strip()
    if name:
        return name
    return str(claims.get("preferred_username") or "").strip()


def groups_from(claims: dict[str, Any]) -> tuple[str, ...]:
    """Группы из claim'а `groups`.

    Мусор отбрасывается молча, а не роняет вход: состав claim'ов в IC-GROUP пока
    не проверен, и падение на неожиданном типе означало бы, что человек не может
    работать, пока кто-то не поправит маппер в Keycloak. Права здесь не выдаются —
    их считает `permissions_for` по белому списку, — так что пропустить лишнее
    безопасно, а не пустить человека нельзя.
    """
    raw = claims.get("groups")
    if not isinstance(raw, list):
        return ()
    return tuple(item for item in raw if isinstance(item, str) and item)


def expires_at_from(claims: dict[str, Any]) -> datetime:
    """`exp` токена как момент времени в UTC.

    Срок сессии приложения берётся отсюда, а не назначается своим: сессия не
    должна переживать пропуск, по которому выдана. В IC-GROUP токен живёт 8 часов
    и не обновляется — то есть один рабочий день на один вход.
    """
    exp = claims.get("exp")
    if not isinstance(exp, (int, float)):
        raise ValueError("В токене нет срока действия (exp).")
    return datetime.fromtimestamp(float(exp), tz=timezone.utc)


def claims_from(payload: dict[str, Any]) -> IdentityClaims:
    """Разобранный токен. Подпись к этому моменту уже проверена — здесь только чтение."""
    subject = str(payload.get("sub") or "").strip()
    if not subject:
        raise ValueError("В токене нет идентификатора пользователя (sub).")
    username = str(payload.get("preferred_username") or "").strip()
    full_name = full_name_from(payload)
    if not full_name:
        # Показывать в справочнике «кто загрузил» пустую строку нельзя, а
        # придумывать имя за AD — тем более.
        raise ValueError("В токене нет ни имени, ни логина пользователя.")
    email = str(payload.get("email") or "").strip() or None
    return IdentityClaims(
        subject=subject,
        username=username or full_name,
        full_name=full_name,
        email=email,
        groups=groups_from(payload),
        expires_at=expires_at_from(payload),
        raw=payload,
    )


__all__ = [
    "IdentityClaims",
    "Permission",
    "claims_from",
    "expires_at_from",
    "full_name_from",
    "groups_from",
    "permissions_for",
]
