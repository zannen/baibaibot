import urllib.parse
from typing import Union


def encode(val: dict) -> str:
    return "&".join(
        _encode_inner(innerkey, innerval)
        for innerkey, innerval in val.items()
        if innerval is not None
    )


def _encode_inner(
    key: str,
    val: Union[bool, dict, float, int, list, str],
) -> str:
    if isinstance(val, bool):
        return f"{key}={str(val).lower()}"
    if isinstance(val, float):
        return f"{key}={val}"
    if isinstance(val, int):
        return f"{key}={val}"
    if isinstance(val, str):
        return f"{key}={urllib.parse.quote(val)}"
    if isinstance(val, list):
        return "&".join(
            _encode_inner(f"{key}[{i}]", val[i]) for i in range(len(val))
        )
    if isinstance(val, dict):
        return "&".join(
            _encode_inner(f"{key}[{innerkey}]", innerval)
            for innerkey, innerval in val.items()
        )
    raise Exception(f"Unhandled data type: key={key} val={val} ({type(val)})")
