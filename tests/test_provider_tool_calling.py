"""Tool-calling loop de los providers (spec 023). No pega a ninguna API real — se
monkeypatchea el método de creación del SDK con respuestas fake con la misma forma
(duck-typed vía SimpleNamespace) que el objeto real devuelto por Anthropic/OpenAI."""

from types import SimpleNamespace

from maestro_qa.providers.anthropic_provider import AnthropicProvider
from maestro_qa.providers.openai_compat_provider import OpenAICompatProvider

_TOOLS = [
    {
        "name": "read_file",
        "description": "Lee un archivo",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    }
]


def _text_block(text):
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(id_, name, input_):
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=input_)


def test_anthropic_executes_tool_call_then_returns_final_text(monkeypatch):
    provider = AnthropicProvider(model="claude-sonnet-5", api_key="fake-key")
    responses = [
        SimpleNamespace(
            stop_reason="tool_use",
            content=[_tool_use_block("call-1", "read_file", {"path": "src/login.jsx"})],
        ),
        SimpleNamespace(stop_reason="end_turn", content=[_text_block("listo")]),
    ]
    calls = []

    def fake_create(**kwargs):
        calls.append(kwargs)
        return responses.pop(0)

    monkeypatch.setattr(provider._client.messages, "create", fake_create)

    executed = []

    def executor(name, args):
        executed.append((name, args))
        return "contenido del archivo"

    result = provider.complete(
        system="sos un agente", messages=[{"role": "user", "content": "hola"}], tools=_TOOLS, tool_executor=executor
    )

    assert result == "listo"
    assert executed == [("read_file", {"path": "src/login.jsx"})]
    assert len(calls) == 2
    assert calls[0]["tools"][0]["name"] == "read_file"


def test_anthropic_without_tools_behaves_like_before(monkeypatch):
    provider = AnthropicProvider(model="claude-sonnet-5", api_key="fake-key")
    monkeypatch.setattr(
        provider._client.messages,
        "create",
        lambda **kwargs: SimpleNamespace(stop_reason="end_turn", content=[_text_block("ok")]),
    )

    result = provider.complete(system="sos un agente", messages=[{"role": "user", "content": "hola"}])

    assert result == "ok"


def test_anthropic_stops_after_max_iterations_instead_of_hanging(monkeypatch):
    provider = AnthropicProvider(model="claude-sonnet-5", api_key="fake-key")
    call_count = 0

    def always_tool_use(**kwargs):
        nonlocal call_count
        call_count += 1
        return SimpleNamespace(
            stop_reason="tool_use", content=[_tool_use_block(f"call-{call_count}", "read_file", {"path": "x"})]
        )

    monkeypatch.setattr(provider._client.messages, "create", always_tool_use)

    result = provider.complete(
        system="sos un agente",
        messages=[{"role": "user", "content": "hola"}],
        tools=_TOOLS,
        tool_executor=lambda name, args: "contenido",
    )

    assert result == ""  # último bloque de tool_use no tiene texto, y se cortó por el tope
    assert call_count == 8


def _openai_message(content=None, tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls)


def _openai_tool_call(id_, name, arguments):
    return SimpleNamespace(id=id_, function=SimpleNamespace(name=name, arguments=arguments))


def test_openai_compat_executes_tool_call_then_returns_final_text(monkeypatch):
    provider = OpenAICompatProvider(model="deepseek-chat", api_key="fake-key")
    responses = [
        _openai_message(tool_calls=[_openai_tool_call("call-1", "read_file", '{"path": "src/login.jsx"}')]),
        _openai_message(content="listo"),
    ]
    calls = []

    def fake_create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=responses.pop(0))])

    monkeypatch.setattr(provider._client.chat.completions, "create", fake_create)

    executed = []

    def executor(name, args):
        executed.append((name, args))
        return "contenido del archivo"

    result = provider.complete(
        system="sos un agente", messages=[{"role": "user", "content": "hola"}], tools=_TOOLS, tool_executor=executor
    )

    assert result == "listo"
    assert executed == [("read_file", {"path": "src/login.jsx"})]
    assert len(calls) == 2
    assert calls[0]["tools"][0]["function"]["name"] == "read_file"


def test_openai_compat_without_tools_behaves_like_before(monkeypatch):
    provider = OpenAICompatProvider(model="deepseek-chat", api_key="fake-key")
    monkeypatch.setattr(
        provider._client.chat.completions,
        "create",
        lambda **kwargs: SimpleNamespace(choices=[SimpleNamespace(message=_openai_message(content="ok"))]),
    )

    result = provider.complete(system="sos un agente", messages=[{"role": "user", "content": "hola"}])

    assert result == "ok"
