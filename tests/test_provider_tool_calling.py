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


def test_anthropic_forces_final_text_when_iteration_cap_is_reached(monkeypatch):
    # bug real (auditoría 2026-08-14): antes del fix, la última llamada seguía ofreciendo
    # tools, y si el modelo insistía en pedir tool_use el resultado final era "" — se
    # perdía todo lo explorado/escrito. El fix corta las tools en la última iteración
    # para forzar una respuesta de texto.
    provider = AnthropicProvider(model="claude-sonnet-5", api_key="fake-key")
    call_count = 0

    def fake_create(**kwargs):
        nonlocal call_count
        call_count += 1
        if "tools" in kwargs:
            return SimpleNamespace(
                stop_reason="tool_use", content=[_tool_use_block(f"call-{call_count}", "read_file", {"path": "x"})]
            )
        return SimpleNamespace(stop_reason="end_turn", content=[_text_block("resumen final sin más tools")])

    monkeypatch.setattr(provider._client.messages, "create", fake_create)

    result = provider.complete(
        system="sos un agente",
        messages=[{"role": "user", "content": "hola"}],
        tools=_TOOLS,
        tool_executor=lambda name, args: "contenido",
    )

    assert result == "resumen final sin más tools"
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


def test_openai_compat_forces_final_text_when_iteration_cap_is_reached(monkeypatch):
    # mismo bug/fix que Anthropic (auditoría 2026-08-14), verificado también acá porque
    # los dos providers implementan el loop por separado.
    provider = OpenAICompatProvider(model="deepseek-chat", api_key="fake-key")
    call_count = 0

    def fake_create(**kwargs):
        nonlocal call_count
        call_count += 1
        if "tools" in kwargs:
            message = _openai_message(
                tool_calls=[_openai_tool_call(f"call-{call_count}", "read_file", '{"path": "x"}')]
            )
        else:
            message = _openai_message(content="resumen final sin más tools")
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    monkeypatch.setattr(provider._client.chat.completions, "create", fake_create)

    result = provider.complete(
        system="sos un agente",
        messages=[{"role": "user", "content": "hola"}],
        tools=_TOOLS,
        tool_executor=lambda name, args: "contenido",
    )

    assert result == "resumen final sin más tools"
    assert call_count == 8


def test_openai_compat_handles_malformed_tool_call_arguments_without_crashing(monkeypatch):
    # bug real (auditoría 2026-08-14): json.loads(fn.arguments) corría sin try/except —
    # un modelo real (sobre todo modelos locales/abiertos) que devuelva argumentos
    # truncados/mal formados crasheaba complete() entero en vez de reportar el error a
    # la tool y seguir el loop.
    provider = OpenAICompatProvider(model="deepseek-chat", api_key="fake-key")
    responses = [
        _openai_message(tool_calls=[_openai_tool_call("call-1", "read_file", '{"path": "src/login.jsx"')]),  # roto
        _openai_message(content="listo"),
    ]

    def fake_create(**kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(message=responses.pop(0))])

    monkeypatch.setattr(provider._client.chat.completions, "create", fake_create)

    executed = []
    result = provider.complete(
        system="sos un agente",
        messages=[{"role": "user", "content": "hola"}],
        tools=_TOOLS,
        tool_executor=lambda name, args: executed.append((name, args)) or "contenido",
    )

    assert result == "listo"
    assert executed == []  # el tool_executor nunca se llamó con argumentos rotos
