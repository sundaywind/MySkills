#!/usr/bin/env python3
"""Bounded MCP stdio transport. Use chatcut_client.Session for validated operations."""
import json
import hashlib
import math
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import time
from chatcut_errors import RemoteToolError


def server_config():
    override = os.environ.get("CHATCUT_MCP_COMMAND")
    if override:
        return [os.path.expanduser(override)], {}
    path = Path(os.environ.get("CHATCUT_MCP_CONFIG", "~/.workbuddy/mcp.json")).expanduser()
    if path.exists():
        config = json.loads(path.read_text())
        if not isinstance(config, dict):
            raise ValueError("MCP 配置必须是对象")
        servers = config.get("mcpServers", config)
        if not isinstance(servers, dict):
            raise ValueError("mcpServers 必须是对象")
        entry = servers.get("chatcut_desktop", {})
        if not isinstance(entry, dict):
            raise ValueError("chatcut_desktop 配置必须是对象")
        if entry.get("command"):
            if not isinstance(entry["command"], str):
                raise ValueError("chatcut_desktop.command 必须是可执行路径字符串")
            args, env = entry.get("args", []), entry.get("env", {})
            if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
                raise ValueError("chatcut_desktop.args must be a list of strings")
            if not isinstance(env, dict) or not all(isinstance(v, str) for v in env.values()):
                raise ValueError("chatcut_desktop.env must contain string values")
            return [os.path.expanduser(entry["command"]), *args], env
    wrapper = Path.home() / "Library/Application Support/ChatCut/chatcut-mcp"
    if wrapper.is_file():
        return [str(wrapper)], {}
    command = shutil.which("chatcut-mcp")
    if command:
        return [command], {}
    raise RuntimeError("找不到 ChatCut MCP；请检查安装或设置 CHATCUT_MCP_COMMAND 为可执行文件路径。")


def tool_result(res):
    if "error" in res:
        raise RemoteToolError(res, result_summary(res))
    result = res.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("MCP response is missing result")
    if result.get("isError"):
        raise RemoteToolError(res, result_summary(res))
    return result


class ChatCutStdio:
    def __init__(self, client_name="chatcut-skill-stdio", timeout=30):
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be positive")
        self.timeout = timeout
        self._activated = False
        command, extra_env = server_config()
        self.endpoint_fingerprint = hashlib.sha256(json.dumps(command).encode()).hexdigest()
        env = dict(os.environ)
        env.update(extra_env)
        env.setdefault("CHATCUT_MCP_CLIENT", "workbuddy")
        self.p = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True, bufsize=1, env=env)
        self._id = 0
        self._rpc_lock = threading.Lock()
        self._responses = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()
        try:
            self.init_result = tool_result(self.rpc("initialize", {
                "protocolVersion": "2024-11-05", "capabilities": {},
                "clientInfo": {"name": client_name, "version": "0.3"}}))
            self.notify("notifications/initialized")
        except Exception:
            self.close()
            raise

    def _read(self):
        try:
            for line in self.p.stdout:
                try:
                    message = json.loads(line)
                    if isinstance(message, dict) and "id" in message and "method" not in message:
                        self._responses.put(message)
                except json.JSONDecodeError:
                    continue
        finally:
            self._responses.put(None)

    def _send(self, obj):
        self.p.stdin.write(json.dumps(obj) + "\n")
        self.p.stdin.flush()

    def rpc(self, method, params=None):
        with self._rpc_lock:
            return self._rpc(method, params)

    def _rpc(self, method, params=None):
        self._id += 1
        req = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            req["params"] = params
        deadline = time.monotonic() + self.timeout
        # A full stdin pipe must not evade the timeout.
        sent = queue.Queue(maxsize=1)
        def write_request():
            try:
                self._send(req)
                sent.put(None)
            except Exception as exc:
                sent.put(exc)
        threading.Thread(target=write_request, daemon=True).start()
        label = (params or {}).get("name", method)
        try:
            error = sent.get(timeout=max(0, deadline - time.monotonic()))
        except queue.Empty:
            raise TimeoutError(f"MCP {label} 写入超时；提交结果未知，禁止自动重试。") from None
        if error:
            raise RuntimeError(f"MCP {label} 连接写入失败；提交结果可能未知。") from error
        while True:
            try:
                obj = self._responses.get(timeout=max(0, deadline - time.monotonic()))
            except queue.Empty:
                raise TimeoutError(f"MCP {label} 超过 {self.timeout}s；提交结果可能未知，禁止自动重试。") from None
            if obj is None:
                raise RuntimeError("MCP 连接关闭；请检查 Desktop 是否运行。")
            if isinstance(obj, dict) and obj.get("id") == self._id:
                return obj

    def notify(self, method, params=None):
        obj = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            obj["params"] = params
        self._send(obj)

    def call_tool(self, name, arguments=None):
        if name not in {"get_active_project", "get_guidelines", "execute"}:
            raise ValueError("仅支持 ChatCut Desktop 三个 MCP 入口。")
        if name != "get_active_project" and not self._activated:
            self.activate()
        return self.rpc("tools/call", {"name": name, "arguments": arguments or {}})

    def activate(self):
        self._activated = False
        res = self.call_tool("get_active_project")
        result = tool_result(res)
        value = result.get("structuredContent") or _first_text_json(res)
        if not isinstance(value, dict):
            raise RuntimeError("无法解析当前项目")
        self._activated = True
        return value

    def guidelines_text(self):
        result = tool_result(self.call_tool("get_guidelines"))
        if result.get("structuredContent"):
            return json.dumps(result["structuredContent"], ensure_ascii=False)
        return "\n".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")

    def execute(self, name, arguments):
        return self.call_tool("execute", {"name": name, "arguments": arguments})

    def close(self):
        if self.p.poll() is None:
            self.p.terminate()
            try:
                self.p.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.p.kill()
                self.p.wait(timeout=2)
        for stream in (self.p.stdin, self.p.stdout):
            if stream:
                stream.close()


def _first_text_json(res):
    for c in res.get("result", {}).get("content", []):
        if c.get("type") == "text":
            try:
                return json.loads(c["text"])
            except (ValueError, TypeError):
                continue
    return {}


def result_summary(res, max_chars=4000):
    if "error" in res:
        out = "RPC ERROR: " + json.dumps(res["error"], ensure_ascii=False)
        return out[:max_chars] + ("\n[truncated; full error retained]" if len(out) > max_chars else "")
    result = res.get("result", {})
    parts = ["[isError=true]"] if result.get("isError") else []
    for c in result.get("content", []):
        if c.get("type") == "text":
            parts.append(c.get("text", ""))
        elif c.get("type") == "image":
            parts.append("[inline image omitted]")
    if not parts and result.get("structuredContent"):
        parts.append(json.dumps(result["structuredContent"], ensure_ascii=False))
    out = "\n".join(parts)
    return out if len(out) <= max_chars else out[:max_chars] + "\n[truncated]"
