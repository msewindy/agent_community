"""DashScope Paraformer ASR for student chat (short utterances, zh-CN)."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


class AsrError(RuntimeError):
    pass


def _api_key() -> str:
    key = (os.environ.get("DASHSCOPE_API_KEY") or "").strip()
    if not key:
        raise AsrError("DASHSCOPE_API_KEY 未配置（~/.hermes/.env）")
    return key


def convert_to_wav(src: Path, *, sample_rate: int = 16000) -> Path:
    """webm/ogg/mp4 → wav（需系统 ffmpeg）。"""
    if shutil.which("ffmpeg") is None:
        raise AsrError("服务器未安装 ffmpeg，无法转换录音格式")
    fd, out = tempfile.mkstemp(prefix="asr_", suffix=".wav")
    os.close(fd)
    out_path = Path(out)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "wav",
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        out_path.unlink(missing_ok=True)
        detail = (proc.stderr or proc.stdout or "").strip()[-400:]
        raise AsrError(f"ffmpeg 转换失败: {detail}")
    return out_path


def _sentence_text(sent) -> str:
    if sent is None:
        return ""
    if isinstance(sent, list):
        return "".join(_sentence_text(item) for item in sent)
    if isinstance(sent, dict):
        return str(sent.get("text") or "")
    return str(sent).strip()


class _CollectCallback:
    """DashScope Recognition 回调：收集最终句子。"""

    def __init__(self) -> None:
        self.parts: list[str] = []
        self.error_message: str | None = None

    def on_open(self) -> None:
        return None

    def on_complete(self) -> None:
        return None

    def on_close(self) -> None:
        return None

    def on_error(self, result) -> None:
        self.error_message = getattr(result, "message", None) or str(result)

    def on_event(self, result) -> None:
        if not hasattr(result, "get_sentence"):
            return
        text = _sentence_text(result.get_sentence())
        if text:
            self.parts.append(text)


def transcribe_wav_file(path: Path, *, sample_rate: int = 16000) -> str:
    _api_key()
    try:
        from http import HTTPStatus

        from dashscope.audio.asr import Recognition
        from dashscope.audio.asr.recognition import RecognitionCallback
    except ImportError as exc:
        raise AsrError("未安装 dashscope，请 pip install dashscope") from exc

    class _CB(_CollectCallback, RecognitionCallback):
        pass

    callback = _CB()
    recognition = Recognition(
        model="paraformer-realtime-v2",
        callback=callback,
        format="wav",
        sample_rate=sample_rate,
        language_hints=["zh", "en"],
    )
    result = recognition.call(str(path))
    status = getattr(result, "status_code", None)
    if status is not None and int(status) != int(HTTPStatus.OK):
        msg = getattr(result, "message", None) or callback.error_message or str(result)
        raise AsrError(f"DashScope ASR 失败: {msg}")
    if callback.error_message:
        raise AsrError(f"DashScope ASR 失败: {callback.error_message}")

    text = "".join(callback.parts).strip()
    if not text and hasattr(result, "get_sentence"):
        text = _sentence_text(result.get_sentence())
    if not text and hasattr(result, "output"):
        out = result.output
        if isinstance(out, dict):
            text = str(out.get("text") or out.get("sentence", {}).get("text") or "").strip()
    return text


def transcribe_upload(
    data: bytes,
    *,
    filename: str = "audio.webm",
    content_type: str = "",
) -> str:
    if not data:
        raise AsrError("空音频")
    suffix = Path(filename).suffix.lower() or ".webm"
    if not suffix.startswith("."):
        suffix = f".{suffix}"
    fd, tmp_in = tempfile.mkstemp(prefix="asr_in_", suffix=suffix)
    os.close(fd)
    in_path = Path(tmp_in)
    wav_path: Path | None = None
    try:
        in_path.write_bytes(data)
        ct = (content_type or "").lower()
        if suffix == ".wav" or "wav" in ct:
            wav_path = in_path
            text = transcribe_wav_file(wav_path)
        else:
            wav_path = convert_to_wav(in_path)
            text = transcribe_wav_file(wav_path)
        if not text:
            raise AsrError("没听清，请靠近麦克风再说一次")
        return text
    finally:
        in_path.unlink(missing_ok=True)
        if wav_path is not None and wav_path != in_path:
            wav_path.unlink(missing_ok=True)
