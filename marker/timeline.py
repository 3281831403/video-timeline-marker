"""视频时间线标记核心逻辑。

时间单位统一为毫秒（ms）。帧号 n 与时间 t 的关系为 n = round(t * fps / 1000)，
即帧时长 frame_ms = 1000 / fps；涉及帧的接口以 1 帧为容差，吸附误差不超过 0.5 帧。

标记结构：{"t": 毫秒, "label": 标签, "color": 颜色}。
除 move_marker 外，各接口均不得原地修改入参，返回值中的列表与入参互不共享。
"""

import bisect
import math
import numbers


class MarkerError(ValueError):
    """时间线标记相关错误：非法索引、非法 fps/duration、批量校验失败等。"""


def _clone(marker):
    """复制一个标记字典，避免返回值与入参共享可变对象。"""
    return dict(marker)


def _check_duration(duration):
    """校验时长：必须是有限正数，否则抛 MarkerError。"""
    if (
        not isinstance(duration, numbers.Real)
        or isinstance(duration, bool)
        or not math.isfinite(duration)
        or duration <= 0
    ):
        raise MarkerError(f"非法时长: {duration!r}，必须为有限正数")


def _check_fps(fps):
    """校验帧率：必须是有限正数，否则抛 MarkerError（避免除零）。"""
    if (
        not isinstance(fps, numbers.Real)
        or isinstance(fps, bool)
        or not math.isfinite(fps)
        or fps <= 0
    ):
        raise MarkerError(f"非法帧率: {fps!r}，必须为有限正数")


def insert_marker(markers, marker):
    """按时间插入一个标记，返回新的标记列表（不修改入参）。

    规则：
    - 结果按 t 升序排列，t 的单位为毫秒；
    - 同一 t 的标记保持插入顺序：已存在的同刻标记在前，新 marker 追加在其后；
    - 除插入位置外，其他标记的相对顺序不变。

    参数：
        markers: 已按 t 升序排列的标记列表。
        marker: 待插入标记 {"t", "label", "color"}。

    返回：新的标记列表。
    """
    times = [m["t"] for m in markers]
    pos = bisect.bisect_right(times, marker["t"])
    return [_clone(m) for m in markers[:pos]] + [_clone(marker)] + [
        _clone(m) for m in markers[pos:]
    ]


def move_marker(markers, index, t):
    """把 markers[index] 的时间改为 t（毫秒），重新排序后返回新列表。

    规则：
    - index 必须满足 0 <= index < len(markers)，否则抛 MarkerError；
    - 修改时间后按 t 升序重新排序，同一时间保持原列表中的相对顺序（稳定排序）；
    - 不修改入参。
    """
    if not isinstance(index, numbers.Integral) or isinstance(index, bool):
        raise MarkerError(f"非法索引: {index!r}")
    if not 0 <= index < len(markers):
        raise MarkerError(f"索引越界: {index}，有效范围 0..{len(markers) - 1}")

    result = [_clone(m) for m in markers]
    result[index]["t"] = t
    # sorted 是稳定排序：同一 t 的标记保持修改前的相对顺序。
    result.sort(key=lambda m: m["t"])
    return result


def merge_close(markers, threshold):
    """合并相邻过近的标记，返回新列表（不修改入参）。

    规则：
    - 相邻指排序后相邻的两个标记；若后一个 t 减去前一个 t <= threshold（毫秒），
      则合并为一个标记，保留较早标记的 t/label/color，并继续与后续标记比较；
    - threshold <= 0 时不合并，返回原内容的副本。

    参数：
        markers: 已按 t 升序的标记列表。
        threshold: 合并阈值，单位毫秒。
    """
    if (
        not isinstance(threshold, numbers.Real)
        or isinstance(threshold, bool)
        or not math.isfinite(threshold)
    ):
        raise MarkerError(f"非法合并阈值: {threshold!r}")

    ordered = sorted((_clone(m) for m in markers), key=lambda m: m["t"])
    if threshold <= 0:
        return ordered

    result = []
    for marker in ordered:
        if result and marker["t"] - result[-1]["t"] <= threshold:
            # 保留较早的标记，继续与后续标记比较。
            continue
        result.append(marker)
    return result


def snap_to_frame(markers, fps):
    """把每个标记的 t 吸附到最近帧，返回新列表（不修改入参）。

    规则：
    - 帧时长 frame_ms = 1000 / fps，帧号 n = floor(t / frame_ms + 0.5)（四舍五入，
      0.5 帧向上取整），新时间 t' = n * frame_ms，单位仍为毫秒；
    - 吸附误差不超过 0.5 帧（测试以 1 帧为容差）；
    - fps 必须为有限正数，否则抛 MarkerError，不得因 fps=0 触发除零；
    - 多个标记吸附到同一帧时，保持原相对顺序。
    """
    _check_fps(fps)
    frame_ms = 1000 / fps

    result = []
    for marker in markers:
        frame = math.floor(marker["t"] / frame_ms + 0.5)
        snapped = _clone(marker)
        snapped["t"] = frame * frame_ms
        result.append(snapped)
    return result


