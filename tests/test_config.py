import pytest

from maestro_qa.providers import get_provider
from maestro_qa.providers.anthropic_provider import AnthropicProvider
from maestro_qa.providers.openai_compat_provider import OpenAICompatProvider


@pytest.fixture
def base_env(monkeypatch):
    monkeypatch.setenv("MAESTRO_MODEL", "some-model")
    monkeypatch.setenv("MAESTRO_API_KEY", "sk-test")


def test_anthropic_provider_selected(base_env, monkeypatch):
    monkeypatch.setenv("MAESTRO_PROVIDER", "anthropic")
    assert isinstance(get_provider(), AnthropicProvider)


@pytest.mark.parametrize("name", ["openai", "gemini", "kimi", "qwen", "deepseek"])
def test_openai_compat_provider_selected(base_env, monkeypatch, name):
    monkeypatch.setenv("MAESTRO_PROVIDER", name)
    assert isinstance(get_provider(), OpenAICompatProvider)


def test_unknown_provider_raises(base_env, monkeypatch):
    monkeypatch.setenv("MAESTRO_PROVIDER", "not-a-real-provider")
    with pytest.raises(ValueError):
        get_provider()


def test_switching_provider_needs_no_code_change(base_env, monkeypatch):
    monkeypatch.setenv("MAESTRO_PROVIDER", "anthropic")
    first = get_provider()
    monkeypatch.setenv("MAESTRO_PROVIDER", "deepseek")
    second = get_provider()
    assert type(first) is not type(second)
