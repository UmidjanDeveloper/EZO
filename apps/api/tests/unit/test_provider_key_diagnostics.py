"""A rejected or wrongly shaped AI key is named as such, never as a generic failure."""

from ezo_api.providers.errors import ProviderErrorKind, kind_from_error
from ezo_api.providers.registry import key_warnings
from ezo_api.settings import Settings


def test_a_bad_key_answered_with_400_is_an_auth_failure() -> None:
    gemini = (
        "400 INVALID_ARGUMENT. {'error': {'message': "
        "'API key not valid. Please pass a valid API key.'}}"
    )
    assert kind_from_error(400, gemini) == ProviderErrorKind.AUTH
    assert kind_from_error(401, "Incorrect API key provided: key_****") == ProviderErrorKind.AUTH
    assert kind_from_error(400, "invalid x-api-key") == ProviderErrorKind.AUTH
    # Everything else still follows the status code.
    assert (
        kind_from_error(400, "Request contains an invalid argument.")
        == ProviderErrorKind.BAD_REQUEST
    )
    assert kind_from_error(429, "Resource exhausted") == ProviderErrorKind.RATE_LIMIT
    assert kind_from_error(None, "") == ProviderErrorKind.UNKNOWN


_ALIASES = {
    "gemini_api_key": "GEMINI_API_KEY",
    "openai_api_key": "OPENAI_API_KEY",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
}


def _settings(base_url: str | None = None, **keys: str) -> Settings:
    values = {_ALIASES[name]: value for name, value in keys.items()}
    for name in _ALIASES.values():
        values.setdefault(name, "")
    if base_url:
        values["OPENAI_BASE_URL"] = base_url
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def test_key_shapes_are_checked_by_prefix_only() -> None:
    good = _settings(
        gemini_api_key="AIza" + "x" * 35,
        openai_api_key="sk-proj-abc",
        anthropic_api_key="sk-ant-abc",
    )
    assert key_warnings(good) == {}
    wrong = _settings(gemini_api_key="AQ.Ab8RN6something", openai_api_key="key_yB5cIQX")
    assert key_warnings(wrong) == {
        "gemini": "unexpected_key_format",
        "openai": "unexpected_key_format",
    }


def test_an_openai_compatible_service_keeps_its_own_key_format() -> None:
    settings = _settings(base_url="https://openrouter.ai/api/v1", openai_api_key="or-v1-abc")
    assert key_warnings(settings) == {}