def range_markers(markers, start, end):
    """返回时间落在 [start, end) 内的标记，左闭右开。

    规则：
    - 保留原列表顺序，不修改入参；
    - start > end 时抛 MarkerError；
    - start、end 单位毫秒，start 可取、end 不可取。
    """
    if start > end:
        raise MarkerError(f"非法区间: start={start} 大于 end={end}")

    # 左闭右开：start 可取，end 不可取；线性过滤以保留原列表顺序。
    return [_clone(m) for m in markers if start <= m["t"] < end]


def to_chapters(markers, duration):
    """把标记转换为章节列表 [{"start", "end", "title"}]，单位毫秒。

    规则：
    - 每个标记开启一章：start = 标记的 t，title = 标记的 label；
    - 第 i 章的 end = 第 i+1 个标记的 t，最后一章的 end = duration（片尾）；
    - 章节首尾相接，无空洞；
    - 空标记返回一整段 [{"start": 0, "end": duration, "title": "完整视频"}]；
    - duration 必须是有限正数，否则抛 MarkerError。
    """
    _check_duration(duration)

    ordered = sorted((_clone(m) for m in markers), key=lambda m: m["t"])
    if not ordered:
        return [{"start": 0, "end": duration, "title": "完整视频"}]

    chapters = []
    for i, marker in enumerate(ordered):
        start = marker["t"]
        # 最后一章的结束时间必须是片尾 duration，而不是最后一个标记的时间。
        end = ordered[i + 1]["t"] if i + 1 < len(ordered) else duration
        chapters.append({"start": start, "end": end, "title": marker["label"]})
    return chapters


def validate_markers(markers, duration):
    """校验标记，返回问题描述列表（无问题返回 []），按标记下标顺序排列。

    检查项：
    - 越界：t < 0 或 t > duration（毫秒），消息含 "越界"；
    - 重复：同一 label 出现多次，消息含 "重复"；
    - 空标签：label 为空或仅含空白字符，消息含 "空标签"。

    duration 必须是有限正数，否则抛 MarkerError。
    """
    _check_duration(duration)

    problems = []
    seen = set()
    for index, marker in enumerate(markers):
        t = marker["t"]
        label = marker["label"]

        if t < 0 or t > duration:
            problems.append(f"标记 {index} 越界: t={t}，有效范围 0..{duration}")

        if not isinstance(label, str) or not label.strip():
            problems.append(f"标记 {index} 空标签: {label!r}")
        elif label in seen:
            problems.append(f"标记 {index} 重复标签: {label!r}")
        else:
            seen.add(label)

    return problems


def marker_batch(timelines, config):
    """批量处理多条轨道，返回 {"tracks": [...], "chapters": [...]}。

    参数：
        timelines: 多条轨道的标记列表。
        config: 至少包含 {"fps": 帧率, "threshold": 合并阈值(ms), "duration": 时长(ms)}。

    处理流程：对每条轨道依次执行
    validate_markers -> merge_close(threshold) -> snap_to_frame(fps) -> to_chapters(duration)。
    tracks[i] 为第 i 条轨道处理后的标记列表，chapters[i] 为对应章节列表，
    顺序与 timelines 一致。

    异常与回滚：
    - 任一条轨道校验失败（validate_markers 返回非空）、config 缺字段、
      或 fps/duration 非法时，抛 MarkerError；
    - 抛出异常时不得修改 timelines 中的任何列表（整体回滚）；
    - 每条轨道使用独立的列表副本，轨道之间不得共享可变对象。
    """
    if not isinstance(config, dict):
        raise MarkerError("config 必须是字典")
    for key in ("fps", "threshold", "duration"):
        if key not in config:
            raise MarkerError(f"config 缺少字段: {key}")

    fps = config["fps"]
    threshold = config["threshold"]
    duration = config["duration"]

    # 先做全局配置校验，保证任何轨道都不会被处理到一半。
    _check_fps(fps)
    _check_duration(duration)
    if (
        not isinstance(threshold, numbers.Real)
        or isinstance(threshold, bool)
        or not math.isfinite(threshold)
    ):
        raise MarkerError(f"非法合并阈值: {threshold!r}")

    # 每条轨道各自复制一份独立的标记对象，轨道之间不共享任何可变对象。
    copies = [[_clone(marker) for marker in track] for track in timelines]

    # 先校验全部轨道，任一失败即整体拒绝，尚未产生任何输出副作用。
    for index, track in enumerate(copies):
        problems = validate_markers(track, duration)
        if problems:
            raise MarkerError(f"轨道 {index} 校验失败: " + "; ".join(problems))

    tracks = []
    chapters = []
    for track in copies:
        merged = merge_close(track, threshold)
        snapped = snap_to_frame(merged, fps)
        tracks.append(snapped)
        chapters.append(to_chapters(snapped, duration))

    return {"tracks": tracks, "chapters": chapters}
