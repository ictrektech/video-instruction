"""scene-detect 管道配置与工具函数单元测试。"""

from __future__ import annotations

import pytest

from scene_detect.schemas.scene import SceneBoundary
from scene_detect.services.detector import (
    _boundary_from_range,
    _frame_to_time,
    _full_video_boundary,
    _resolve_scene_settings,
    _scaled_size,
    merge_short_scenes,
    select_scene_policy,
    shrink_to_max_scene_count,
)
from scene_detect.utils import coalesce, resolve_video_path


class TestScaledSize:
    def test_downscale_16_9(self):
        assert _scaled_size(1920, 1080, 640) == (640, 360)
        assert _scaled_size(3840, 2160, 640) == (640, 360)
        assert _scaled_size(1280, 720, 640) == (640, 360)

    def test_no_upscale(self):
        assert _scaled_size(320, 180, 640) == (320, 180)
        assert _scaled_size(640, 360, 640) == (640, 360)

    def test_scale_disabled(self):
        assert _scaled_size(1920, 1080, 0) == (1920, 1080)
        assert _scaled_size(1920, 1080, -1) == (1920, 1080)

    def test_height_even(self):
        # 1280x720 @ 480 → 480x270（已为偶数）
        assert _scaled_size(1280, 720, 480) == (480, 270)
        w, h = _scaled_size(1920, 1081, 640)
        assert w == 640
        assert h % 2 == 0


class TestCoalesce:
    def test_none_uses_default(self):
        assert coalesce(None, 640) == 640

    def test_keeps_zero(self):
        assert coalesce(0, 640) == 0

    def test_keeps_false(self):
        assert coalesce(False, True) is False

    def test_keeps_value(self):
        assert coalesce(4, 2) == 4


class TestBoundaryHelpers:
    def test_full_video(self):
        b = _full_video_boundary(100, 25.0)
        assert b.scene_index == 0
        assert b.start_frame == 0
        assert b.end_frame == 99
        assert b.start_time == 0.0
        assert b.end_time == _frame_to_time(100, 25.0)

    def test_half_open_end(self):
        b = _boundary_from_range(1, 10, 50, 25.0)
        assert b.start_frame == 10
        assert b.end_frame == 49
        assert b.start_time == 0.4
        assert b.end_time == 2.0


class TestResolveVideoPath:
    def test_absolute(self):
        assert resolve_video_path("/data/a.mp4", "/photos") == "/data/a.mp4"

    def test_relative(self):
        assert resolve_video_path("a/b.mp4", "/photos") == "/photos/a/b.mp4"


class TestScenePolicy:
    @pytest.mark.parametrize(
        ("duration", "expected"),
        [
            (179.999, (28.0, 2.5, 20)),
            (180.0, (29.0, 3.5, 40)),
            (600.0, (30.0, 5.0, 80)),
            (1800.0, (31.0, 8.0, 120)),
            (5400.0, (32.0, 10.0, 200)),
        ],
    )
    def test_select_policy_at_duration_boundaries(self, duration, expected):
        policy = select_scene_policy(duration)
        assert (policy.threshold, policy.min_scene_len_sec, policy.max_scene_count) == expected

    def test_resolve_uses_duration_policy_by_default(self):
        policy, threshold, max_scenes = _resolve_scene_settings(7200.0, None, None)

        assert threshold == policy.threshold == 32.0
        assert max_scenes == policy.max_scene_count == 200

    def test_resolve_explicit_values_override_duration_policy(self):
        policy, threshold, max_scenes = _resolve_scene_settings(7200.0, 25.0, 42)

        assert policy.threshold == 32.0
        assert threshold == 25.0
        assert max_scenes == 42

    def test_resolve_preserves_zero_max_scenes(self):
        _, _, max_scenes = _resolve_scene_settings(7200.0, None, 0)

        assert max_scenes == 0


class TestScenePostProcess:
    @staticmethod
    def _scene(idx: int, start: float, end: float) -> SceneBoundary:
        return SceneBoundary(
            scene_index=idx,
            start_frame=int(start * 25),
            end_frame=max(int(end * 25) - 1, int(start * 25)),
            start_time=start,
            end_time=end,
        )

    def test_merge_short_middle_scene_into_next(self):
        scenes = [
            self._scene(0, 0.0, 3.0),
            self._scene(1, 3.0, 3.2),
            self._scene(2, 3.2, 8.0),
        ]

        merged = merge_short_scenes(scenes, 0.5)

        assert len(merged) == 2
        assert merged[0].start_time == 0.0
        assert merged[0].end_time == 3.0
        assert merged[1].start_time == 3.0
        assert merged[1].end_time == 8.0
        assert [scene.scene_index for scene in merged] == [0, 1]

    def test_merge_short_last_scene_into_previous(self):
        scenes = [
            self._scene(0, 0.0, 5.0),
            self._scene(1, 5.0, 5.2),
        ]

        merged = merge_short_scenes(scenes, 0.5)

        assert len(merged) == 1
        assert merged[0].start_time == 0.0
        assert merged[0].end_time == 5.2

    def test_shrink_to_max_scene_count_prefers_shortest(self):
        scenes = [
            self._scene(0, 0.0, 5.0),
            self._scene(1, 5.0, 5.4),
            self._scene(2, 5.4, 10.0),
            self._scene(3, 10.0, 20.0),
        ]

        shrunk = shrink_to_max_scene_count(scenes, 3)

        assert len(shrunk) == 3
        assert shrunk[1].start_time == 5.0
        assert shrunk[1].end_time == 10.0
        assert [scene.scene_index for scene in shrunk] == [0, 1, 2]
