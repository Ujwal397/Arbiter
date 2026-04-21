import json
from typing import Any, Optional, Callable

# Mock the constants LiteLLM expects
OPT_INDENT_2 = 1
OPT_APPEND_NEWLINE = 2
OPT_NON_STR_KEYS = 4
OPT_SERIALIZE_DATETIME = 8

def dumps(obj: Any, default: Optional[Callable[[Any], Any]] = None, option: int = 0) -> bytes:
    """Mock orjson.dumps using standard json"""
    indent = 2 if option & OPT_INDENT_2 else None
    res = json.dumps(obj, default=default, indent=indent)
    if option & OPT_APPEND_NEWLINE:
        res += "\n"
    return res.encode('utf-8')

def loads(s: str | bytes) -> Any:
    """Mock orjson.loads using standard json"""
    return json.loads(s)

class JSONDecodeError(json.JSONDecodeError):
    pass
