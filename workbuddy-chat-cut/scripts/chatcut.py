#!/usr/bin/env python3
"""One ChatCut access CLI: capabilities, describe, draft, prepare, recipes, run, call."""
import argparse
import base64
import importlib.util
import json
from pathlib import Path
import sys
import uuid

from chatcut_client import AccessError, Catalog, Session, read_json, write_json, reconcile
from chatcut_params import build_arguments
from chatcut_errors import RemoteToolError
from chatcut_checks import available_frames, filter_orientation

NAV = Path(__file__).resolve().parent.parent / "references" / "capabilities.json"


def show(value):
    print(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2))


def compact_result(receipt):
    """Full result stays in the private receipt; image bytes never flood model context."""
    data = {k: v for k, v in receipt.items() if k not in {"result", "rawResponse", "rawError", "preflightRaw", "preflight"}}
    if any(k in receipt for k in ("rawError", "preflightRaw")):
        data["fullDiagnostics"] = receipt["receiptPath"]
    result = receipt.get("result", {})
    compact = {k: v for k, v in result.items() if k != "content"}
    content = []
    for index, block in enumerate(result.get("content", [])):
        if block.get("type") == "image" and block.get("data"):
            ext = "jpg" if block.get("mimeType") == "image/jpeg" else "png"
            path = Path(receipt["receiptPath"]).with_name(receipt["requestId"] + f"-{index}.{ext}")
            if not path.exists():
                decoded = base64.b64decode(block["data"], validate=True)
                with path.open("xb") as stream:
                    stream.write(decoded)
            content.append({"type": "image", "path": str(path), "mimeType": block.get("mimeType")})
        elif block.get("type") == "text" and len(block.get("text", "")) > 16000:
            content.append({"type": "text", "text": block["text"][:16000],
                            "truncated": True, "fullResult": receipt["receiptPath"]})
        else:
            content.append(block)
    compact["content"] = content
    data["result"] = compact
    data["meaning"] = "returned 仅表示操作返回；后台生成或导出是否完成需另查。"
    return data


def show_receipt(receipt):
    show(compact_result(receipt))
    if receipt.get("compositionVerification", {}).get("ok") is False:
        raise SystemExit(1)


