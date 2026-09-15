"""Locks in a real bug found against a live device: Dart's `http` package
defaults every multipart upload to `application/octet-stream` when no
content type is set (confirmed in its source, which has never implemented
filename-based inference), and this gateway used to hard-reject that,
silently breaking every voice query from the mobile app before it ever
reached Whisper.
"""

import pytest

from app.api.errors import ApiError
from app.speech.validation import validate_audio_content_type


def test_accepts_generic_octet_stream():
    validate_audio_content_type("application/octet-stream")  # must not raise


def test_accepts_missing_content_type():
    validate_audio_content_type(None)  # must not raise
    validate_audio_content_type("")  # must not raise


def test_accepts_known_audio_types():
    for content_type in ("audio/wav", "audio/mp4", "audio/m4a", "audio/mpeg", "audio/aac"):
        validate_audio_content_type(content_type)  # must not raise


def test_rejects_explicitly_non_audio_type():
    with pytest.raises(ApiError) as exc_info:
        validate_audio_content_type("text/plain")
    assert exc_info.value.code == "INVALID_REQUEST"
    assert exc_info.value.status_code == 400


def test_rejects_image_type():
    with pytest.raises(ApiError):
        validate_audio_content_type("image/png")
