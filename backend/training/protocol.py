import json
from math import isfinite

SOURCE_LIMIT = 8_000
MEMORY_LIMIT = 16 * 1024
REQUEST_LIMIT = 256 * 1024
RESPONSE_LIMIT = 24 * 1024


def error(code: str, message: str, line: int | None = None) -> dict:
    return {"error": {"code": code, "message": message, "line": line}}


def json_memory(value, depth=0):
    if depth > 64:
        raise ValueError
    kind = type(value)
    if value is None or kind in (bool, int, str):
        return
    if kind is float and isfinite(value):
        return
    if kind is list:
        for item in value:
            json_memory(item, depth + 1)
        return
    if kind is dict and all(type(key) is str for key in value):
        for item in value.values():
            json_memory(item, depth + 1)
        return
    raise ValueError


def encode(value) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode()


def validate_result(result, allowed):
    if type(result) is not dict or result.keys() != {"direction", "memory"}:
        return error("result", "Возвращайте словарь с ключами direction и memory.")
    if type(result["direction"]) is not str or result["direction"] not in allowed:
        return error(
            "direction",
            "Направление должно входить в state['self']['allowed_directions'].",
        )
    try:
        json_memory(result["memory"])
        if len(encode(result["memory"])) > MEMORY_LIMIT:
            raise ValueError
    except (ValueError, RecursionError, MemoryError):
        return error("memory", "Память должна быть JSON-значением размером до 16 КиБ.")
    return result
