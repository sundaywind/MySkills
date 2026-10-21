"""Reusable input assembly. No operation-specific parameter schema is stored here."""
import copy
from pathlib import Path
from chatcut_client import AccessError, loads, dumps, read_json


def assign(document, path, value, seen):
    """Use top-level names or RFC6901 pointers, e.g. /adds/0/startFrame."""
    parts = [p.replace("~1", "/").replace("~0", "~") for p in path[1:].split("/")] if path.startswith("/") else [path]
    if not path or any(p == "" for p in parts):
        raise AccessError("invalid_field", "字段名不能为空")
    key = tuple(parts)
    if any(key[:len(prev)] == prev or prev[:len(key)] == key for prev in seen):
        raise AccessError("conflicting_field", f"重复或相互覆盖的输入字段：{path}")
    seen.add(key)
    node = document
    for index, part in enumerate(parts):
        last = index == len(parts) - 1
        if isinstance(node, list):
            if not part.isdecimal() or int(part) > 10000:
                raise AccessError("invalid_field", f"数组下标无效：{path}")
            offset = int(part)
            if offset > len(node):
                raise AccessError("invalid_field", f"数组不能跳过元素：{path}")
            if offset == len(node):
                node.append(None if last else ([] if parts[index + 1].isdecimal() else {}))
            if last:
                node[offset] = value
                return
            node = node[offset]
        elif isinstance(node, dict):
            if last:
                node[part] = value
                return
            if part not in node:
                node[part] = [] if parts[index + 1].isdecimal() else {}
            node = node[part]
        else:
            raise AccessError("invalid_field", f"无法在标量内部设置字段：{path}")


def build_arguments(params=None, *, sets=(), texts=(), files=(), json_files=(), json_strings=()):
    document = copy.deepcopy(read_json(params)) if params else {}
    if not isinstance(document, dict):
        raise AccessError("invalid_arguments", "参数文件的顶层必须是 JSON 对象")
    seen = set()
    for entries, mode in [(sets, "json"), (texts, "text"), (files, "file"),
                          (json_files, "json_file"), (json_strings, "json_string")]:
        for entry in entries:
            if "=" not in entry:
                raise AccessError("invalid_field", f"需要 FIELD=VALUE：{entry}")
            key, value = entry.split("=", 1)
            if mode == "json":
                value = loads(value)
            elif mode == "file":
                value = Path(value).expanduser().read_text(encoding="utf-8")
            elif mode in {"json_file", "json_string"}:
                value = read_json(Path(value).expanduser())
                if mode == "json_string":
                    value = dumps(value)
            assign(document, key, value, seen)
    return document

