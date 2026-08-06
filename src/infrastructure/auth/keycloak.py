"""Обмен кода на токен и проверка подписи токена по JWKS."""

from __future__ import annotations

from urllib.parse import urlencode

import httpx
import jwt
from jwt import PyJWKClient

from application.exceptions import AuthenticationError
from domain.auth import IdentityClaims, claims_from
from settings.auth import AuthSettings

# Столько ждём Keycloak. Обмен кода — единственный синхронный поход наружу на
# пути входа, и повиснуть на нём насмерть хуже, чем честно не пустить.
_TIMEOUT_SECONDS = 10.0

# Допуск на расхождение часов между Keycloak и backend. Без него токен, выданный
# секунду назад машиной, которая на пару секунд впереди, отвергается как «ещё не
# действительный», и вход ломается необъяснимо и через раз.
_CLOCK_SKEW_SECONDS = 30


class KeycloakIdentityProvider:
    """Authorization Code без PKCE: клиент конфиденциальный, секрет на backend.

    PKCE защищает от перехвата кода там, где секрет держать негде, — в SPA и
    мобильных приложениях. Здесь код прилетает на backend, обменивается с
    секретом и в браузер не попадает вовсе, так что PKCE ничего не добавил бы.

    Токен проверяется **по подписи**, а не просто декодируется. Разница
    принципиальная: JWT — это base64, его содержимое читает и подделывает кто
    угодно, и «распарсить токен» без проверки подписи означает пускать в систему
    любого, кто умеет собрать словарь с нужным `sub` и списком групп.
    """

    def __init__(self, settings: AuthSettings) -> None:
        self._settings = settings
        self._jwks: PyJWKClient | None = None

    def _jwks_client(self) -> PyJWKClient:
        """Клиент JWKS создаётся при первом обращении, а не в конструкторе.

        `PyJWKClient` проверяет адрес прямо в `__init__` и падает на пустой
        схеме. В парольном режиме (`AUTH_USE_KEYCLOAK=false`) `issuer` пуст,
        адрес получается вида `/protocol/openid-connect/certs` — и создание
        провайдера роняло любой запрос к `/auth/*`, хотя сам Keycloak в этом
        режиме не нужен вовсе.

        Провайдер при этом собирается всегда: он висит зависимостью на
        `get_auth_service`, а тот — на всех ручках входа. Разводить две сборки
        под два режима значило бы плодить состояния; дешевле не трогать то, чем
        не пользуются.

        Ключи кэшируются внутри клиента: JWKS меняется при ротации ключей realm,
        то есть примерно никогда, а ходить за ним на каждый вход — лишний поход в
        сеть на критическом пути. Сам клиент живёт столько же, сколько провайдер,
        то есть до перезапуска процесса.
        """
        if self._jwks is None:
            self._jwks = PyJWKClient(self._settings.jwks_uri, cache_keys=True)
        return self._jwks

    def authorization_url(self, *, state: str) -> str:
        query = urlencode(
            {
                "client_id": self._settings.client_id,
                "response_type": "code",
                "scope": "openid profile email",
                "redirect_uri": self._settings.redirect_uri,
                "state": state,
            }
        )
        return f"{self._settings.authorization_endpoint}?{query}"

    def claims_for_code(self, *, code: str) -> IdentityClaims:
        access_token = self._exchange(code)
        payload = self._verify(access_token)
        try:
            return claims_from(payload)
        except ValueError as error:
            raise AuthenticationError(str(error)) from error

    def _exchange(self, code: str) -> str:
        try:
            response = httpx.post(
                self._settings.token_endpoint,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self._settings.redirect_uri,
                    "client_id": self._settings.client_id,
                    "client_secret": self._settings.client_secret,
                },
                timeout=_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as error:
            raise AuthenticationError(f"Keycloak недоступен: {error}") from error
        if response.status_code != 200:
            # Тело ответа Keycloak сюда не тащим: там бывает и секрет клиента, а
            # эта строка уезжает в лог.
            raise AuthenticationError(
                f"Keycloak отклонил код авторизации (HTTP {response.status_code})."
            )
        token = response.json().get("access_token")
        if not isinstance(token, str) or not token:
            raise AuthenticationError("Keycloak не вернул access-токен.")
        return token

    def _verify(self, token: str) -> dict:
        """Подпись, издатель, аудитория и срок. Все четыре — обязательны.

        Подпись здесь главное. JWT — это base64: его содержимое читает и
        подделывает кто угодно, и «разобрать токен» без сверки подписи означает
        пускать любого, кто умеет собрать словарь с нужным `sub` и списком групп.

        `audience` проверяется, чтобы токен, выданный для соседнего приложения
        того же realm, не открывал наше: без этой проверки любой клиент IC-GROUP
        стал бы пропуском сюда.
        """
        try:
            key = self._jwks_client().get_signing_key_from_jwt(token).key
            return jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                issuer=self._settings.issuer,
                audience=self._settings.client_id,
                leeway=_CLOCK_SKEW_SECONDS,
                options={"require": ["exp", "iss", "sub"]},
            )
        except jwt.PyJWTError as error:
            raise AuthenticationError(f"Токен не прошёл проверку: {error}") from error


__all__ = ["KeycloakIdentityProvider"]
