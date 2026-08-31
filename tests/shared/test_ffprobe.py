"""shared.core.ffprobe URL 支持单元测试。"""

from __future__ import annotations

import json

import pytest

from shared.core import ffprobe


class _FakeResult:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _probe_stdout() -> str:
    return json.dumps(
        {
            "streams": [
                {
                    "codec_type": "video",
                    "width": 1280,
                    "height": 720,
                    "avg_frame_rate": "25/1",
                    "r_frame_rate": "25/1",
                    "duration": "10.0",
                    "nb_frames": "250",
                    "codec_name": "h264",
                }
            ],
            "format": {"duration": "10.0", "bit_rate": "1000000"},
        }
    )


def test_query_video_metadata_adds_network_options_for_url(monkeypatch):
    captured: dict[str, list[str]] = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _FakeResult(stdout=_probe_stdout())

    monkeypatch.setattr(ffprobe.subprocess, "run", fake_run)

    url = "http://host/v.mp4?token=abc"
    ffprobe.query_video_metadata(url)

    cmd = captured["cmd"]
    url_index = cmd.index(url)
    assert "-rw_timeout" in cmd
    assert "30000000" in cmd
    assert "-reconnect" in cmd
    assert "-reconnect_streamed" in cmd
    assert cmd.index("-rw_timeout") < url_index


def test_query_video_metadata_does_not_add_network_options_for_local(monkeypatch):
    captured: dict[str, list[str]] = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _FakeResult(stdout=_probe_stdout())

    monkeypatch.setattr(ffprobe.subprocess, "run", fake_run)

    ffprobe.query_video_metadata("/data/v.mp4")

    assert "-rw_timeout" not in captured["cmd"]
    assert "-reconnect" not in captured["cmd"]


def test_query_video_metadata_raises_on_ffprobe_failure(monkeypatch):
    def fake_run(cmd, **kwargs):
        return _FakeResult(returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr(ffprobe.subprocess, "run", fake_run)

    try:
        ffprobe.query_video_metadata("/data/v.mp4")
    except RuntimeError as exc:
        assert "ffprobe 失败" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_query_video_metadata_redacts_token_in_ffprobe_error(monkeypatch):
    token = "nk_secret123"
    url = f"http://host/v.mp4?token={token}"

    def fake_run(cmd, **kwargs):
        return _FakeResult(returncode=1, stdout="", stderr=f"failed: {url}")

    monkeypatch.setattr(ffprobe.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError) as exc_info:
        ffprobe.query_video_metadata(url)

    assert token not in str(exc_info.value)
    assert "token=***" in str(exc_info.value)
