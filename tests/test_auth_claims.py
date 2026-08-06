"""Разбор токена и маппинг групп: чистая логика, без базы и без Keycloak.

Здесь проверяется единственное решение, которое приложение принимает само:
какие права следуют из групп, приехавших в токене. Всё остальное во входе —
редиректы, обмен кода, подпись — делает Keycloak и библиотека, и тесты на них
были бы тестами чужого кода.

Набор написан против конкретной ловушки: **в токене приезжает вся оргструктура
компании**, а не роли приложения. Отделы, рассылки, доступы к сетевым шарам,
забытое легаси — десятки строк, из которых осмысленных для нас единицы.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from domain.auth import (
    Permission,
    claims_from,
    expires_at_from,
    full_name_from,
    groups_from,
    permissions_for,
)
from settings.auth import (
    AuthSettings,
    AuthSetupError,
    build_auth_settings,
    validate_auth_setup,
)

ADMINS = frozenset({"/AI-AD-Admins"})

# Похоже на то, что отдаёт Keycloak поверх LDAP-federation: полные пути, лишние
# группы, кириллица и пробелы в именах.
REAL_GROUPS = (
    "/Departments/Marketing",
    "/Рассылки/Все сотрудники",
    "/Общие ресурсы/Файловый архив",
)


def _payload(**overrides) -> dict:
    base = {
        "sub": "f81d4fae-7dec-11d0-a765-00a0c91e6bf6",
        "preferred_username": "i.obychny",
        "given_name": "Иван",
        "family_name": "Обычный",
        "email": "i.obychny@example.test",
        "groups": list(REAL_GROUPS),
        "exp": 1_800_000_000,
    }
    base.update(overrides)
    return base


# --- маппинг групп -----------------------------------------------------------


def test_extra_groups_grant_nothing():
    """Отделы и рассылки — оргструктура, а не роли. Прав они не дают."""
    assert permissions_for(REAL_GROUPS, admin_groups=ADMINS) == frozenset()


def test_listed_group_grants_admin():
    groups = (*REAL_GROUPS, "/AI-AD-Admins")
    assert permissions_for(groups, admin_groups=ADMINS) == frozenset({Permission.ADMIN})


def test_empty_whitelist_grants_nothing_to_anyone():
    """Незаполненный `AUTH_ADMIN_GROUPS` не должен раздавать права всем подряд.

    Ошибиться здесь легко: пустое множество пересекается с чем угодно в пустоту,
    но стоит написать проверку наоборот — и ненастроенный стенд станет открытым.
    """
    assert permissions_for(("/AI-AD-Admins",), admin_groups=frozenset()) == frozenset()


@pytest.mark.parametrize(
    "group",
    [
        "AI-AD-Admins",
        "/ai-ad-admins",
        "/AI-AD-Admins/Sub",
        "/Departments/AI-AD-Admins",
        " /AI-AD-Admins",
    ],
    ids=[
        "без ведущего слэша",
        "другой регистр",
        "вложенная группа",
        "тот же лист в другой ветке",
        "с пробелом",
    ],
)
def test_similar_group_names_do_not_grant_admin(group: str):
    """Совпадение — точное, и только оно.

    Keycloak отдаёт группу полным путём, а в русском AD рядом живут `Маркетинг` и
    `Маркетинг (архив)`. Сравнение по префиксу или без регистра выдало бы права
    владельцу похоже названной группы — то есть человеку, которому их не
    выписывали.
    """
    assert permissions_for((group,), admin_groups=ADMINS) == frozenset()


def test_cyrillic_group_matches_exactly():
    """Кириллица и пробелы в имени — норма для русского AD, а не крайний случай."""
    admins = frozenset({"/Отделы/Администраторы АИ"})
    assert permissions_for(
        ("/Отделы/Администраторы АИ",), admin_groups=admins
    ) == frozenset({Permission.ADMIN})


# --- разбор claim'ов ---------------------------------------------------------


def test_full_name_prefers_given_and_family():
    """`name` собирается по шаблону realm и приезжает то так, то этак.

    В русских инсталляциях он бывает и «Иван Обычный», и «Обычный Иван», и
    пустым. Справочник людей показывается рядом с записями, заведёнными руками, —
    разнобой там виден сразу, поэтому имя собирается из отдельных полей.
    """
    assert full_name_from(_payload(name="Обычный Иван")) == "Иван Обычный"


def test_full_name_falls_back_to_name_then_login():
    assert full_name_from({"name": "Пётр Петров"}) == "Пётр Петров"
    assert full_name_from({"preferred_username": "p.petrov"}) == "p.petrov"


def test_person_without_a_name_cannot_be_created_silently():
    """Пустое ФИО в справочнике — это пустая строка в выпадашке «Кто загрузил»."""
    with pytest.raises(ValueError):
        claims_from({"sub": "x", "exp": 1_800_000_000})


def test_token_without_subject_is_rejected():
    """`sub` — единственная связь с человеком. Без него запись не к чему привязать."""
    with pytest.raises(ValueError):
        claims_from(_payload(sub=""))


@pytest.mark.parametrize(
    "groups",
    [None, "not-a-list", [1, 2, 3], ["", None, "/Departments/IT"]],
    ids=["claim отсутствует", "не список", "не строки", "мусор вперемешку"],
)
def test_broken_groups_claim_does_not_break_the_login(groups):
    """Неожиданный `groups` не должен мешать человеку работать.

    Состав claim'ов в IC-GROUP пока не проверен. Падение здесь означало бы, что
    люди не могут войти, пока кто-то не поправит маппер в Keycloak. Прав тут не
    выдают — их считает белый список, — так что пропустить лишнее безопасно, а не
    пустить человека нельзя.
    """
    parsed = groups_from({"groups": groups})
    assert all(isinstance(item, str) and item for item in parsed)


def test_expiry_comes_from_the_token():
    """Срок сессии не назначается свой: она не должна пережить свой пропуск."""
    moment = expires_at_from({"exp": 1_800_000_000})
    assert moment == datetime.fromtimestamp(1_800_000_000, tz=timezone.utc)


def test_token_without_expiry_is_rejected():
    with pytest.raises(ValueError):
        expires_at_from({})


def test_claims_carry_the_raw_payload_for_the_dump():
    """Сырой payload нужен разведочному дампу — увидеть, что реально приезжает."""
    claims = claims_from(_payload())
    assert claims.raw["preferred_username"] == "i.obychny"
    assert claims.groups == REAL_GROUPS
    assert claims.full_name == "Иван Обычный"


# --- переключатель способа входа ---------------------------------------------


def _settings(issuer: str, *, use_keycloak: bool) -> AuthSettings:
    return build_auth_settings(
        oidc_issuer=issuer,
        oidc_client_id="ai-ad" if issuer else "",
        oidc_client_secret="secret" if issuer else "",
        redirect_uri="http://localhost:8000/api/v1/auth/callback",
        frontend_url="http://localhost:5173",
        admin_groups="/AI-AD-Admins",
        claims_dump_path=None,
        use_keycloak=use_keycloak,
    )


def test_keycloak_mode_without_credentials_refuses_to_start():
    """Иначе сервис поднимется, покажет «Войти» и отправит человека в никуда.

    Разбираться пришлось бы уже на развёрнутом стенде, поэтому падаем при
    запуске: логи читают, когда что-то случилось, а несостоявшийся старт
    замечают за минуту.
    """
    with pytest.raises(AuthSetupError):
        validate_auth_setup(_settings("", use_keycloak=True))


@pytest.mark.parametrize(
    ("issuer", "client_id", "secret"),
    [
        ("https://ssoc.ic-group.ru/realms/IC-GROUP", "", "s"),
        ("https://ssoc.ic-group.ru/realms/IC-GROUP", "ai-ad", ""),
    ],
    ids=["без client_id", "без секрета"],
)
def test_partial_credentials_refuse_to_start(issuer: str, client_id: str, secret: str):
    """Обязательны все три, а не только адрес.

    Без `client_id` Keycloak не поймёт, кто спрашивает; без секрета не отдаст
    токен. Проверка по одному адресу пропустила бы конфигурацию, которая
    сломается на первом же входе.
    """
    settings = build_auth_settings(
        oidc_issuer=issuer,
        oidc_client_id=client_id,
        oidc_client_secret=secret,
        redirect_uri="r",
        frontend_url="f",
        admin_groups="/A",
        claims_dump_path=None,
        use_keycloak=True,
    )
    with pytest.raises(AuthSetupError):
        validate_auth_setup(settings)


def test_password_mode_needs_nothing():
    """Заглушке настраивать нечего, и это её главное свойство: работает всегда."""
    validate_auth_setup(_settings("", use_keycloak=False))


def test_keycloak_mode_with_full_credentials_starts():
    validate_auth_setup(
        _settings("https://ssoc.ic-group.ru/realms/IC-GROUP", use_keycloak=True)
    )
