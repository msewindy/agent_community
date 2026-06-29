"""ASR routing: Chinese → FunASR, English → faster-whisper."""

from __future__ import annotations

import os
import re
from pathlib import Path

# Keep model caches off crowded /home when possible
os.environ.setdefault("HF_HOME", "/tmp/agent_voice_hf")
os.environ.setdefault("MODELSCOPE_CACHE", "/tmp/agent_voice_modelscope")


def _cjk_ratio(text: str) -> float:
    if not text:
        return 0.0
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    return cjk / max(len(text), 1)


class ASRRouter:
    """Lazy-load backends; route by detected or hinted language."""

    def __init__(
        self,
        *,
        whisper_size: str = "base",
        funasr_model: str = "paraformer-zh",
        device: str = "auto",
    ) -> None:
        self.whisper_size = whisper_size
        self.funasr_model = funasr_model
        self.device = device
        self._whisper = None
        self._funasr = None

    def _whisper_device(self) -> tuple[str, str]:
        import torch

        if self.device == "cpu":
            return "cpu", "int8"
        if self.device == "cuda":
            return "cuda", "float16"
        if torch.cuda.is_available():
            return "cuda", "float16"
        return "cpu", "int8"

    def _get_whisper(self):
        if self._whisper is None:
            from faster_whisper import WhisperModel

            dev, ctype = self._whisper_device()
            self._whisper = WhisperModel(self.whisper_size, device=dev, compute_type=ctype)
        return self._whisper

    def _get_funasr(self):
        if self._funasr is None:
            from funasr import AutoModel

            self._funasr = AutoModel(model=self.funasr_model, disable_update=True)
        return self._funasr

    def detect_language(self, audio_path: str | Path) -> str:
        """Return 'zh' or 'en' using whisper language detection."""
        model = self._get_whisper()
        _, info = model.transcribe(
            str(audio_path),
            language=None,
            beam_size=1,
            vad_filter=False,
        )
        lang = (info.language or "en").lower()
        if lang.startswith("zh") or lang in ("yue", "ja", "ko"):
            # ja/ko mis-detect possible; refine with transcript ratio later
            return "zh"
        return "en"

    def transcribe(
        self,
        audio_path: str | Path,
        *,
        language: str | None = None,
    ) -> tuple[str, str]:
        """Transcribe file; returns (text, language_used)."""
        path = Path(audio_path)
        lang = language or self.detect_language(path)
        if lang == "zh":
            text = self._transcribe_zh(path)
            if _cjk_ratio(text) < 0.15:
                # Fallback if FunASR garbled or wrong route
                text, lang = self._transcribe_en(path), "en"
            return text.strip(), lang
        text, detected = self._transcribe_en(path)
        return text.strip(), detected

    def _transcribe_zh(self, path: Path) -> str:
        model = self._get_funasr()
        res = model.generate(input=str(path), batch_size=1)
        if not res:
            return ""
        item = res[0]
        if isinstance(item, dict):
            return str(item.get("text", ""))
        return str(item)

    def _transcribe_en(self, path: Path) -> tuple[str, str]:
        model = self._get_whisper()
        segments, info = model.transcribe(
            str(path),
            language="en",
            beam_size=1,
            vad_filter=True,
        )
        text = "".join(s.text for s in segments)
        return text, (info.language or "en")
