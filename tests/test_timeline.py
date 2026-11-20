"""video-timeline-marker 验收测试（15 个，初始全部为红）。"""

import copy

import pytest

from marker.timeline import (
    MarkerError,
    insert_marker,
    marker_batch,
    merge_close,
    move_marker,
    range_markers,
    snap_to_frame,
    to_chapters,
    validate_markers,
)


def mk(t, label, color="#4e79a7"):
    """构造一个标记。"""
    return {"t": t, "label": label, "color": color}


def labels(markers):
    """取出标记标签序列。"""
    return [m["label"] for m in markers]


# ---------------------------------------------------------------------------
# 10 个缺陷各 1 条
# ---------------------------------------------------------------------------


def test_insert_marker_keeps_insertion_order_for_same_time():
    """缺陷 1：插入必须稳定，同一时间按插入顺序，不得用不稳定的 sort(key=t)。"""
    markers = [mk(1000, "a"), mk(3000, "b")]
    result = insert_marker(markers, mk(2000, "c"))
    assert labels(result) == ["a", "c", "b"]

    same_time = [mk(2000, "x"), mk(2000, "y")]
    result = insert_marker(same_time, mk(2000, "z"))
    assert labels(result) == ["x", "y", "z"]
    assert labels(markers) == ["a", "b"]


def test_move_marker_resorts_timeline():
    """缺陷 2：移动后必须重新排序，否则时间线错乱；越界索引抛 MarkerError。"""
    markers = [mk(1000, "a"), mk(2000, "b"), mk(3000, "c")]
    result = move_marker(markers, 0, 3500)
    assert labels(result) == ["b", "c", "a"]
    assert [m["t"] for m in result] == [2000, 3000, 3500]
    assert labels(markers) == ["a", "b", "c"]

    with pytest.raises(MarkerError):
        move_marker(markers, 3, 1000)


def test_merge_close_uses_given_threshold():
    """缺陷 3：合并必须使用传入阈值，不能写死 1 秒。"""
    markers = [mk(0, "intro"), mk(1500, "intro-2"), mk(4000, "main")]
    result = merge_close(markers, 2000)
    assert [m["t"] for m in result] == [0, 4000]
    assert labels(result) == ["intro", "main"]


def test_snap_to_frame_uses_nearest_frame():
    """缺陷 4：吸附到最近帧，向下取整会偏半帧。"""
    markers = [mk(149, "a"), mk(160, "b"), mk(349, "c")]
    result = snap_to_frame(markers, 10)  # 1 帧 = 100 ms
    assert [m["t"] for m in result] == [100, 200, 300]
    assert labels(result) == ["a", "b", "c"]


def test_range_markers_is_left_closed_right_open():
    """缺陷 5：范围查询左闭右开，闭区间会在边界重复。"""
    markers = [mk(1000, "a"), mk(2000, "b"), mk(3000, "c")]
    assert labels(range_markers(markers, 1000, 3000)) == ["a", "b"]
    assert labels(range_markers(markers, 1001, 3000)) == ["b"]


def test_to_chapters_last_chapter_reaches_duration():
    """缺陷 6：最后一章必须到片尾 duration，不能用最后一个标记收尾。"""
    markers = [mk(0, "intro"), mk(5000, "demo"), mk(12000, "end")]
    chapters = to_chapters(markers, 20000)
    assert len(chapters) == 3
    assert chapters[-1] == {"start": 12000, "end": 20000, "title": "end"}


def test_validate_flags_marker_past_duration():
    """缺陷 7：标记超出时长必须报越界。"""
    markers = [mk(1000, "ok"), mk(10500, "late")]
    problems = validate_markers(markers, 10000)
    assert len(problems) == 1
    assert "越界" in problems[0]


def test_validate_flags_duplicate_labels():
    """缺陷 8：重复标签必须报错，否则导出后重名。"""
    markers = [mk(1000, "intro"), mk(2000, "intro")]
    problems = validate_markers(markers, 10000)
    assert len(problems) == 1
    assert "重复" in problems[0]


def test_marker_batch_keeps_tracks_isolated():
    """缺陷 9：批量处理各轨必须使用独立列表，不能共用同一标记列表。"""
    track_a = [mk(1000, "a1"), mk(5000, "a2")]
    track_b = [mk(2000, "b1")]
    config = {"fps": 10, "threshold": 0, "duration": 10000}

    result = marker_batch([track_a, track_b], config)
    assert len(result["tracks"]) == 2
    assert result["tracks"][0] is not result["tracks"][1]
    assert result["tracks"][0] is not track_a
    assert labels(track_a) == ["a1", "a2"]

    result["tracks"][0].append(mk(9000, "extra"))
    assert labels(result["tracks"][1]) == ["b1"]
    assert labels(track_a) == ["a1", "a2"]


def test_snap_to_frame_rejects_zero_fps():
    """缺陷 10：fps=0 必须校验并抛 MarkerError，不能除零。"""
    with pytest.raises(MarkerError):
        snap_to_frame([mk(1000, "a")], 0)


# ---------------------------------------------------------------------------
# 5 条组合测试
# ---------------------------------------------------------------------------


def test_to_chapters_empty_markers_covers_whole_video():
    """空标记必须生成一个覆盖整段的章节。"""
    assert to_chapters([], 8000) == [{"start": 0, "end": 8000, "title": "完整视频"}]


def test_merge_close_zero_threshold_keeps_all():
    """threshold=0 时不合并任何标记。"""
    markers = [mk(0, "a"), mk(1, "b"), mk(2, "c")]
    result = merge_close(markers, 0)
    assert labels(result) == ["a", "b", "c"]
    assert [m["t"] for m in result] == [0, 1, 2]


def test_marker_batch_rejects_zero_fps_and_rolls_back():
    """批量配置 fps=0 必须整体抛 MarkerError，且回滚不修改入参。"""
    track = [mk(1000, "a")]
    before = copy.deepcopy([track])
    with pytest.raises(MarkerError):
        marker_batch([track], {"fps": 0, "threshold": 0, "duration": 10000})
    assert [track] == before


def test_chapters_are_contiguous_without_gaps():
    """章节必须首尾相接、无空洞，且从 0 附近的第一个标记到片尾。"""
    markers = [mk(0, "a"), mk(4000, "b"), mk(9000, "c")]
    chapters = to_chapters(markers, 15000)
    assert chapters[0]["start"] == 0
    for prev, nxt in zip(chapters, chapters[1:]):
        assert prev["end"] == nxt["start"]
    assert chapters[-1]["end"] == 15000


def test_marker_batch_preserves_track_order_on_success():
    """批量全部成功时，输出轨道与章节顺序必须与输入一致。"""
    track0 = [mk(1000, "intro"), mk(5000, "main")]
    track1 = [mk(2000, "solo")]
    config = {"fps": 10, "threshold": 0, "duration": 10000}

    result = marker_batch([track0, track1], config)
    assert labels(result["tracks"][0]) == ["intro", "main"]
    assert labels(result["tracks"][1]) == ["solo"]
    assert [c["title"] for c in result["chapters"][0]] == ["intro", "main"]
    assert result["chapters"][1] == [{"start": 2000, "end": 10000, "title": "solo"}]
