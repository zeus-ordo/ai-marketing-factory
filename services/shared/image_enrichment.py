import base64
import json
import math
import re
from typing import Any

_FORBIDDEN_FIELD_PARTS = ("private", "storage", "path", "base64", "binary", "bytes", "blob")
_PATH_VALUE = re.compile(r"^(?:[a-zA-Z]:[\\/]|[\\/]|file:|private:|storage:)")
_RELATIVE_PATH_VALUE = re.compile(r"^(?:\.\.?[\\/])")
_BASE64_VALUE = re.compile(r"^[A-Za-z0-9+/]+={0,2}$")


def _validate_json_value(value: Any, field_name: str, depth: int) -> None:
    if depth > 8:
        raise ValueError("image attributes are too deeply nested")
    normalized_name = re.sub(r"[^a-z0-9]", "", field_name.casefold())
    if any(part in normalized_name for part in _FORBIDDEN_FIELD_PARTS):
        raise ValueError("image attributes cannot contain private, storage, path, base64, or binary fields")
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("image attributes must contain finite JSON numbers")
        return
    if isinstance(value, str):
        if len(value) > 4096:
            raise ValueError("image attribute strings are too long")
        if _PATH_VALUE.match(value) or _RELATIVE_PATH_VALUE.match(value) or value.startswith("data:") and ";base64," in value.casefold():
            raise ValueError("image attributes cannot contain private paths or base64 data")
        if _BASE64_VALUE.fullmatch(value) and ("=" in value or len(value) >= 64 or len(value) == 4 and value.isupper()):
            try:
                decoded = base64.b64decode(value, validate=True)
            except ValueError:
                pass
            else:
                if b"\x00" in decoded or len(value) >= 64:
                    raise ValueError("image attributes cannot contain base64 data")
        return
    if isinstance(value, dict):
        if len(value) > 64:
            raise ValueError("image attribute objects contain too many fields")
        for key, child in value.items():
            if not isinstance(key, str):
                raise TypeError("image attribute object keys must be strings")
            _validate_json_value(child, key, depth + 1)
        return
    if isinstance(value, list):
        if len(value) > 64:
            raise ValueError("image attribute lists contain too many values")
        for child in value:
            _validate_json_value(child, field_name, depth + 1)
        return
    raise TypeError(f"image attributes contain unsupported value type: {type(value).__name__}")


def validate_safe_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(attributes, dict):
        raise TypeError("image attributes must be an object")
    _validate_json_value(attributes, "attributes", 0)
    if len(json.dumps(attributes, ensure_ascii=True, allow_nan=False)) > 32768:
        raise ValueError("image attributes exceed the maximum size")
    return attributes
