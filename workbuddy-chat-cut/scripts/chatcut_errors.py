"""Preserve remote errors intact while exposing bounded field-level diagnostics."""
import json
import re


def pointer(parts):
    return "/" + "/".join(str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def field_issues(raw):
    found, seen = [], set()
    decoder = json.JSONDecoder()

    def visit(value, depth=0):
        if depth > 12 or len(found) >= 30:
            return
        if isinstance(value, dict):
            path = value.get("path")
            message = value.get("message")
            if isinstance(path, list) and isinstance(message, str):
                item = {"path": pointer(path), "message": message[:1000], "rule": value.get("code")}
                key = (item["path"], item["message"])
                if key not in seen:
                    seen.add(key)
                    found.append(item)
            for child in value.values():
                visit(child, depth + 1)
        elif isinstance(value, list):
            for child in value:
                visit(child, depth + 1)
        elif isinstance(value, str):
            # Some servers embed Zod issues after a long non-JSON prefix.
            end = -1
            for match in re.finditer(r"[\[{]", value):
                if match.start() < end:
                    continue
                try:
                    parsed, length = decoder.raw_decode(value[match.start():])
                except ValueError:
                    continue
                end = match.start() + length
                visit(parsed, depth + 1)

    visit(raw)
    return found


class RemoteToolError(RuntimeError):
    def __init__(self, raw, summary):
        self.raw = raw
        self.issues = field_issues(raw)
        super().__init__(summary)
