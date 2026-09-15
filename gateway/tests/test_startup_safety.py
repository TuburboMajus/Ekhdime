import pytest

from app.main import _validate_startup_safety
from tests.conftest import make_settings


def test_refuses_to_start_with_unsafe_token_in_production():
    settings = make_settings(environment="production", gateway_api_token="change-me")
    with pytest.raises(RuntimeError, match="GATEWAY_API_TOKEN"):
        _validate_startup_safety(settings)


def test_allows_unsafe_token_in_development():
    settings = make_settings(environment="development", gateway_api_token="change-me")
    _validate_startup_safety(settings)  # must not raise


def test_allows_strong_token_in_production():
    settings = make_settings(environment="production", gateway_api_token="a-strong-random-token")
    _validate_startup_safety(settings)  # must not raise
