"""scene-detect 异步任务结果契约测试。"""

from __future__ import annotations

import json

from scene_detect.schemas.scene import SceneBoundary, SceneMetadata, ScenePolicyDTO, WarningDTO
from scene_detect.services.tasks import run_detect_scenes


class TestDetectTaskContract:
    def test_task_result_includes_metadata_policy_and_warnings(self, monkeypatch, tmp_path):
        captured_update_calls: list[tuple[str, dict]] = []
        video_path = tmp_path / "sample.mp4"
        video_path.write_bytes(b"fake")

        def fake_update_job(job_id: str, **kwargs):
            captured_update_calls.append((job_id, kwargs))

        def fake_detect_scenes(*args, **kwargs):
            return (
                [
                    SceneBoundary(
                        scene_index=0,
                        start_frame=0,
                        end_frame=24,
                        start_time=0.0,
                        end_time=1.0,
                    )
                ],
                SceneMetadata(
                    fps=25.0,
                    total_frames=25,
                    duration=1.0,
                    width=1280,
                    height=720,
                ),
                ScenePolicyDTO(
                    threshold=28.0,
                    min_scene_len_sec=2.5,
                    max_scene_count=20,
                ),
                [
                    WarningDTO(
                        code="short_scenes_merged",
                        message="短场景合并: 2 -> 1",
                        scope="scenes",
                    )
                ],
            )

        monkeypatch.setattr("scene_detect.services.tasks.update_job", fake_update_job)
        monkeypatch.setattr("scene_detect.services.detector.detect_scenes", fake_detect_scenes)

        scenes = run_detect_scenes.call_local(
            "job-1",
            str(video_path),
            threshold=27.0,
            max_scenes=80,
            scale_width=640,
            decode_threads=0,
        )

        assert scenes == [
            {
                "scene_index": 0,
                "start_frame": 0,
                "end_frame": 24,
                "start_time": 0.0,
                "end_time": 1.0,
            }
        ]
        assert len(captured_update_calls) == 2

        _, final_update = captured_update_calls[-1]
        assert final_update["status"] == "succeeded"

        result = final_update["result_json"]
        assert result["metadata"] == {
            "fps": 25.0,
            "total_frames": 25,
            "duration": 1.0,
            "width": 1280,
            "height": 720,
        }
        assert result["policy"] == {
            "threshold": 28.0,
            "min_scene_len_sec": 2.5,
            "max_scene_count": 20,
        }
        assert result["warnings"] == [
            {
                "code": "short_scenes_merged",
                "message": "短场景合并: 2 -> 1",
                "scope": "scenes",
                "target_id": "",
            }
        ]
        assert result["scenes"] == scenes

        json.dumps(result, ensure_ascii=False)
