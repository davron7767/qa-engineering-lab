import pytest
from pydantic import ValidationError

from app.config import PLACEHOLDER_SECRET, Settings
from app.security import csrf_token, csrf_valid, hash_password, hash_token, verify_password
from app.services.rules import OrderLine
from app.web.routes import parse_quantities, safe_next


class TestPasswords:
    def test_hash_is_not_plaintext_and_verifies(self) -> None:
        hashed = hash_password("correct horse battery")
        assert "correct horse" not in hashed
        assert hashed.startswith("$argon2")
        assert verify_password("correct horse battery", hashed)

    def test_wrong_password_and_missing_hash_fail(self) -> None:
        hashed = hash_password("correct horse battery")
        assert not verify_password("wrong", hashed)
        assert not verify_password("anything", None)
        assert not verify_password("anything", "not-a-hash")


def test_token_hash_is_stable_sha256() -> None:
    assert hash_token("abc") == hash_token("abc")
    assert len(hash_token("abc")) == 64


class TestCsrf:
    def test_round_trip(self) -> None:
        token = csrf_token("k" * 32, "session-1")
        assert csrf_valid("k" * 32, "session-1", token)

    @pytest.mark.parametrize("submitted", [None, "", "deadbeef"])
    def test_rejects_missing_or_wrong(self, submitted: str | None) -> None:
        assert not csrf_valid("k" * 32, "session-1", submitted)

    def test_bound_to_session(self) -> None:
        assert not csrf_valid("k" * 32, "session-2", csrf_token("k" * 32, "session-1"))


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("/orders", "/orders"),
        ("/orders?page=2", "/orders?page=2"),
        ("//evil.example", "/products"),
        ("https://evil.example", "/products"),
        ("/\\evil.example", "/products"),
        (None, "/products"),
    ],
)
def test_safe_next_blocks_open_redirects(target: str | None, expected: str) -> None:
    assert safe_next(target) == expected


class TestParseQuantities:
    def test_blank_and_zero_are_skipped(self) -> None:
        lines, errors = parse_quantities({"qty_1": "2", "qty_2": "", "qty_3": "0", "csrf": "x"})
        assert lines == [OrderLine(1, 2)]
        assert errors == []

    @pytest.mark.parametrize(
        ("raw", "message"),
        [
            ("1.5", "not a whole number"),
            ("abc", "not a whole number"),
            ("-1", "at least 1"),
            ("1001", "must not exceed 1000"),
        ],
    )
    def test_invalid_values(self, raw: str, message: str) -> None:
        lines, errors = parse_quantities({"qty_1": raw})
        assert lines == []
        assert message in errors[0]

    def test_nothing_selected(self) -> None:
        assert parse_quantities({})[1] == ["Select at least one product by entering a quantity."]


class TestProductionGuards:
    def test_placeholder_secret_refused_in_production(self) -> None:
        with pytest.raises(ValidationError, match="SECRET_KEY"):
            Settings(app_env="production", secret_key=PLACEHOLDER_SECRET, _env_file=None)

    def test_defect_mode_refused_in_production(self) -> None:
        with pytest.raises(ValidationError, match="DEFECT_MODE"):
            Settings(
                app_env="production", secret_key="x" * 40, defect_mode="wrong_total", _env_file=None
            )

    def test_test_hooks_never_active_in_production(self) -> None:
        settings = Settings(
            app_env="production", secret_key="x" * 40, enable_test_hooks=True, _env_file=None
        )
        assert settings.test_hooks_active is False
