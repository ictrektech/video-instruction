"""shared.utils.video_source 单元测试。"""

from __future__ import annotations

from shared.utils.video_source import (
    ffmpeg_network_options,
    is_http_url,
    redact_url,
    resolve_video_path,
    video_identity,
)


def test_is_http_url_recognizes_http_and_https():
    assert is_http_url("http://host/v.mp4")
    assert is_http_url("https://host/v.mp4")
    assert not is_http_url("/data/v.mp4")
    assert not is_http_url("relative/v.mp4")


def test_resolve_video_path_keeps_url_untouched():
    url = "http://nowen-video:8080/api/stream/abc/direct?token=xxx"
    assert resolve_video_path(url, "/data") == url


def test_resolve_video_path_keeps_absolute_local_path():
    assert resolve_video_path("/data/a.mp4", "/photos") == "/data/a.mp4"


def test_resolve_video_path_joins_relative_path():
    assert resolve_video_path("a/b.mp4", "/photos") == "/photos/a/b.mp4"


def test_redact_url_masks_token_query_value():
    url = "http://host/api/stream/abc/direct?token=secret123&x=1"
    redacted = redact_url(url)
    assert "secret123" not in redacted
    assert "token=***" in redacted
    assert "x=1" in redacted


def test_redact_url_only_masks_token_query_key():
    url = "http://host/v.mp4?sign=abc&key=def&token=ghi"
    redacted = redact_url(url)
    assert "abc" in redacted
    assert "def" in redacted
    assert "ghi" not in redacted
    assert "token=***" in redacted


def test_redact_url_masks_userinfo_credentials():
    """user:pass@host 里的密码必须抹掉，否则会进日志、错误明细和调用方数据库。"""
    redacted = redact_url("https://alice:s3cret@llm.example.com/v1")

    assert "s3cr3t" not in redacted
    assert "alice" not in redacted
    assert redacted == "https://***@llm.example.com/v1"


def test_redact_url_keeps_host_and_port_without_credentials():
    assert redact_url("http://gw:8080/v1") == "http://gw:8080/v1"


def test_redact_url_ignores_at_sign_outside_userinfo():
    """邮箱式的 @ 在路径/query 里很常见，不能被当成 userinfo 一起抹掉。"""
    assert redact_url("http://host/v.mp4?to=a@b") == "http://host/v.mp4?to=a@b"
    assert redact_url("http://host/mail/a@b/v.mp4") == "http://host/mail/a@b/v.mp4"


def test_redact_url_keeps_local_path_unchanged():
    assert redact_url("/data/v.mp4") == "/data/v.mp4"


def test_ffmpeg_network_options_contains_expected_parameters():
    options = ffmpeg_network_options()
    assert "-rw_timeout" in options
    assert "30000000" in options
    assert "-reconnect" in options
    assert "-reconnect_streamed" in options
    assert "-reconnect_delay_max" in options


def test_video_identity_uses_url_hash_for_http():
    url = "http://host/v.mp4?token=abc"
    ident = video_identity(url)
    assert isinstance(ident, str)
    assert len(ident) == 64
    # 同一个 URL 即使 token 变化，身份也应稳定
    assert video_identity("http://host/v.mp4?token=abc") == video_identity(
        "http://host/v.mp4?token=def"
    )
