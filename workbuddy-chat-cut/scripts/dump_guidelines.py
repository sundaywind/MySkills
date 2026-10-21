#!/usr/bin/env python3
"""Dump current ChatCut Desktop MCP guidelines to readable files.

Use when the host cannot conveniently display a large get_guidelines result.
This authorized local helper opens a separate session and saves current definitions;
it does not bypass host permissions and never submits editing operations.

Usage:
  python3 dump_guidelines.py <out_dir>                  # guidelines.txt + operations.json + operations.md
  python3 dump_guidelines.py <out_dir> --list           # ...and print all operation names
  python3 dump_guidelines.py <out_dir> --op edit_item   # print one op's description + schema (markdown)
  python3 dump_guidelines.py <out_dir> --grep caption   # print ops whose name/description matches

Outputs in <out_dir>:
  guidelines.txt   raw text as returned by get_guidelines
  operations.json  parsed JSON  {instruction, operations:[{name, description, inputSchema}]}
  operations.md    compact markdown, one section per op, schema flattened to bullets

Notes:
  - Requires ChatCut Desktop to be running. The session sees the project currently
    open in Desktop, but this script only reads guidelines; it never runs execute.
  - Keep the latest snapshot for --compare; use an isolated temporary directory.
"""
import json
import argparse
import hashlib
from datetime import datetime, timezone
from pathlib import Path
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chatcut_stdio import ChatCutStdio  # noqa: E402


def fmt_schema(s, indent=0):
    out = []
    props = s.get("properties", {}) or {}
    req = set(s.get("required", []) or [])
    pad = "  " * indent
    for k, v in props.items():
        if not isinstance(v, dict):
            continue
        t = v.get("type")
        if isinstance(t, list):
            t = "|".join(map(str, t))
        if t is None:
            t = "enum" if "enum" in v else ("oneOf" if ("oneOf" in v or "anyOf" in v) else "any")
        line = f"{pad}- {k}{'*' if k in req else ''}: {t}"
        if "enum" in v:
            line += f" {v['enum']}"
        if "default" in v:
            line += f" (default {json.dumps(v['default'], ensure_ascii=False)})"
        if "minimum" in v or "maximum" in v:
            line += f" [{v.get('minimum', '')}..{v.get('maximum', '')}]"
        if v.get("description"):
            line += f" — {v['description']}"
        out.append(line)
        items = v.get("items")
        if t == "array" and isinstance(items, dict):
            if "enum" in items:
                out.append(f"{pad}  items enum: {items['enum']}")
            elif items.get("properties"):
                out.extend(fmt_schema(items, indent + 1))
            elif items.get("description"):
                out.append(f"{pad}  items: {items.get('type')} — {items['description']}")
        elif t == "object" and v.get("properties"):
            out.extend(fmt_schema(v, indent + 1))
        for alt in (v.get("oneOf") or v.get("anyOf") or []):
            if isinstance(alt, dict) and alt.get("properties"):
                out.extend(fmt_schema(alt, indent + 1))
    if s.get("additionalProperties") is False:
        out.append(f"{pad}(additionalProperties: false)")
    return out


def op_markdown(o):
    body = [f"## {o['name']}", "", o.get("description", "").strip(), "", "### inputSchema"]
    body.extend(fmt_schema(o.get("inputSchema", {}) or {}) or ["(no parameters)"])
    body.extend(["", "### 完整 schema（约束以此为准）", "```json",
                 json.dumps(o.get("inputSchema", {}), ensure_ascii=False, indent=2), "```"])
    return "\n".join(body)


def main():
    parser = argparse.ArgumentParser(description="保存当前通用说明、schema 和版本指纹")
    parser.add_argument("out_dir")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--op")
    parser.add_argument("--grep")
    parser.add_argument("--compare", type=Path)
    parser.add_argument("--timeout", type=float, default=30)
    opts = parser.parse_args()
    out_dir = opts.out_dir
    previous = json.loads((opts.compare / "snapshot.json").read_text()) if opts.compare else None
    os.makedirs(out_dir, exist_ok=True)

    client = ChatCutStdio("dump-guidelines", timeout=opts.timeout)
    try:
        active = client.activate()
        text = client.guidelines_text()
    finally:
        client.close()

    txt_path = os.path.join(out_dir, "guidelines.txt")
    with open(txt_path, "w") as f:
        f.write(text)
    print(f"wrote {txt_path} ({len(text)} chars); active project: {active.get('projectId')}")

    try:
        parsed = json.loads(text)
    except Exception:
        raise ValueError("guidelines 不是 JSON；已保存原文，但未建立可用 schema 快照")

    ops = parsed.get("operations") if isinstance(parsed, dict) else parsed
    if not isinstance(ops, list):
        raise ValueError("找不到 operations 列表，请检查 guidelines.txt")

    instruction = parsed.get("instruction", parsed.get("instructions", "")) if isinstance(parsed, dict) else ""
    instruction_text = instruction if isinstance(instruction, str) else json.dumps(instruction, ensure_ascii=False, indent=2)
    Path(out_dir, "instruction.md").write_text(instruction_text, encoding="utf-8")
    snapshot = make_snapshot(ops, instruction, client.init_result.get("serverInfo", {}))
    Path(out_dir, "snapshot.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    if previous:
        print(json.dumps(compare_snapshots(previous, snapshot), ensure_ascii=False, indent=2))

    json_path = os.path.join(out_dir, "operations.json")
    with open(json_path, "w") as f:
        json.dump(parsed, f, ensure_ascii=False, indent=1)
    md_path = os.path.join(out_dir, "operations.md")
    with open(md_path, "w") as f:
        f.write(f"# ChatCut Desktop MCP operations ({len(ops)})\n\n")
        f.write("\n\n".join(op_markdown(o) for o in ops))
    print(f"wrote {json_path} and {md_path} ({len(ops)} operations)")

    if opts.list:
        for o in ops:
            print("-", o.get("name"))

    if opts.op:
        name = opts.op
        for o in ops:
            if o.get("name") == name:
                print(op_markdown(o))
                break
        else:
            raise ValueError(f"operation {name} not found")

    if opts.grep:
        pat = re.compile(opts.grep, re.I)
        for o in ops:
            if pat.search(o.get("name", "")) or pat.search(o.get("description", "")):
                desc = o.get("description", "").strip().split("\n")[0]
                print(f"- {o['name']}: {desc[:140]}")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def make_snapshot(ops, instruction, server):
    if any(not isinstance(o, dict) or not o.get("name") for o in ops):
        raise ValueError("操作列表包含无效记录")
    return {"capturedAt": datetime.now(timezone.utc).isoformat(), "server": server,
            "instructionHash": digest(instruction),
            "operations": {o["name"]: digest(o) for o in ops}}


def compare_snapshots(old, new):
    a, b = old["operations"], new["operations"]
    return {"serverChanged": old.get("server") != new.get("server"),
            "instructionChanged": old.get("instructionHash") != new.get("instructionHash"),
            "added": sorted(b.keys() - a.keys()), "removed": sorted(a.keys() - b.keys()),
            "changed": sorted(k for k in a.keys() & b.keys() if a[k] != b[k])}


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
