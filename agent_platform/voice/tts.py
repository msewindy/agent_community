"""Edge-TTS synthesis (M1 baseline)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import edge_tts


async def synthesize_to_file(
    text: str,
    output_path: str | Path,
    *,
    voice: str,
) -> Path:
    """Write MP3 (or edge-tts default container) to *output_path*."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    communicate = edge_tts.Communicate(text, voice=voice)
    await communicate.save(str(out))
    return out


def synthesize_to_file_sync(
    text: str,
    output_path: str | Path,
    *,
    voice: str,
) -> Path:
    return asyncio.run(synthesize_to_file(text, output_path, voice=voice))


def voice_for_language(lang: str, *, zh_voice: str, en_voice: str) -> str:
    return zh_voice if lang.startswith("zh") else en_voice
