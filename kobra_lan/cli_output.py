"""One presentation boundary; renderers never access devices or private storage."""
import json
import re
import unicodedata

QUALIFICATION = "Qualified: Kobra X model 20030 / firmware 2.0.2.2; print start remains experimental."


def safe_text(value):
    """Remove terminal controls and credential-bearing strings from display data."""
    value = re.sub(r"[a-zA-Z][a-zA-Z0-9+.-]*://[^\s\"<>]+", "[redacted URL]", value)
    value = re.sub(r"-----BEGIN .*?-----.*", "[redacted credential]", value, flags=re.S)
    return "".join(c if not unicodedata.category(c).startswith("C") else " " for c in value)


def safe_result(value):
    if isinstance(value, dict):
        return {safe_text(str(k)): safe_result(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe_result(v) for v in value]
    if isinstance(value, str):
        return safe_text(value)
    return value


def text_lines(value, depth=0):
    prefix = "  " * depth
    if isinstance(value, dict):
        yield from mapping_lines(value, depth)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, (dict, list)):
                yield from text_lines(item, depth)
            else:
                yield prefix + "- " + scalar(item)
    else:
        yield prefix + scalar(value)


def mapping_lines(value, depth):
    prefix = "  " * depth
    for key, item in value.items():
        label = key.replace("_", " ").capitalize()
        if key == "default" and item is None:
            yield prefix + label + ": none"
        elif isinstance(item, (dict, list)) and item:
            yield prefix + label + ":"
            yield from text_lines(item, depth + 1)
        else:
            yield prefix + label + ": " + scalar(item)


def scalar(value):
    if value is None:
        return "unknown"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if value == [] or value == {}:
        return "none"
    return str(value)


def emit(json_mode, result=None, *, code=None, message=None):
    envelope = {"schema_version": 1, "ok": code is None}
    if code is not None:
        envelope["error"] = {"code": code, "message": safe_text(message)}
    if result is not None:
        envelope["result"] = safe_result(result)
        envelope["result"]["qualification"] = QUALIFICATION
    if json_mode:
        print(json.dumps(envelope, ensure_ascii=True))
    else:
        if code is not None:
            print("Error (" + code + "): " + envelope["error"]["message"])
        if result is not None:
            print("\n".join(text_lines(envelope["result"])))
        if result is None:
            print(QUALIFICATION)