def overview(catalog, query="", group=None):
    nav = read_json(NAV)
    groups = []
    matched = set()
    for entry in nav["groups"]:
        found = []
        for op in catalog.summary(query):
            if any(token in op["name"] for token in entry["match"]):
                matched.add(op["name"])
                found.append({"name": op["name"], "summary": op["description"][:100],
                              "readOnlyHint": op["readOnlyHint"]})
        if group is None or entry["id"] == group:
            groups.append({"id": entry["id"], "title": entry["title"], "purpose": entry["purpose"],
                           "available": bool(found), "operations": found})
    if group is not None and not any(g["id"] == group for g in nav["groups"]):
        raise AccessError("unknown_group", "未知能力类别", [g["id"] for g in nav["groups"]])
    other = [{"name": o["name"], "summary": o["description"][:100]}
             for o in catalog.summary(query) if o["name"] not in matched]
    return {"operationCount": len(catalog.operations),
            "groups": groups, "other": other if group is None else [],
            "note": "摘要仅供导航；首次任务用 instructions 分页读通用规则，describe 读取所用操作完整定义。类别可交叉。"}


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state-dir", default=".chatcut", help="固定工作目录，保存实时目录和防重复调用记录")
    p.add_argument("--timeout", type=float, default=30)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="本机依赖检查，不连接 ChatCut")
    sub.add_parser("active", help="读取当前项目与实时服务信息")
    q = sub.add_parser("frames", help="离线计算正常速度源素材最大可用帧数")
    q.add_argument("--source-duration", required=True)
    q.add_argument("--fps", required=True)
    q.add_argument("--source-in-us", type=int, default=0)
    q.add_argument("--requested", type=int)
    q = sub.add_parser("filter-orientation", help="按实际返回宽高筛选，不信方向标签")
    q.add_argument("--input", type=Path, required=True)
    q.add_argument("--orientation", choices=("vertical", "horizontal", "square"), required=True)
    q.add_argument("--output", type=Path, required=True)
    q.add_argument("--items-path", default="", help="结果数组的 JSON Pointer；默认输入本身是数组")
    q = sub.add_parser("check-captions", help="只读核对口播来源和音乐字幕污染")
    q.add_argument("--project", required=True)
    q.add_argument("--speech-track", action="append", required=True)
    q.add_argument("--music-track", action="append", default=[])
    q = sub.add_parser("verify-size", help="只读核对活动时间线尺寸；不符则报错")
    q.add_argument("--project", required=True)
    q.add_argument("--timeline", required=True)
    q.add_argument("--width", type=int, required=True)
    q.add_argument("--height", type=int, required=True)
    q = sub.add_parser("ready", help="新建/切换项目后只读检查就绪，不重试写入")
    q.add_argument("--project", required=True)
    q.add_argument("--params", type=Path, help="当前 read_project 所需参数，默认空对象")
    q = sub.add_parser("reconcile", help="只读核查后记录结论；不重发原请求")
    q.add_argument("request_id")
    q.add_argument("--evidence", required=True)
    q.add_argument("--outcome", choices=("applied", "not-applied"), required=True)
    q.add_argument("--note", required=True)
    for command in ("capabilities", "describe", "draft", "instructions"):
        q = sub.add_parser(command)
        q.add_argument("--catalog", type=Path, help="离线读取某次 catalog.json 或 operations.json；不代表实时")
        q.add_argument("--refresh", action="store_true", help="忽略导航缓存，重新读取实时能力")
        if command == "capabilities":
            q.add_argument("--search", default="")
            q.add_argument("--group")
        elif command == "instructions":
            q.add_argument("--offset", type=int, default=0)
            q.add_argument("--limit", type=int, default=3000)
        else:
            q.add_argument("operation")
        if command == "describe":
            q.add_argument("--output", type=Path, help="完整定义保存到文件，只打印索引")
        if command == "draft":
            q.add_argument("--output", type=Path, required=True)
    for command in ("prepare", "call"):
        q = sub.add_parser(command)
        q.add_argument("operation")
        q.add_argument("--project", required=True)
        q.add_argument("--params", type=Path)
        for flag in ("set", "text", "file", "json-file", "json-string"):
            q.add_argument("--" + flag, action="append", default=[])
        if command == "prepare":
            q.add_argument("--output", type=Path, required=True)
        else:
            q.add_argument("--write", action="store_true")
            q.add_argument("--allow-layout-change", action="store_true")
            q.add_argument("--preflight", choices=("auto", "require", "skip"), default="auto")
    q = sub.add_parser("run")
    q.add_argument("plan", type=Path)
    q.add_argument("--write", action="store_true")
    q.add_argument("--allow-layout-change", action="store_true")
    q.add_argument("--preflight", choices=("auto", "require", "skip"), default="auto")
    q = sub.add_parser("receipt", help="读调用结果；不连接 ChatCut")
    q.add_argument("request_id")
    q = sub.add_parser("recipe", help="常见参数封装，只生成经过校验的计划，不立即修改项目")
    q.add_argument("kind", choices=("import", "place", "place-media", "transcribe", "hide-music-captions", "update-item", "motion", "update-code", "set-size", "delete-item", "delete-attached"))
    q.add_argument("--project", required=True)
    q.add_argument("--output", type=Path, required=True)
    q.add_argument("--path", action="append")
    q.add_argument("--name")
    q.add_argument("--asset")
    q.add_argument("--track")
    q.add_argument("--type")
    q.add_argument("--start", type=int)
    q.add_argument("--duration", type=int)
    q.add_argument("--properties", type=Path)
    q.add_argument("--item")
    q.add_argument("--fields", type=Path)
    q.add_argument("--code", type=Path)
    q.add_argument("--metadata", type=Path)
    q.add_argument("--timeline")
    q.add_argument("--width", type=int)
    q.add_argument("--height", type=int)
    q.add_argument("--source-duration")
    q.add_argument("--fps")
    q.add_argument("--source-in-us", type=int, default=0)
    q.add_argument("--role", choices=("speech", "music"))
    q.add_argument("--speech-track", action="append")
    q.add_argument("--music-track")
    q.add_argument("--caption-track")
    return p


