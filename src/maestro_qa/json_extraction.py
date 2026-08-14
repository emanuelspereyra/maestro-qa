import json


def extract_json(text: str, kind: type) -> str:
    """Extrae el primer valor JSON válido de tipo `kind` (dict u list) del texto.

    Usa json.JSONDecoder.raw_decode probando cada candidato de apertura hasta que uno
    parsea como JSON completo — a diferencia de un regex greedy (\\{.*\\}), esto no se
    confunde si hay otra llave/corchete en prosa antes o después del JSON real (una nota
    al final del LLM, un ejemplo inline, etc.). Ver specs/022-endurecimiento-agentes.md.
    """
    opener = "{" if kind is dict else "["
    label = "objeto" if kind is dict else "array"
    decoder = json.JSONDecoder()

    start = 0
    while True:
        start = text.find(opener, start)
        if start == -1:
            raise ValueError(f"La respuesta del LLM no contiene un {label} JSON válido")
        try:
            _, end = decoder.raw_decode(text, start)
            return text[start:end]
        except json.JSONDecodeError:
            start += 1
