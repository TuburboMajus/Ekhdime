"""Shared audio upload validation for /api/v1/query/audio and /api/v1/stt.

Was duplicated between app/api/query.py and app/api/audio.py -- consolidated
here after that duplication let a real bug slip through (see
`_GENERIC_CONTENT_TYPES` below).
"""

from __future__ import annotations

from app.api.errors import ApiError

AUDIO_MIME_WHITELIST = {
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp4",
    "audio/m4a",
    "audio/x-m4a",
    "audio/aac",
    "audio/ogg",
    "audio/webm",
}

# Generic/absent content types many HTTP multipart clients send when they
# don't bother inferring one from the filename -- confirmed in Dart's `http`
# package source (multipart_file.dart), whose `MultipartFile.fromBytes`
# defaults to exactly this and has an unimplemented
# `// TODO: Infer the content-type from the filename`. Every real-device
# audio upload from the mobile app arrived this way and was rejected here
# before ever reaching Whisper -- found by checking the gateway's own logs
# against a live recording. Treat these as "unknown", not "invalid": let
# Whisper's own ffmpeg-based decoding be the actual judge of whether the
# bytes are valid audio, rather than gatekeeping on a client-declared MIME
# type that's known to often be absent or generic.
_GENERIC_CONTENT_TYPES = {"application/octet-stream", ""}


def validate_audio_content_type(content_type: str | None) -> None:
    """Raises ApiError(INVALID_REQUEST) only for a content type that
    positively identifies itself as something other than audio. A missing
    or generic content type is allowed through.
    """
    if not content_type or content_type in _GENERIC_CONTENT_TYPES:
        return
    if content_type not in AUDIO_MIME_WHITELIST:
        raise ApiError(
            "INVALID_REQUEST",
            f"Unsupported audio content type: {content_type}",
            status_code=400,
        )
