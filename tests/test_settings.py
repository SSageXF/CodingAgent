from __future__ import annotations

import pytest

from evidencecoder.settings import Settings


CONFIG_NAMES = (
    "EVIDENCECODER_MODEL",
    "EVIDENCECODER_BASE_URL",
    "EVIDENCECODER_API_KEY",
    "OPENAI_API_KEY",
    "EVIDENCECODER_MAX_CYCLES",
    "EVIDENCECODER_WALL_TIME",
)


def clear_configuration(monkeypatch) -> None:
    for name in CONFIG_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_settings_load_dotenv_with_quotes_comments_and_limits(tmp_path, monkeypatch):
    clear_configuration(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# local configuration\n"
        'EVIDENCECODER_MODEL="模型-name"\n'
        "EVIDENCECODER_BASE_URL=https://gateway.test/v1  # comment\n"
        "EVIDENCECODER_API_KEY='secret-value'\n"
        "EVIDENCECODER_MAX_CYCLES=44\n"
        "EVIDENCECODER_WALL_TIME=900\n",
        encoding="utf-8",
    )

    settings = Settings.from_env(tmp_path, env_file=env_file)
    assert settings.model == "模型-name"
    assert settings.base_url == "https://gateway.test/v1"
    assert settings.api_key == "secret-value"
    assert settings.max_cycles == 44
    assert settings.wall_time_seconds == 900


def test_cli_override_then_environment_then_dotenv_priority(tmp_path, monkeypatch):
    clear_configuration(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "EVIDENCECODER_MODEL=from-file\nEVIDENCECODER_API_KEY=file-key\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("EVIDENCECODER_MODEL", "from-environment")
    monkeypatch.setenv("EVIDENCECODER_API_KEY", "environment-key")

    environment_settings = Settings.from_env(tmp_path, env_file=env_file)
    explicit_settings = Settings.from_env(tmp_path, env_file=env_file, model="from-cli")
    assert environment_settings.model == "from-environment"
    assert environment_settings.api_key == "environment-key"
    assert explicit_settings.model == "from-cli"


def test_invalid_dotenv_fails_without_echoing_secret(tmp_path, monkeypatch):
    clear_configuration(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text("INVALID LINE secret-value\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"invalid \.env syntax at line 1") as captured:
        Settings.from_env(tmp_path, env_file=env_file)
    assert "secret-value" not in str(captured.value)
