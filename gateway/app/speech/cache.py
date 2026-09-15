"""Bounded, TTL'd disk cache for synthesized audio.

Per the root README's TTS-caching rule: key on a hash of
(text, voice, format, speed, model), expire entries after
`TTS_CACHE_TTL_SECONDS`, and never let the directory grow unbounded --
evict oldest files first once `TTS_CACHE_MAX_MB` is exceeded.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

from app.config import Settings


def cache_key(text: str, voice: str, audio_format: str, speed: float, model: str) -> str:
    raw = f"{model}|{voice}|{audio_format}|{speed}|{text}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class TtsCache:
    def __init__(self, settings: Settings, subdirectory: str | None = None):
        self.settings = settings
        base = Path(settings.tts_cache_dir)
        self.dir = base / subdirectory if subdirectory else base
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str, audio_format: str) -> Path:
        return self.dir / f"{key}.{audio_format}"

    def get(self, key: str, audio_format: str) -> bytes | None:
        path = self._path(key, audio_format)
        if not path.exists():
            return None
        age = time.time() - path.stat().st_mtime
        if age > self.settings.tts_cache_ttl_seconds:
            path.unlink(missing_ok=True)
            return None
        return path.read_bytes()

    def put(self, key: str, audio_format: str, data: bytes) -> None:
        path = self._path(key, audio_format)
        path.write_bytes(data)
        self._evict_if_needed()

    def _evict_if_needed(self) -> None:
        max_bytes = self.settings.tts_cache_max_mb * 1024 * 1024
        files = sorted(self.dir.glob("*"), key=lambda p: p.stat().st_mtime)
        total = sum(f.stat().st_size for f in files)
        idx = 0
        while total > max_bytes and idx < len(files):
            f = files[idx]
            total -= f.stat().st_size
            f.unlink(missing_ok=True)
            idx += 1
