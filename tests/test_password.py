"""Unit tests for password hashing."""

from app.core.security.password import hash_password, verify_password


class TestPassword:
    def test_hash_and_verify(self) -> None:
        raw = "MyP@ssw0rd!"
        hashed = hash_password(raw)
        assert hashed != raw
        assert hashed.startswith("$2b$")
        assert verify_password(raw, hashed)

    def test_wrong_password_fails(self) -> None:
        hashed = hash_password("correct-password")
        assert not verify_password("wrong-password", hashed)

    def test_same_password_different_hash(self) -> None:
        """Same password produces different hashes each time (salt)."""
        pwd = "same-password"
        h1 = hash_password(pwd)
        h2 = hash_password(pwd)
        assert h1 != h2
        assert verify_password(pwd, h1)
        assert verify_password(pwd, h2)
