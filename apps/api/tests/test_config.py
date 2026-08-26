from pytest import MonkeyPatch

from app.core.config import Settings


def test_settings_parse_cors_origins_from_json_environment(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("API_CORS_ORIGINS", '["https://support.example.com"]')

    settings = Settings()

    assert settings.api_cors_origins == ["https://support.example.com"]
