"""Best-effort answer-text language -> Kokoro voice mapping.

Kokoro's voices are each single-language (an "ff_siwis" voice speaking
French text sounds natural; the same text spoken by an English voice like
"af_heart" is badly mispronounced -- found live: the assistant answering in
French still used the English default voice, and the result was
unintelligible). Nothing upstream tells us what language a given answer is
in -- the model just answers in whatever language the user asked in, and
neither `/query` nor `/query/audio` take a per-message voice from the
mobile app today -- so the answer text itself is the only signal available.
"""

from __future__ import annotations

from langdetect import LangDetectException, detect

# Kokoro-FastAPI v0.9.0's voice list (GET /v1/audio/voices on a live
# container) groups voices by a language-prefix convention: af_/am_ and
# bf_/bm_ are both English (American/British), so English needs no entry
# here -- it's whatever `default_voice` already is. Only languages Kokoro
# has a *distinct* voice for are worth detecting.
_VOICE_BY_LANGUAGE = {
    "fr": "ff_siwis",
    "es": "ef_dora",
    "it": "if_sara",
    "pt": "pf_dora",
    "hi": "hf_alpha",
    "ja": "jf_alpha",
    "zh-cn": "zf_xiaobei",
    "zh-tw": "zf_xiaobei",
}


def voice_for_text(text: str, default_voice: str) -> str:
    """`default_voice` covers English, any language Kokoro has no distinct
    voice for, and a failed/ambiguous detection -- never worth failing a
    whole TTS request over a language guess."""
    try:
        language = detect(text)
    except LangDetectException:
        return default_voice
    return _VOICE_BY_LANGUAGE.get(language, default_voice)