def recipe(session, opts):
    def need(*keys):
        missing = [key for key in keys if getattr(opts, key) is None]
        if missing:
            raise AccessError("missing_recipe_fields", "缺少常用方法参数", missing)
    if opts.kind == "import":
        need("path")
        return session.import_files(opts.path, project_id=opts.project, name=opts.name)
    if opts.kind == "transcribe":
        need("asset", "role")
        return session.transcribe_speech(project_id=opts.project, asset_id=opts.asset, role=opts.role)
    if opts.kind == "hide-music-captions":
        need("caption_track", "music_track", "speech_track")
        return session.hide_music_captions(project_id=opts.project, caption_track=opts.caption_track,
                                          music_source=opts.music_track, speech_sources=opts.speech_track)
    if opts.kind == "place-media":
        need("asset", "track", "type", "start", "duration", "source_duration", "fps")
        return session.place_media(project_id=opts.project, asset_id=opts.asset, track_id=opts.track,
                kind=opts.type, start_frame=opts.start, duration_frames=opts.duration,
                source_duration=opts.source_duration, fps=opts.fps, source_in_us=opts.source_in_us)
    if opts.kind == "set-size":
        need("timeline", "width", "height")
        return session.set_size(project_id=opts.project, timeline_id=opts.timeline, width=opts.width, height=opts.height)
    if opts.kind in {"delete-item", "delete-attached"}:
        need("item")
        if opts.kind == "delete-attached":
            need("type")
        elif opts.type is not None:
            raise AccessError("invalid_arguments", "delete-item 不接收 --type；删效果/转场请用 delete-attached")
        return session.delete_item(project_id=opts.project, item_id=opts.item,
                                   attached_type=opts.type if opts.kind == "delete-attached" else None)
    if opts.kind == "place":
        need("asset", "track", "type", "start", "duration")
        return session.place(project_id=opts.project, asset_id=opts.asset, track_id=opts.track,
                             kind=opts.type, start_frame=opts.start, duration_frames=opts.duration,
                             properties=read_json(opts.properties) if opts.properties else None)
    if opts.kind == "update-item":
        need("item", "fields")
        return session.update_item(project_id=opts.project, item_id=opts.item, fields=read_json(opts.fields))
    if opts.kind == "motion":
        need("code", "metadata")
        return session.motion_graphic(project_id=opts.project, code_file=opts.code,
                                      metadata=read_json(opts.metadata))
    need("asset", "code")
    return session.update_asset_code(project_id=opts.project, asset_id=opts.asset, code_file=opts.code,
                                     properties=read_json(opts.properties) if opts.properties else None)


def save_plan(path, plan):
    write_json(path, plan, exclusive=True)
    return {"ok": True, "prepared": True, "executed": False, "plan": str(path.resolve()),
            "requestId": plan["requestId"], "projectId": plan["projectId"], "operation": plan["name"],
            "argumentKeys": sorted(plan["arguments"])}


def main():
    opts = parser().parse_args()
    if opts.command == "active":
        from chatcut_stdio import ChatCutStdio
        client = ChatCutStdio("chatcut-access", timeout=opts.timeout)
        try:
            show({"project": client.activate(), "server": client.init_result.get("serverInfo", {}),
                  "guidelinesFetched": False})
        finally:
            client.close()
        return
    if opts.command == "frames":
        result = available_frames(opts.source_duration, opts.fps, opts.source_in_us, opts.requested)
        show(result)
        if not result["ok"]:
            raise SystemExit(1)
        return
    if opts.command == "filter-orientation":
        data = read_json(opts.input)
        if opts.items_path:
            if not opts.items_path.startswith("/"):
                raise AccessError("invalid_field", "items-path 必须是 JSON Pointer")
            try:
                for part in opts.items_path[1:].split("/"):
                    part = part.replace("~1", "/").replace("~0", "~")
                    data = data[int(part)] if isinstance(data, list) else data[part]
            except (KeyError, IndexError, ValueError, TypeError) as exc:
                raise AccessError("invalid_field", "结果数组路径不存在；不猜返回结构") from exc
        result = filter_orientation(data, opts.orientation)
        write_json(opts.output, result, exclusive=True)
        show({"ok": result["ok"], "acceptedCount": len(result["accepted"]),
              "rejectedCount": len(result["rejected"]), "unknownCount": len(result["unknown"]),
              "output": str(opts.output.resolve())})
        if not result["ok"]:
            raise SystemExit(1)
        return
    if opts.command == "reconcile":
        show(reconcile(opts.state_dir, opts.request_id, opts.evidence, opts.outcome, opts.note))
        return
    if opts.command == "doctor":
        from chatcut_stdio import server_config
        command, _ = server_config()
        show({"python": sys.version.split()[0], "jsonschemaInstalled": importlib.util.find_spec("jsonschema") is not None,
              "serverExecutable": command[0], "networkConnectionTested": False})
        return
    if opts.command == "receipt":
        import re
        if not re.fullmatch(r"[0-9a-f-]{36}", opts.request_id):
            raise AccessError("invalid_request_id", "requestId 格式错误")
        path = Path(opts.state_dir).resolve() / "receipts" / (opts.request_id + ".json")
        show(compact_result({**read_json(path), "receiptPath": str(path)}))
        return
    offline = getattr(opts, "catalog", None)
    cached = False
    if opts.command in {"capabilities", "describe", "draft", "instructions"}:
        if offline and opts.refresh:
            raise AccessError("conflicting_input", "--catalog 和 --refresh 不能同时使用")
        default_cache = Path(opts.state_dir).resolve() / "catalog.json"
        if not offline and not opts.refresh and default_cache.is_file():
            offline, cached = default_cache, True
    if offline:
        data = read_json(offline)
        catalog = Catalog(data.get("guidelines", data) if isinstance(data, dict) else data)
        dispatch_catalog(opts, catalog, {"source": "cached" if cached else "offline", "catalogPath": str(offline.resolve()),
                                        "capturedAt": data.get("capturedAt") if isinstance(data, dict) else None,
                                        "warning": "离线目录仅供导航；执行始终重新读取实时 schema。"})
        return

    # Read and parse inputs before establishing a connection.
    args = None
    if opts.command in {"prepare", "call"}:
        args = build_arguments(opts.params, sets=opts.set, texts=opts.text, files=opts.file,
                               json_files=opts.json_file, json_strings=opts.json_string)
    plan = read_json(opts.plan) if opts.command == "run" else None
    with Session(opts.state_dir, opts.timeout) as session:
        if opts.command == "active":
            show({"project": session.active, "server": session.server,
                  "operationCount": len(session.catalog.operations)})
        elif opts.command == "verify-size":
            show(session.verify_size(opts.project, opts.timeline, opts.width, opts.height))
        elif opts.command == "check-captions":
            result = session.check_captions(project_id=opts.project, speech_sources=opts.speech_track,
                                            music_sources=opts.music_track)
            show(result)
            if not result["ok"]:
                raise SystemExit(1)
        elif opts.command == "ready":
            show(compact_result(session.ready(opts.project, read_json(opts.params) if opts.params else None)))
        elif opts.command in {"capabilities", "describe", "draft", "instructions"}:
            dispatch_catalog(opts, session.catalog, {"source": "live", "project": session.active,
                                                     "catalogPath": str(session.state_dir / "catalog.json"),
                                                     "server": session.server})
        elif opts.command in {"prepare", "call"}:
            plan = session.prepare(opts.operation, args, opts.project)
            if opts.command == "prepare":
                show(save_plan(opts.output, plan))
            else:
                # Persist the exact plan before submitting so the same ID can be inspected/replayed safely.
                path = Path(opts.state_dir) / "plans" / (plan["requestId"] + ".json")
                write_json(path, plan, exclusive=True)
                show_receipt(session.run(plan, allow_write=opts.write, preflight=opts.preflight, allow_layout_change=opts.allow_layout_change))
        elif opts.command == "recipe":
            show(save_plan(opts.output, recipe(session, opts)))
        else:
            show_receipt(session.run(plan, allow_write=opts.write, preflight=opts.preflight, allow_layout_change=opts.allow_layout_change))


