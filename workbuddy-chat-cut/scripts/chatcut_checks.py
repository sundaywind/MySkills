"""Deterministic checks; no creative choices, automatic retries, or hidden writes."""
from fractions import Fraction


def available_frames(duration_seconds, fps, source_in_us=0, requested=None):
    """Normal-speed source capacity, exact decimal/rational arithmetic; never round up."""
    if type(source_in_us) is not int or source_in_us < 0:
        raise ValueError("source_in_us 必须是非负整数微秒")
    try:
        duration, rate = Fraction(str(duration_seconds)), Fraction(str(fps))
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError("源时长/帧率需为有效有限数值或分数，如 30000/1001") from exc
    if duration <= 0 or rate <= 0:
        raise ValueError("源时长和时间线帧率必须为正数")
    remaining = duration - Fraction(source_in_us, 1000000)
    if remaining <= 0:
        raise ValueError("源入点已超出素材可用范围")
    capacity = remaining * rate
    maximum = capacity.numerator // capacity.denominator
    if requested is not None and (type(requested) is not int or requested <= 0):
        raise ValueError("请求帧数必须为正整数")
    return {"ok": maximum > 0 and (requested is None or requested <= maximum),
            "maxFrames": maximum, "requestedFrames": requested,
            "fps": str(rate), "sourceInUs": source_in_us,
            "note": "依据提供的源时长和时间线帧率，正常速度向下取整；不自动缩短请求，不适用于变速/循环。"}


def filter_orientation(results, orientation):
    if orientation not in {"vertical", "horizontal", "square"} or not isinstance(results, list):
        raise ValueError("需要结果数组和 vertical/horizontal/square")
    accepted, rejected, unknown = [], [], []
    for index, item in enumerate(results):
        if not isinstance(item, dict):
            unknown.append({"index": index, "reason": "结果不是对象"})
            continue
        try:
            if isinstance(item.get("width"), bool) or isinstance(item.get("height"), bool):
                raise ValueError()
            w, h = Fraction(str(item["width"])), Fraction(str(item["height"]))
            if w <= 0 or h <= 0:
                raise ValueError()
        except (KeyError, ValueError, ZeroDivisionError):
            unknown.append({"index": index, "reason": "缺少有效实际宽高，不根据 orientation 标签猜测"})
            continue
        actual = "vertical" if h > w else "horizontal" if w > h else "square"
        if actual == orientation:
            accepted.append(item)
        else:
            rejected.append({"index": index, "actual": actual})
    return {"ok": bool(accepted), "orientation": orientation, "accepted": accepted,
            "rejected": rejected, "unknown": unknown,
            "note": "仅核对提供的结果宽高，不证明下载文件尺寸或旋转方向；入库前还需核对实际媒体。"}


def caption_coverage(data, speech_sources, music_sources=()):
    speech, music = set(speech_sources), set(music_sources)
    if not speech or not all(isinstance(x, str) and x for x in speech | music) or speech & music:
        raise ValueError("需要互不重叠的口播/音乐源轨完整 ID；不能用 A1 等显示名或混合轨代替")
    captions = data.get("captions") if isinstance(data, dict) else None
    if not isinstance(captions, dict) or not isinstance(captions.get("tracks"), list):
        raise ValueError("read_captions 未返回 captions.tracks；不能确认来源覆盖")
    tracks = captions["tracks"]
    if not all(isinstance(t, dict) for t in tracks):
        raise ValueError("字幕轨返回格式异常")
    covered, missing, hidden, empty = [], [], [], []
    for source in sorted(speech):
        originals = [t for t in tracks if t.get("sourceTrackId") == source and t.get("role") == "original"]
        if not originals:
            missing.append(source)
        elif not any(type(t.get("cardCount")) is int and t["cardCount"] > 0 for t in originals):
            empty.append(source)
        elif captions.get("visible") is not True or not any(
                t.get("visible") is True and type(t.get("cardCount")) is int and t["cardCount"] > 0 for t in originals):
            hidden.append(source)
        else:
            covered.append(source)
    music_captions = [{"captionTrackId": t.get("id"), "sourceTrackId": t.get("sourceTrackId")}
                      for t in tracks if t.get("sourceTrackId") in music and t.get("visible") is True
                      and type(t.get("cardCount")) is int and t["cardCount"] > 0]
    unknown = [t.get("id") for t in tracks if not t.get("sourceTrackId") and t.get("visible") is True]
    return {"ok": not (missing or hidden or empty or music_captions or unknown),
            "coveredSpeechSources": covered, "missingSpeechSources": missing,
            "hiddenSpeechSources": hidden, "emptySpeechSources": empty,
            "visibleMusicCaptionTracks": music_captions, "unknownSourceTracks": unknown,
            "note": "仅证明指定源轨有可见原文字幕，不证明每句齐全或识别准确。缺失时停止，不搬轨/重建字幕。"}
