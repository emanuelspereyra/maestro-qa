import json

import pytest

from maestro_qa.json_extraction import extract_json


def test_extracts_clean_object():
    text = '{"a": 1, "b": 2}'
    assert json.loads(extract_json(text, dict)) == {"a": 1, "b": 2}


def test_extracts_clean_array():
    text = '[{"a": 1}]'
    assert json.loads(extract_json(text, list)) == [{"a": 1}]


def test_extracts_object_wrapped_in_markdown_fence():
    text = '```json\n{"a": 1}\n```'
    assert json.loads(extract_json(text, dict)) == {"a": 1}


def test_ignores_trailing_prose_with_extra_braces():
    # bug real: un regex greedy (\{.*\}) captura hasta la ÚLTIMA llave del texto,
    # mezclando esta nota final adentro del JSON y rompiendo json.loads.
    text = '{"a": 1}\n\nOjo: el campo `{b}` todavía no está confirmado.'
    assert json.loads(extract_json(text, dict)) == {"a": 1}


def test_ignores_leading_prose_with_braces():
    text = 'Como referencia, el formato es `{ejemplo}`. Acá está: {"a": 1}'
    assert json.loads(extract_json(text, dict)) == {"a": 1}


def test_skips_invalid_inline_brace_and_finds_real_json_later():
    text = 'Ejemplo de campo: {no_es_json_valido sin comillas} y despues: {"a": 1}'
    assert json.loads(extract_json(text, dict)) == {"a": 1}


def test_no_json_at_all_raises_clear_error():
    with pytest.raises(ValueError, match="no contiene un objeto JSON"):
        extract_json("Lo siento, no puedo generar eso.", dict)


def test_object_requested_but_only_array_present_raises_clear_error():
    # sin ninguna "[" en el texto, no hay array que extraer — falla claro, no en silencio
    with pytest.raises(ValueError, match="no contiene un array JSON"):
        extract_json('{"a": 1}', list)


def test_truncated_json_raises_clear_error():
    with pytest.raises(ValueError, match="no contiene un objeto JSON"):
        extract_json('{"a": 1, "b": [1, 2,', dict)


def test_two_separate_objects_extracts_only_the_first():
    text = '{"a": 1} {"b": 2}'
    assert json.loads(extract_json(text, dict)) == {"a": 1}
