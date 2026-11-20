import pytest
from pydantic import ValidationError

from backend.app.config import Settings


def test_defaults_are_safe_for_demo():
    s = Settings()
    assert s.demo_mode is True
    assert s.llm_provider == "auto"
    assert s.max_iterations > 0
    assert s.llm_api_key is None


def test_limits_must_be_positive():
    with pytest.raises(ValidationError):
        Settings(max_iterations=0)


def test_env_file_is_not_read(monkeypatch, tmp_path):
    # Garante que a configuracao nao le ficheiros .env (regra do projecto).
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("MAX_ITERATIONS=99\n", encoding="utf-8")
    assert Settings().max_iterations == 12
