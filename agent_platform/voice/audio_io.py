"""16 kHz mono PCM helpers."""

from __future__ import annotations

import queue
import subprocess
import threading
import time
from pathlib import Path

import numpy as np


def load_audio_16k_mono(path: str | Path) -> tuple[np.ndarray, int]:
    """Load audio file as int16 mono @ 16 kHz (soundfile; mp3 via librosa if needed)."""
    import soundfile as sf

    p = Path(path)
    try:
        data, sr = sf.read(str(p), dtype="float32", always_2d=True)
    except Exception:
        import librosa

        y, sr = librosa.load(str(p), sr=None, mono=True)
        data = y.reshape(-1, 1)

    mono = data.mean(axis=1)
    if sr != 16000:
        import librosa

        mono = librosa.resample(mono, orig_sr=sr, target_sr=16000)
        sr = 16000
    pcm = (np.clip(mono, -1.0, 1.0) * 32767).astype(np.int16)
    return pcm, 16000


def save_wav_16k_mono(path: str | Path, pcm_int16: np.ndarray) -> Path:
    import soundfile as sf

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    f32 = pcm_int16.astype(np.int16).astype(np.float32) / 32768.0
    sf.write(str(out), f32, 16000, subtype="PCM_16")
    return out


class StoppablePlayer:
    """Background ffplay process that can be terminated (barge-in)."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None

    def play(self, path: str | Path) -> None:
        import shutil

        ffplay = shutil.which("ffplay")
        if not ffplay:
            raise RuntimeError("ffplay not found")
        self._proc = subprocess.Popen(
            [ffplay, "-nodisp", "-autoexit", str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None

    def wait(self) -> int:
        if not self._proc:
            return 0
        return self._proc.wait()


def play_audio_file(path: str | Path) -> None:
    """Play mp3/wav via ffplay (blocking)."""
    player = StoppablePlayer()
    player.play(path)
    player.wait()


def play_audio_with_barge_in(
    path: str | Path,
    vad,
    *,
    device: int | None = None,
    chunk_samples: int = 512,
    speech_frames_to_trigger: int = 3,
) -> bool:
    """
    Play audio while monitoring the mic with Silero VAD.

    Returns True if user speech interrupted playback (barge-in).
    """
    import sounddevice as sd

    from voice.vad import CHUNK_SAMPLES_16K

    audio_q: queue.Queue[np.ndarray] = queue.Queue()
    barge_event = threading.Event()

    def _callback(indata, _frames, _time, _status) -> None:
        audio_q.put(indata[:, 0].copy())

    player = StoppablePlayer()
    player.play(path)

    vad.reset()
    speech_streak = 0
    buffer = np.array([], dtype=np.int16)

    stream = sd.InputStream(
        samplerate=16000,
        channels=1,
        dtype="int16",
        blocksize=chunk_samples,
        device=device,
        callback=_callback,
    )

    with stream:
        while player._proc and player._proc.poll() is None:
            try:
                block = audio_q.get(timeout=0.05)
            except queue.Empty:
                continue
            buffer = np.concatenate([buffer, block.astype(np.int16)])
            while len(buffer) >= CHUNK_SAMPLES_16K:
                chunk = buffer[:CHUNK_SAMPLES_16K]
                buffer = buffer[CHUNK_SAMPLES_16K:]
                segments = vad.process_chunk(chunk)
                if segments:
                    speech_streak += 1
                    if speech_streak >= speech_frames_to_trigger:
                        player.stop()
                        barge_event.set()
                        break
                else:
                    speech_streak = 0
            if barge_event.is_set():
                break

    if not barge_event.is_set():
        player.wait()
    return barge_event.is_set()


def record_mic(seconds: float, sr: int = 16000, device: int | None = None) -> np.ndarray:
    import sounddevice as sd

    audio = sd.rec(int(seconds * sr), samplerate=sr, channels=1, dtype="int16", device=device)
    sd.wait()
    return audio[:, 0]
