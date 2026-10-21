"""Schema-driven ChatCut access: discovery, validation, plans, receipts and recipes."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
import uuid

from chatcut_stdio import ChatCutStdio, tool_result
from chatcut_errors import RemoteToolError, pointer
from chatcut_checks import available_frames, caption_coverage


class AccessError(Exception):
    def __init__(self, code, message, details=None):
        self.code, self.details = code, details
        super().__init__(message)

    def as_dict(self):
        return {"ok": False, "code": self.code, "message": str(self), "details": self.details}


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"重复 JSON 字段：{key}")
        value[key] = item
    return value


def loads(text):
    def invalid(value):
        raise ValueError(f"非标准 JSON 数值：{value}")
    return json.loads(text, object_pairs_hook=_pairs, parse_constant=invalid)


def dumps(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True)


def fingerprint(value):
    return hashlib.sha256(dumps(value).encode("utf-8")).hexdigest()


def read_json(path):
    return loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value, *, exclusive=False):
    """Private files; atomically replace receipts/cache, never silently overwrite a plan."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode()
    if exclusive:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        return
    fd, temp = tempfile.mkstemp(prefix="." + path.name + "-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def validate(schema, arguments):
    """Use the declared draft. External references never trigger network requests."""
    try:
        from jsonschema import validators, Draft202012Validator, FormatChecker
        from referencing import Registry
        from referencing.exceptions import NoSuchResource
    except ImportError as exc:
        raise AccessError("missing_dependency",
                          "缺少 jsonschema。请用当前 Python 安装 scripts/requirements.txt。") from exc

    if not isinstance(arguments, dict):
        raise AccessError("invalid_arguments", "arguments 必须是 JSON 对象")
    # Reject NaN/Infinity even when arguments came from the Python API.
    try:
        dumps(arguments)
    except (TypeError, ValueError) as exc:
        raise AccessError("invalid_arguments", str(exc)) from exc

    def no_network(uri):
        raise NoSuchResource(ref=uri)

    try:
        if isinstance(schema, dict) and "$schema" in schema:
            cls = validators.validator_for(schema, default=None)
            if cls is None:
                raise AccessError("unknown_schema_draft", "不支持该 JSON Schema 版本，不能跳过校验")
        else:
            cls = Draft202012Validator
        cls.check_schema(schema)
        validator = cls(schema, registry=Registry(retrieve=no_network), format_checker=FormatChecker())
        errors = list(validator.iter_errors(arguments))
    except AccessError:
        raise
    except Exception as exc:
        raise AccessError("schema_unusable", "接口 schema 无效或引用无法解析；未提交操作。",
                          {"reason": str(exc)}) from exc
    if errors:
        details = []
        for error in sorted(errors, key=lambda e: "/".join(map(str, e.absolute_path)))[:30]:
            parts = list(error.absolute_path)
            if error.validator == "required" and isinstance(error.instance, dict):
                for field in error.validator_value:
                    item = {"path": pointer(parts + [field]), "rule": "required", "message": "缺少必填字段"}
                    if field not in error.instance and item not in details:
                        details.append(item)
            else:
                details.append({"path": pointer(parts), "rule": error.validator, "message": error.message})
        raise AccessError("invalid_arguments", "参数不符合当前接口定义；未提交操作。", details)


class Catalog:
    def __init__(self, document):
        if isinstance(document, list):
            document = {"instruction": "", "operations": document}
        if not isinstance(document, dict) or not isinstance(document.get("operations"), list):
            raise AccessError("invalid_guidelines", "guidelines 缺少 operations 数组")
        self.document = document
        self.instruction = document.get("instruction", document.get("instructions", ""))
        self.operations = {}
        for op in document["operations"]:
            if not isinstance(op, dict) or not isinstance(op.get("name"), str) or not isinstance(op.get("inputSchema"), dict):
                raise AccessError("invalid_guidelines", "接口列表含不完整的操作定义")
            if op["name"] in self.operations:
                raise AccessError("invalid_guidelines", "接口列表含重复名称")
            self.operations[op["name"]] = op
        self.hash = fingerprint({**document, "operations": sorted(document["operations"], key=lambda op: op["name"])})

    def operation(self, name):
        if name not in self.operations:
            raise AccessError("unknown_operation", f"当前 ChatCut 没有操作 {name}；请查询 capabilities")
        return self.operations[name]

    def summary(self, query=""):
        query = query.casefold()
        return [{"name": op["name"], "description": op.get("description", ""),
                 "required": op["inputSchema"].get("required", []) if isinstance(op["inputSchema"], dict) else [],
                 "readOnlyHint": op.get("annotations", {}).get("readOnlyHint")}
                for op in self.operations.values()
                if not query or query in (op["name"] + " " + op.get("description", "")).casefold()]

    def describe(self, name):
        return dict(self.operation(name))

    def draft(self, name):
        """Required fields only; null means the caller must supply a value, never a guessed ID."""
        schema = self.operation(name)["inputSchema"]
        hints = []

        def sample(node, root, field, depth=0):
            if not isinstance(node, dict) or depth > 15:
                hints.append({"path": field, "note": "需按完整 schema 填写"})
                return None
            if "$ref" in node:
                ref = node["$ref"]
                if not ref.startswith("#/"):
                    return None
                target = root
                try:
                    for part in ref[2:].split("/"):
                        target = target[part.replace("~1", "/").replace("~0", "~")]
                except (KeyError, TypeError):
                    return None
                return sample(target, root, field, depth + 1)
            if "const" in node:
                return copy.deepcopy(node["const"])
            if "default" in node:
                return copy.deepcopy(node["default"])
            if node.get("type") == "object":
                return {key: sample(node.get("properties", {}).get(key, {}), root, field + "/" + key, depth + 1)
                        for key in node.get("required", [])}
            hints.append({"path": field, "type": node.get("type"), "enum": node.get("enum"),
                          "description": node.get("description", ""), "note": "请填写；不猜值"})
            return None

        return {"arguments": sample(schema, schema, ""), "hints": hints,
                "inputSchema": schema, "instruction": self.instruction}


# Conservative fallback for schemas lacking MCP readOnlyHint. Not an operation registry.
# Every name and every parameter is still checked against the LIVE catalog.
READS = {"read_project", "inspect_item", "inspect_asset", "browse_assets",
         "read_captions", "find_transcript", "preview_timeline", "list_projects",
         "browse_library", "search_fonts"}
READ_ACTIONS = {"edit_track": {"list"}, "manage_timelines": {"list"},
                "track_progress": {"status", "params"}, "manage_markers": {"list", "get"}}


def read_only(operation, arguments):
    hint = operation.get("annotations", {}).get("readOnlyHint")
    if isinstance(hint, bool):
        return hint
    action = arguments.get("action")
    return operation["name"] in READS or (
        isinstance(action, str) and action in READ_ACTIONS.get(operation["name"], set()))


def result_data(result):
    if "structuredContent" in result:
        return result["structuredContent"]
    for block in result.get("content", []):
        if block.get("type") == "text":
            try:
                return loads(block["text"])
            except (ValueError, KeyError):
                pass
    return None


def reconcile(state_dir, request_id, evidence_id, outcome, note):
    """Record an explicit evidence-based conclusion, never synthesize a tool success."""
    if not all(isinstance(v, str) and re.fullmatch(r"[0-9a-f-]{36}", v)
               for v in (request_id, evidence_id)):
        raise AccessError("invalid_request_id", "需要有效的原调用和只读证据 requestId")
    if outcome not in {"applied", "not-applied"} or not note.strip():
        raise AccessError("invalid_reconciliation", "必须明确结论并说明核对到的实际 ID/字段；查不清不要解除拦截")
    root = Path(state_dir).resolve() / "receipts"
    path = root / (request_id + ".json")
    receipt = read_json(path)
    evidence = read_json(root / (evidence_id + ".json"))
    if receipt.get("state") != "unknown" or receipt.get("reconciliation"):
        raise AccessError("invalid_reconciliation", "只处理尚未核实的 unknown；pending 可能仍在运行，不解除拦截")
    if (evidence.get("state") != "returned" or evidence.get("mutation") is not False
            or evidence.get("projectId") != receipt.get("projectId")
            or evidence.get("endpoint") != receipt.get("endpoint")
            or evidence.get("server") != receipt.get("server")
            or evidence.get("startedAt", 0) <= receipt.get("finishedAt", receipt.get("startedAt", 0))):
        raise AccessError("invalid_evidence", "证据必须是掉线后、同服务同项目的成功只读调用")
    data = result_data(evidence.get("result", {}))
    if isinstance(data, dict) and (data.get("success") is False or data.get("status") in {"failed", "error"}):
        raise AccessError("invalid_evidence", "只读结果报告失败，不能作为核对证据")
    receipt["reconciliation"] = {"outcome": outcome, "note": note, "evidenceRequestId": evidence_id,
                                 "recordedAt": time.time(), "basis": "explicit_caller_review"}
    write_json(path, receipt)
    return {"ok": True, "receiptPath": str(path), "reconciliation": receipt["reconciliation"],
            "resubmitted": False, "note": "原请求仍禁止重放；这是调用者核对结论，不是伪造的服务端返回。"}


class Session:
    def __init__(self, state_dir=".chatcut", timeout=30, client_factory=ChatCutStdio):
        self.state_dir = Path(state_dir).resolve()
        self.timeout, self.client_factory = timeout, client_factory
        self.client = None

    def __enter__(self):
        self.client = self.client_factory("chatcut-access", timeout=self.timeout)
        try:
            self.active = self.client.activate()
            self.catalog = Catalog(loads(self.client.guidelines_text()))
            self.server = self.client.init_result.get("serverInfo", {})
            self.endpoint = getattr(self.client, "endpoint_fingerprint", None)
            write_json(self.state_dir / "catalog.json", {
                "capturedAt": time.time(), "server": self.server,
                "endpoint": self.endpoint, "projectId": self.active.get("projectId"),
                "catalogHash": self.catalog.hash, "guidelines": self.catalog.document})
            return self
        except BaseException as exc:
            self.client.close()
            if isinstance(exc, RemoteToolError):
                path = self.state_dir / "errors" / (str(uuid.uuid4()) + ".json")
                write_json(path, {"rawError": exc.raw, "issues": exc.issues})
                raise AccessError("connection_tool_error", str(exc),
                                  {"errorPath": str(path), "issues": exc.issues}) from exc
            raise

    def __exit__(self, *args):
        self.client.close()

    def check_project(self, expected):
        if not expected:
            raise AccessError("project_required", "调用必须显式指定目标 projectId")
        current = self.client.activate()
        if current.get("projectId") != expected:
            raise AccessError("project_changed", "当前项目与目标不同；未提交操作。",
                              {"expected": expected, "actual": current.get("projectId")})
        return current

    def ready(self, project_id, arguments=None):
        """Explicit readiness check after creating/switching projects; never retry writes."""
        arguments = {} if arguments is None else arguments
        operation = self.catalog.operation("read_project")
        if not read_only(operation, arguments):
            raise AccessError("readiness_unavailable", "当前 read_project 未被声明为只读，停止就绪检查")
        plan = self.prepare("read_project", arguments, project_id)
        result = self.run(plan)
        data = result_data(result.get("result", {}))
        if isinstance(data, dict) and (data.get("success") is False or data.get("status") in ("failed", "error")):
            raise AccessError("project_not_ready", "读取项目报告失败，不要继续写入")
        self.check_project(project_id)
        return result

    def _check_unresolved(self, project_id):
        for path in (self.state_dir / "receipts").glob("*.json"):
            receipt = read_json(path)
            if (receipt.get("projectId") in (None, project_id)
                    and receipt.get("mutation") is not False
                    and receipt.get("state") in {"pending", "unknown"}
                    and not receipt.get("reconciliation")):
                raise AccessError("unresolved_write", "此项目有未核实写入；换请求 ID 也不能重发。先只读核查并 reconcile。",
                                  {"receiptPath": str(path), "requestId": receipt.get("requestId")})

    def composition(self, project_id):
        receipt = self.ready(project_id)
        data = result_data(receipt["result"])
        timeline = data.get("activeTimeline") if isinstance(data, dict) else None
        if not isinstance(timeline, dict) or not all(
                key in timeline for key in ("id", "compositionWidth", "compositionHeight", "durationFrames")):
            raise AccessError("composition_unavailable", "read_project 未返回可确认的活动时间线尺寸；不能猜测", {"receiptPath": receipt["receiptPath"]})
        return timeline, receipt["receiptPath"]

    def verify_size(self, project_id, timeline_id, width, height):
        timeline, path = self.composition(project_id)
        actual = {"timelineId": timeline["id"], "width": timeline["compositionWidth"], "height": timeline["compositionHeight"]}
        expected = {"timelineId": timeline_id, "width": width, "height": height}
        if actual != expected:
            raise AccessError("composition_mismatch", "实际时间线/尺寸与目标不符；停止摆素材，不自动重试改尺寸",
                              {"expected": expected, "actual": actual, "receiptPath": path})
        return {"ok": True, "composition": actual, "receiptPath": path}

    def prepare(self, name, arguments, project_id):
        self.check_project(project_id)
        operation = self.catalog.operation(name)
        try:
            validate(operation["inputSchema"], arguments)
        except AccessError as exc:
            raise AccessError(exc.code, f"{name}：{exc}", exc.details) from exc
        plan = {"version": 1, "requestId": str(uuid.uuid4()), "createdAt": time.time(),
                "projectId": project_id, "name": name, "arguments": copy.deepcopy(arguments),
                "operationHash": fingerprint(operation), "catalogHash": self.catalog.hash,
                "server": self.server, "endpoint": self.endpoint}
        plan["planHash"] = fingerprint(plan)
        return plan

    def run(self, plan, *, allow_write=False, preflight="auto", allow_layout_change=False):
        """At-most-once submission for a requestId in this state directory. No blind retry."""
        required = {"version", "requestId", "createdAt", "projectId", "name", "arguments",
                    "operationHash", "catalogHash", "server", "endpoint", "planHash"}
        if not isinstance(plan, dict) or set(plan) != required or plan["version"] != 1:
            raise AccessError("invalid_plan", "计划格式错误；请重新 prepare")
        if not isinstance(plan["requestId"], str) or not re.fullmatch(r"[0-9a-f-]{36}", plan["requestId"]):
            raise AccessError("invalid_plan", "requestId 格式错误")
        unsigned = {key: value for key, value in plan.items() if key != "planHash"}
        if plan["planHash"] != fingerprint(unsigned):
            raise AccessError("plan_modified", "计划被改动；请重新 prepare 和校验")
        receipt_path = self.state_dir / "receipts" / (plan["requestId"] + ".json")

        # A prior returned result must never be re-executed, even after the project/schema changes.
        if receipt_path.exists():
            return self._existing(receipt_path, plan)

        # Python callers may hold a Session open for a long time. Revalidate the live contract.
        self.catalog = Catalog(loads(self.client.guidelines_text()))
        operation = self.catalog.operation(plan["name"])
        if plan["operationHash"] != fingerprint(operation) or plan["catalogHash"] != self.catalog.hash:
            raise AccessError("schema_changed", "接口定义已变化；请重新 prepare，不执行旧计划")
        if plan["server"] != self.server or plan["endpoint"] != self.endpoint:
            raise AccessError("server_changed", "连接的服务已变化；请重新 prepare")
        validate(operation["inputSchema"], plan["arguments"])
        mutation = not read_only(operation, plan["arguments"])
        if mutation and not allow_write:
            raise AccessError("write_not_enabled", "此操作可能修改项目；在用户任务已授权时传 --write")
        if mutation:
            self._check_unresolved(plan["projectId"])
        self.check_project(plan["projectId"])
        resizing = plan["name"] == "manage_timelines" and plan["arguments"].get("action") == "update" and any(
            key in plan["arguments"] for key in ("ratio", "compositionWidth", "compositionHeight"))
        if resizing:
            timeline, evidence_path = self.composition(plan["projectId"])
            if plan["arguments"].get("timelineId") != timeline["id"]:
                raise AccessError("composition_target", "改尺寸需显式指定当前活动时间线完整 ID；先切到目标再操作")
            if (timeline["durationFrames"] != 0 or timeline.get("captionsPresent") is not False) and not allow_layout_change:
                raise AccessError("layout_change_blocked", "时间线已有内容或无法确认空白，改比例可能破坏浮层；确认任务允许后用 --allow-layout-change",
                                  {"receiptPath": evidence_path})
        prop = operation["inputSchema"].get("properties", {}).get("validateOnly", {})
        supported = prop.get("type") == "boolean"
        library_add = plan["name"] == "edit_item" and any(
            isinstance(item, dict) and str(item.get("assetId", "")).startswith("library:sound:")
            for item in plan["arguments"].get("adds", []) or [])
        if preflight not in {"auto", "require", "skip"}:
            raise AccessError("invalid_preflight", "preflight 必须是 auto/require/skip")
        if preflight == "require":
            if not supported or library_add:
                raise AccessError("preflight_unavailable", "当前操作没有明确的 validateOnly 布尔参数")
            if plan["arguments"].get("validateOnly"):
                raise AccessError("preflight_conflict", "本次调用本身已是 validateOnly，无需重复预检")
        do_preflight = (preflight != "skip" and supported and not library_add
                        and not plan["arguments"].get("validateOnly"))

        receipt = {"requestId": plan["requestId"], "planHash": plan["planHash"],
                   "projectId": plan["projectId"], "name": plan["name"],
                   "mutation": mutation, "server": self.server, "endpoint": self.endpoint,
                   "state": "pending", "startedAt": time.time()}
        try:
            write_json(receipt_path, receipt, exclusive=True)
        except FileExistsError:
            return self._existing(receipt_path, plan)
        # Reservation happens before any execute. A crash leaves pending and blocks replay.
        try:
            if do_preflight:
                preview_args = {**plan["arguments"], "validateOnly": True}
                validate(operation["inputSchema"], preview_args)
                preview_raw = self.client.execute(plan["name"], preview_args)
                receipt["preflightRaw"] = preview_raw
                write_json(receipt_path, receipt)
                preview = tool_result(preview_raw)
                data = result_data(preview)
                validation = data.get("validation") if isinstance(data, dict) else None
                verdict = validation.get("isValid") if isinstance(validation, dict) else None
                failed = isinstance(data, dict) and (
                    data.get("valid") is False or data.get("isValid") is False or data.get("success") is False
                    or data.get("status") in ("failed", "error"))
                if verdict is False or failed:
                    raise AccessError("preflight_unconfirmed",
                                      "ChatCut 预检未通过；未提交正式操作。", data)
                receipt["preflight"] = preview
                self.check_project(plan["projectId"])
            receipt["phase"] = "submitted"
            write_json(receipt_path, receipt)
            raw = self.client.execute(plan["name"], plan["arguments"])
            receipt["rawResponse"] = raw
            write_json(receipt_path, receipt)
            result = tool_result(raw)
            receipt.update(state="returned", result=result, finishedAt=time.time())
            if mutation:
                try:
                    after = self.client.activate()
                    if after.get("projectId") != plan["projectId"]:
                        receipt["warning"] = "操作已返回，但项目发生切换；核查实际结果，不要重复提交。"
                except Exception:
                    receipt["warning"] = "操作已返回，但未能复核项目；不要重复提交。"
            write_json(receipt_path, receipt)
            if resizing:
                try:
                    actual, evidence_path = self.composition(plan["projectId"])
                    args = plan["arguments"]
                    correct = actual["id"] == args["timelineId"]
                    for key in ("compositionWidth", "compositionHeight"):
                        if key in args:
                            correct = correct and actual[key] == args[key]
                    if "ratio" in args:
                        w, h = map(int, args["ratio"].split(":"))
                        correct = correct and actual["compositionWidth"] * h == actual["compositionHeight"] * w
                    receipt["compositionVerification"] = {"ok": correct, "actual": actual, "receiptPath": evidence_path,
                        "nextStep": "尺寸核对通过；若原有内容仍须检查布局" if correct else "停止摆素材；尺寸未生效，不自动重试"}
                except Exception as exc:
                    receipt["compositionVerification"] = {"ok": False, "error": str(exc), "nextStep": "修改已返回，但无法核实尺寸；停止摆素材，不重发"}
                write_json(receipt_path, receipt)
            return {**receipt, "receiptPath": str(receipt_path), "replayed": False}
        except BaseException as exc:
            # Even a remote tool error may occur after partial work. Never auto-replay it.
            state = "blocked" if isinstance(exc, AccessError) and receipt.get("phase") != "submitted" else "unknown"
            receipt.update(state=state, error=str(exc), finishedAt=time.time(),
                           nextStep="先核实 ChatCut 实际状态；该 requestId 不会自动重试。")
            if isinstance(exc, RemoteToolError):
                receipt.update(rawError=exc.raw, issues=exc.issues)
            try:
                write_json(receipt_path, receipt)
            except OSError:
                pass  # Existing pending marker still blocks replay.
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            raise AccessError("execution_uncertain" if state == "unknown" else "preflight_failed",
                              f"{plan['name']}：{exc}", {"operation": plan["name"],
                              "receiptPath": str(receipt_path), "state": state,
                              "issues": getattr(exc, "issues", [])}) from exc

    @staticmethod
    def _existing(path, plan):
        try:
            existing = read_json(path)
        except (ValueError, OSError) as exc:
            raise AccessError("receipt_unreadable", "调用记录无法读取；为避免重复执行已停止") from exc
        if existing.get("planHash") != plan["planHash"]:
            raise AccessError("request_id_reused", "同一 requestId 不能用于不同参数")
        if existing.get("state") == "returned":
            return {**existing, "receiptPath": str(path), "replayed": True}
        raise AccessError("replay_blocked", "此调用已提交或结果不确定；先查实际状态，禁止盲目重试。",
                          {"receiptPath": str(path), "state": existing.get("state")})

    # Helpers only assemble API-shaped data. Fresh schema validation remains mandatory.
    def caption_data(self, project_id):
        plan = self.prepare("read_captions", {}, project_id)
        receipt = self.run(plan)
        self.check_project(project_id)
        return result_data(receipt["result"]), receipt["receiptPath"]

    def check_captions(self, *, project_id, speech_sources, music_sources=()):
        data, path = self.caption_data(project_id)
        return {**caption_coverage(data, speech_sources, music_sources), "receiptPath": path}

    def hide_music_captions(self, *, project_id, caption_track, music_source, speech_sources):
        data, _ = self.caption_data(project_id)
        caption_coverage(data, speech_sources, [music_source])  # validates explicit, disjoint source roles
        tracks = [t for t in data["captions"]["tracks"] if t.get("id") == caption_track]
        if len(tracks) != 1 or tracks[0].get("sourceTrackId") != music_source:
            raise AccessError("caption_source_mismatch", "该字幕轨不唯一或不属于指定音乐源轨；不隐藏")
        return self.prepare("edit_captions", {"action": "track", "json": dumps({"trackId": caption_track, "visible": False})}, project_id)

    def transcribe_speech(self, *, project_id, asset_id, role):
        if role != "speech":
            raise AccessError("not_speech", "仅对明确的人声素材发起转写；不主动转写纯音乐")
        return self.prepare("trigger_transcript", {"asset": asset_id}, project_id)

    def place_media(self, *, project_id, asset_id, track_id, kind, start_frame,
                    duration_frames, source_duration, fps, source_in_us=0):
        if kind not in {"audio", "video"}:
            raise AccessError("invalid_arguments", "place-media 仅用于正常速度音视频")
        capacity = available_frames(source_duration, fps, source_in_us, duration_frames)
        if not capacity["ok"]:
            raise AccessError("source_duration_exceeded", "请求超出源素材可用帧数；未提交，也不自动缩短", capacity)
        plan = self.place(project_id=project_id, asset_id=asset_id, track_id=track_id, kind=kind,
                          start_frame=start_frame, duration_frames=duration_frames)
        # Re-prepare so sourceIn participates in schema validation and the plan hash.
        args = copy.deepcopy(plan["arguments"])
        args["adds"][0]["sourceIn"] = source_in_us
        return self.prepare("edit_item", args, project_id)

    def set_size(self, *, project_id, timeline_id, width, height):
        if not timeline_id or any(type(v) is not int or v <= 0 for v in (width, height)):
            raise AccessError("invalid_arguments", "需要完整时间线 ID 和正整数宽高")
        return self.prepare("manage_timelines", {"action": "update", "timelineId": timeline_id,
                            "compositionWidth": width, "compositionHeight": height}, project_id)

    def delete_item(self, *, project_id, item_id, attached_type=None):
        if not isinstance(item_id, str) or not item_id:
            raise AccessError("invalid_arguments", "需要实际时间线片段 ID，不是媒体池素材 ID")
        deletion = {"id": item_id}
        if attached_type is not None:
            if attached_type not in {"pixel-effect", "pixel-transition"}:
                raise AccessError("invalid_arguments", "附属类型只能是 pixel-effect 或 pixel-transition；普通片段删除不带 type")
            deletion["type"] = attached_type
        return self.prepare("edit_item", {"deletes": [deletion]}, project_id)

    def import_files(self, paths, *, project_id, name=None):
        resolved = []
        for path in paths:
            path = Path(path).expanduser().resolve()
            if not path.is_file():
                raise AccessError("file_missing", f"素材文件不存在：{path}")
            resolved.append(str(path))
        if not resolved:
            raise AccessError("file_missing", "至少需要一个素材文件")
        args = {"filePath": resolved[0] if len(resolved) == 1 else resolved}
        if name is not None:
            args["name"] = name
        return self.prepare("push_asset", args, project_id)

    def place(self, *, project_id, asset_id, track_id, kind, start_frame, duration_frames,
              properties=None):
        if not all(isinstance(v, str) and v for v in (asset_id, track_id, kind)):
            raise AccessError("invalid_arguments", "素材、轨道和类型必须是非空字符串")
        if type(start_frame) is not int or start_frame < 0 or type(duration_frames) is not int or duration_frames <= 0:
            raise AccessError("invalid_arguments", "start_frame 应为非负整数，duration_frames 应为正整数，单位都是帧")
        if properties is not None and not isinstance(properties, dict):
            raise AccessError("invalid_arguments", "实例属性必须是对象")
        item = {"type": kind, "assetId": asset_id, "trackId": track_id,
                "startFrame": start_frame, "durationFrames": duration_frames}
        if properties is not None:
            item["propertyOverrides"] = properties
        return self.prepare("edit_item", {"adds": [item]}, project_id)

    def update_item(self, *, project_id, item_id, fields):
        if not isinstance(fields, dict) or not fields or not isinstance(item_id, str) or not item_id:
            raise AccessError("invalid_arguments", "需要非空片段 ID 和更新字段对象")
        if "id" in fields:
            raise AccessError("conflicting_field", "更新字段不要重复包含 id")
        return self.prepare("edit_item", {"updates": [{"id": item_id, **fields}]}, project_id)

    def motion_graphic(self, *, project_id, code_file, metadata):
        if not isinstance(metadata, dict):
            raise AccessError("invalid_arguments", "动效 metadata 必须是对象")
        if "durationInFrames" in metadata and "durationInSeconds" in metadata:
            raise AccessError("invalid_arguments", "动效时长只填帧数或秒数之一")
        if "code" in metadata:
            raise AccessError("conflicting_field", "metadata 不应包含 code；使用 code_file")
        code = Path(code_file).read_text(encoding="utf-8")
        return self.prepare("create_motion_graphic_from_code", {**metadata, "code": code}, project_id)

    def update_asset_code(self, *, project_id, asset_id, code_file, properties=None):
        patch = {"code": Path(code_file).read_text(encoding="utf-8")}
        if properties is not None:
            patch["properties"] = properties
        # The serialization is explicit and isolated; if ChatCut changes its schema, reject.
        return self.prepare("edit_asset", {"action": "update", "assetId": asset_id, "json": dumps(patch)}, project_id)
