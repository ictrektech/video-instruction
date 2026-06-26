"""Unit tests for JWT token generation and validation."""

from app.core.security.jwt import decode_token, generate_token


class TestJWT:
    def test_generate_and_decode(self) -> None:
        token = generate_token(1, "testuser")
        payload = decode_token(token)
        assert payload is not None
        assert payload.userId == 1
        assert payload.username == "testuser"

    def test_invalid_token_returns_none(self) -> None:
        payload = decode_token("invalid-token")
        assert payload is None
