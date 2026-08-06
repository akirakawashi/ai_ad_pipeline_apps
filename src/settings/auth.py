from __future__ import annotations

from pydantic import Field

from settings.base import SettingsModel


class AuthSettings(SettingsModel):
    """Доменный вход через корпоративный Keycloak.

    Keycloak один и только продовый — `IC-GROUP` на `https://ssoc.ic-group.ru`,
    откуда он ходит в Active Directory через LDAP federation. Копии для
    разработки нет и не будет, поэтому настоящий вход проверяется только на
    развёрнутом сервисе, а до тех пор работает заглушка (`use_keycloak=False`).

    Backend не видит и не должен видеть, откуда Keycloak взял человека: ему
    приезжают claim'ы токена, а из домена они или из внутренней базы Keycloak —
    в токен не попадает.
    """

    issuer: str
    client_id: str
    client_secret: str
    redirect_uri: str
    frontend_url: str

    # Группы, дающие право на админ-панель, полным путём. Белый список: в токене
    # приезжает вся оргструктура — отделы, рассылки, доступы к шарам, — и
    # осмысленных для приложения групп там единицы.
    #
    # В конфигурации, а не в базе: иначе первому админу взяться неоткуда.
    # Справочник пуст, пока никто не вошёл, а войти админом нельзя, пока в
    # справочнике нет админа.
    admin_groups: frozenset[str] = Field(default_factory=frozenset)

    # Разведочный дамп claim'ов: состав групп в IC-GROUP пока не известен, и
    # настроить `admin_groups` вслепую нельзя. Пусто — дамп выключен.
    claims_dump_path: str | None = None

    # Переключатель способа входа, и он один на всё:
    #
    #   True  — доменный вход через корпоративный Keycloak;
    #   False — заглушка `admin`/`admin` и `user`/`user`, Keycloak не участвует.
    #
    # Заглушка нужна, потому что Keycloak в компании только продовый: копии для
    # разработки нет, и до развёртывания настоящий вход проверить негде.
    #
    # Комбинаций нет намеренно. Разводить «включено и то, и это» значит заводить
    # состояния, которые никто не держит в голове; один переключатель читается
    # с первого взгляда и в `.env`, и в коде.
    use_keycloak: bool = False

    @property
    def configured(self) -> bool:
        """Реквизиты Keycloak заполнены целиком.

        Все три обязательны: без `issuer` некуда идти, без `client_id` Keycloak
        не поймёт, кто спрашивает, без секрета не отдаст токен. Проверять по
        одному только адресу значило бы стартовать с конфигурацией, которая
        сломается на первом же входе.
        """
        return bool(self.issuer and self.client_id and self.client_secret)

    @property
    def authorization_endpoint(self) -> str:
        return f"{self.issuer}/protocol/openid-connect/auth"

    @property
    def token_endpoint(self) -> str:
        return f"{self.issuer}/protocol/openid-connect/token"

    @property
    def jwks_uri(self) -> str:
        return f"{self.issuer}/protocol/openid-connect/certs"


def warn_if_unusable(settings: AuthSettings) -> str | None:
    """Проверка конфигурации входа. Возвращает причину непригодности или None.

    Раньше здесь было исключение, роняющее запуск. Заменено сознательно: сервис,
    который не поднимается, — это отказ всего, включая то, что к авторизации
    отношения не имеет, и чинить его приходится вслепую по логу. Приложение
    поднимается, healthcheck отвечает, а вход честно сообщает, что не настроен.

    Чего здесь намеренно НЕТ — отката на вход по паролю. Соблазн понятный:
    реквизитов нет, так пустим по `admin`/`admin`, чтобы люди работали. Но это
    ровно тот случай, когда неудачная настройка молча открывает дверь, и никто
    об этом не узнает. Не настроено — значит не пускаем никого.
    """
    if settings.use_keycloak and not settings.configured:
        return (
            "AUTH_USE_KEYCLOAK=true, но AUTH_OIDC_ISSUER, AUTH_OIDC_CLIENT_ID "
            "или AUTH_OIDC_CLIENT_SECRET не заполнены: войти будет нельзя. "
            "Заполните их либо поставьте AUTH_USE_KEYCLOAK=false для входа по "
            "логину и паролю."
        )
    return None


def build_auth_settings(
    *,
    oidc_issuer: str,
    oidc_client_id: str,
    oidc_client_secret: str,
    redirect_uri: str,
    frontend_url: str,
    admin_groups: str,
    claims_dump_path: str | None,
    use_keycloak: bool,
) -> AuthSettings:
    return AuthSettings(
        # Хвостовой слэш в issuer ломает сравнение с `iss` токена и склеивает
        # двойной слэш в путях эндпоинтов. Снимаем один раз здесь.
        issuer=oidc_issuer.rstrip("/"),
        client_id=oidc_client_id,
        client_secret=oidc_client_secret,
        redirect_uri=redirect_uri,
        frontend_url=frontend_url.rstrip("/"),
        admin_groups=parse_group_list(admin_groups),
        claims_dump_path=claims_dump_path or None,
        use_keycloak=use_keycloak,
    )


def parse_group_list(raw: str) -> frozenset[str]:
    """Разбор списка групп из переменной окружения.

    Пустые куски отбрасываются: `"/A,,/B,"` — это две группы, а не четыре, и
    пустая строка в белом списке совпала бы с отсутствующей группой.

    Регистр и пробелы не трогаем. В AD имя группы — точная строка, часто с
    кириллицей и пробелами внутри (`/Рассылки/Все сотрудники`); «умная»
    нормализация здесь означала бы, что права выдаются не тем, кому выписаны.
    """
    return frozenset(part.strip() for part in raw.split(",") if part.strip())