def dispatch_catalog(opts, catalog, context):
    if opts.command == "capabilities":
        show({**context, **overview(catalog, opts.search, opts.group)})
    elif opts.command == "describe":
        operation = catalog.describe(opts.operation)
        if opts.output:
            write_json(opts.output, operation, exclusive=True)
            show({**context, "name": opts.operation, "definitionPath": str(opts.output.resolve())})
        else:
            show({**context, **operation})
    elif opts.command == "instructions":
        if opts.offset < 0 or not 1 <= opts.limit <= 4000:
            raise AccessError("invalid_page", "offset 必须非负；limit 为 1–4000 字符")
        value = catalog.instruction
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        end = min(len(text), opts.offset + opts.limit)
        show({**context, "catalogHash": catalog.hash, "instruction": text[opts.offset:end],
              "offset": opts.offset, "totalChars": len(text), "nextOffset": end if end < len(text) else None,
              "note": "后续页使用同一 catalogPath 离线读取，避免跨版本拼页。"})
    else:
        draft = catalog.draft(opts.operation)
        write_json(opts.output, draft["arguments"], exclusive=True)
        show({**context, "output": str(opts.output.resolve()), "executed": False,
              "hints": draft["hints"],
              "note": "仅草稿，null 必须填写；prepare 时完整校验。"})


if __name__ == "__main__":
    try:
        main()
    except AccessError as exc:
        show(exc.as_dict())
        sys.exit(2 if exc.code in {"invalid_arguments", "invalid_field", "unknown_operation"} else 1)
    except RemoteToolError as exc:
        opts = parser().parse_args()
        path = Path(opts.state_dir).resolve() / "errors" / (str(uuid.uuid4()) + ".json")
        write_json(path, {"rawError": exc.raw, "issues": exc.issues})
        show({"ok": False, "code": "remote_tool_error", "operation": getattr(opts, "operation", opts.command),
              "message": str(exc), "issues": exc.issues, "errorPath": str(path),
              "nextStep": "查看完整错误；不要自动重试写入。"})
        sys.exit(1)
    except (ValueError, OSError, RuntimeError, TimeoutError) as exc:
        show({"ok": False, "code": "local_or_transport_error", "message": str(exc),
              "nextStep": "若已提交调用，先查 .chatcut/receipts；不要自动重试。"})
        sys.exit(1)
