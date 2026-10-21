#!/usr/bin/env python3
"""Verify a native media export; never submit/retry an export or copy its output."""
import argparse
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time

from chatcut_client import AccessError, read_json, result_data


def positive(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError("时间参数必须是有限正数")
    return number


def export_target(receipt):
    if receipt.get("name") != "local_export" or receipt.get("state") != "returned":
        raise ValueError("需要本次 local_export 的成功返回 receipt，不是计划或未确认记录")
    result = receipt.get("result", {})
    if result.get("isError"):
        raise ValueError("导出返回了工具错误")
    data = result_data(result)
    if not isinstance(data, dict) or not isinstance(data.get("outputPath"), str):
        raise ValueError("导出结果缺少 outputPath；核对实际返回格式，不猜路径")
    path = Path(data["outputPath"]).expanduser()
    if not path.is_absolute():
        raise ValueError("导出返回路径不是绝对路径；请核对，不能按当前工作目录猜测")
    if path.suffix.lower() not in {".mp4", ".mov", ".mp3", ".wav"}:
        raise ValueError("仅验证音视频导出；字幕、XML、剪映草稿不能用媒体验证器")
    started = positive(receipt.get("startedAt", 0))
    return path, started, data.get("taskId")


def signature(path, started):
    stat = path.stat()
    if not path.is_file() or stat.st_size <= 0:
        raise ValueError("文件未生成或为空")
    if stat.st_mtime < started:
        raise ValueError("文件早于本次导出，不能交付旧文件")
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def probe_media(path, executable, expected, tolerance, timeout):
    # count_packets scans to EOF, unlike checking only the container header.
    result = subprocess.run(
        [executable, "-v", "error", "-count_packets", "-show_entries",
         "format=duration:stream=codec_type,nb_read_packets", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode or result.stderr.strip():
        raise ValueError("ffprobe 检查失败：" + result.stderr.strip()[:500])
    info = json.loads(result.stdout)
    duration = positive(info.get("format", {}).get("duration", 0))
    streams = [s for s in info.get("streams", []) if s.get("codec_type") in {"audio", "video"}]
    if not streams or any(int(s.get("nb_read_packets", 0)) <= 0 for s in streams):
        raise ValueError("缺少可读的音视频数据包")
    if path.suffix.lower() in {".mp4", ".mov"} and not any(s["codec_type"] == "video" for s in streams):
        raise ValueError("视频导出缺少视频流")
    if abs(duration - expected) > tolerance:
        raise ValueError(f"时长不符：实际 {duration:.3f} 秒，预期 {expected:.3f} 秒")
    return {"durationSeconds": duration, "streams": streams}


def wait_export(receipt, *, expected_duration, timeout=600, stable_seconds=10,
                interval=2, tolerance=0.5, ffprobe="ffprobe"):
    expected_duration, timeout, stable_seconds, interval, tolerance = map(
        positive, (expected_duration, timeout, stable_seconds, interval, tolerance))
    if stable_seconds >= timeout:
        raise ValueError("等待上限必须大于稳定观察时间")
    executable = shutil.which(ffprobe)
    if not executable:
        raise ValueError("未找到 ffprobe；请安装 FFmpeg 或用 --ffprobe 指定路径，不能跳过媒体检查")
    path, started, task_id = export_target(receipt)
    deadline = time.monotonic() + timeout
    previous, stable_since = None, None
    last_error = "文件尚未稳定"
    while time.monotonic() < deadline:
        try:
            current = signature(path, started)
            now = time.monotonic()
            if current != previous:
                previous, stable_since = current, now
            elif now - stable_since >= stable_seconds:
                media = probe_media(path, executable, expected_duration, tolerance,
                                    min(30, max(0.001, deadline - now)))
                if signature(path, started) != current:
                    raise ValueError("媒体检查期间文件仍在变化")
                if time.monotonic() >= deadline:
                    raise TimeoutError("媒体检查超过等待上限")
                return {"ok": True, "verification": "file_verified",
                        "backendCompletionConfirmed": False, "outputPath": str(path),
                        "taskId": task_id, "requestId": receipt.get("requestId"),
                        "sizeBytes": current[2], **media,
                        "note": "已通过本次文件新鲜度、稳定性、数据包和时长检查；不是服务端完成确认或逐帧解码保证。"}
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            last_error = str(exc)
            previous, stable_since = None, None
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(interval, remaining))
    raise TimeoutError("导出验证超时；不要复制或交付。最后检查：" + last_error)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--expected-duration", type=float, required=True, help="目标时间线/导出范围的秒数，不是待验文件自己的时长")
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--stable-seconds", type=float, default=10)
    parser.add_argument("--interval", type=float, default=2)
    parser.add_argument("--tolerance", type=float, default=0.5)
    parser.add_argument("--ffprobe", default="ffprobe")
    args = parser.parse_args()
    try:
        options = vars(args).copy()
        options.pop("receipt")
        result = wait_export(read_json(args.receipt), **options)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (AccessError, OSError, ValueError, TypeError, TimeoutError) as exc:
        print(json.dumps({"ok": False, "error": str(exc), "nextStep": "核查原导出任务；不要自动重新导出或交付。"}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
