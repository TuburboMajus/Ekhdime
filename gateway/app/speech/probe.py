"""Best-effort audio duration probing via `ffprobe`.

Used only for the `MAX_AUDIO_DURATION_SECONDS` validation in
app/api/query.py (README section 23). Writes to a randomly-named temp file
(never trusting the client's filename/extension) and always deletes it
afterwards, per that same section's rules. `ffprobe` ships with the `ffmpeg`
package installed in the gateway image (see gateway/Dockerfile).
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


async def probe_duration_seconds(data: bytes, timeout: float = 10.0) -> float | None:
    fd, path_str = tempfile.mkstemp(prefix="gateway-audio-", suffix=".bin")
    path = Path(path_str)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)

        try:
            proc = await asyncio.create_subprocess_exec(
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except FileNotFoundError:
            logger.warning("ffprobe_not_found")
            return None

        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return None

        try:
            return float(stdout.decode().strip())
        except ValueError:
            return None
    finally:
        path.unlink(missing_ok=True)
