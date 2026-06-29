"""Voice turn: wake / text / mic → Hermes → TTS (+ barge-in)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from voice._config import load_voice_config
from voice.asr_router import ASRRouter
from voice.audio_io import (
    play_audio_file,
    play_audio_with_barge_in,
    record_mic,
    save_wav_16k_mono,
)
from voice.hermes_bridge import HermesBridge, HermesReply
from voice.perception_bridge import VoicePerceptionBridge
from voice.proactive_bridge import VoiceProactiveBridge
from voice.metrics import LatencyTracker
from voice.tts import synthesize_to_file_sync, voice_for_language
from voice.vad import CHUNK_SAMPLES_16K, SileroVAD
from voice.wake import WakeWordDetector, listen_for_wake


class VoicePipeline:
    def __init__(self, config: dict | None = None) -> None:
        self.cfg = config or load_voice_config()
        self._asr: ASRRouter | None = None
        self._hermes_bridge: HermesBridge | None = None
        self._vad: SileroVAD | None = None
        self._wake: WakeWordDetector | None = None
        self._perception: VoicePerceptionBridge | None = None
        self._proactive: VoiceProactiveBridge | None = None

    def _asr_router(self) -> ASRRouter:
        if self._asr is None:
            ac = self.cfg.get("asr", {})
            self._asr = ASRRouter(
                whisper_size=ac.get("whisper_size", "base"),
                funasr_model=ac.get("funasr_model", "paraformer-zh"),
                device=ac.get("device", "auto"),
            )
        return self._asr

    def _get_hermes(self) -> HermesBridge:
        if self._hermes_bridge is None:
            hc = self.cfg.get("hermes", {})
            self._hermes_bridge = HermesBridge(
                provider=hc.get("provider", "deepseek"),
                model=hc.get("model", "deepseek-chat"),
            )
        return self._hermes_bridge

    def _get_vad(self) -> SileroVAD:
        if self._vad is None:
            vc = self.cfg["vad"]
            self._vad = SileroVAD(
                sample_rate=vc["sample_rate"],
                threshold=vc["threshold"],
                min_silence_ms=vc["min_silence_ms"],
                speech_pad_ms=vc.get("speech_pad_ms", 30),
            )
        return self._vad

    def _get_perception(self) -> VoicePerceptionBridge:
        if self._perception is None:
            self._perception = VoicePerceptionBridge.from_voice_config(self.cfg)
        return self._perception

    def _get_proactive(self) -> VoiceProactiveBridge:
        if self._proactive is None:
            self._proactive = VoiceProactiveBridge.from_voice_config(self.cfg)
        return self._proactive

    def _get_wake(self) -> WakeWordDetector:
        if self._wake is None:
            wc = self.cfg.get("wake", {})
            models = wc.get("models") or [wc.get("model", "alexa")]
            self._wake = WakeWordDetector(
                models=models,
                threshold=wc.get("threshold", 0.5),
            )
        return self._wake

    def _vad_segments(self, pcm: np.ndarray) -> list[tuple[int, int]]:
        vad = self._get_vad()
        vad.reset()
        pad = (CHUNK_SAMPLES_16K - len(pcm) % CHUNK_SAMPLES_16K) % CHUNK_SAMPLES_16K
        if pad:
            pcm = np.concatenate([pcm, np.zeros(pad, dtype=np.int16)])
        spans: list[tuple[int, int]] = []
        for i in range(0, len(pcm), CHUNK_SAMPLES_16K):
            for seg in vad.process_chunk(pcm[i : i + CHUNK_SAMPLES_16K]):
                spans.append((seg.start_sample, seg.end_sample))
        tail = vad.flush()
        if tail:
            spans.append((tail.start_sample, tail.end_sample))
        return spans

    def run_text_turn(
        self,
        user_text: str,
        *,
        language: str = "zh",
        play: bool = True,
        barge_in: bool | None = None,
        out_dir: Path | None = None,
        session_id: str | None = None,
        forced_reply: str | None = None,
    ) -> dict:
        tracker = LatencyTracker()
        out_dir = out_dir or Path("/tmp/agent_voice_smoke/turns")
        out_dir.mkdir(parents=True, exist_ok=True)

        sid = session_id or "voice-session"
        proactive_meta: dict = {}
        perception_meta: dict = {}

        if forced_reply:
            reply = HermesReply(text=forced_reply, session_id=sid, elapsed_ms=0.0)
            hermes_ms = 0.0
        else:
            proactive_turn = self._get_proactive().on_user_message(
                user_text, session_id=sid
            )
            proactive_meta = self._get_proactive().turn_metadata(proactive_turn)

            if proactive_turn.reply_override:
                reply = HermesReply(
                    text=proactive_turn.reply_override,
                    session_id=sid,
                    elapsed_ms=0.0,
                )
                hermes_ms = 0.0
                tracker.start("proactive")
                tracker.stop("proactive")
            else:
                perception_turn = self._get_perception().pre_turn(
                    user_text, session_id=sid
                )
                perception_meta = self._get_perception().turn_metadata(perception_turn)

                if perception_turn.reply_override:
                    reply = HermesReply(
                        text=perception_turn.reply_override,
                        session_id=sid,
                        elapsed_ms=0.0,
                    )
                    hermes_ms = 0.0
                    tracker.start("perception")
                    tracker.stop("perception")
                else:
                    hermes_prompt = self._get_perception().apply_to_hermes_prompt(
                        user_text, perception_turn
                    )
                    if perception_turn.handled and perception_turn.vision_intent:
                        tracker.start("perception")
                        tracker.stop("perception")
                    tracker.start("hermes")
                    reply = self._get_hermes().ask(hermes_prompt)
                    hermes_ms = tracker.stop("hermes")

        tts_cfg = self.cfg["tts"]
        voice = voice_for_language(
            language, zh_voice=tts_cfg["zh_voice"], en_voice=tts_cfg["en_voice"]
        )
        mp3 = out_dir / "reply.mp3"
        tracker.start("tts")
        synthesize_to_file_sync(reply.text, mp3, voice=voice)
        tts_ms = tracker.stop("tts")

        use_barge = (
            barge_in
            if barge_in is not None
            else self.cfg.get("barge_in", {}).get("enabled", False)
        )
        interrupted = False
        if play:
            if use_barge:
                bc = self.cfg.get("barge_in", {})
                tracker.start("tts_play")
                interrupted = play_audio_with_barge_in(
                    mp3,
                    self._get_vad(),
                    device=self.cfg["mic"].get("device"),
                    speech_frames_to_trigger=bc.get("speech_frames", 3),
                )
                tracker.stop("tts_play")
            else:
                tracker.start("tts_play")
                play_audio_file(mp3)
                tracker.stop("tts_play")

        out_session = reply.session_id or session_id
        return {
            "user_text": user_text,
            "reply_text": reply.text,
            "session_id": out_session,
            "reply_audio": str(mp3),
            "language": language,
            "barge_in": interrupted,
            "hermes_ms": hermes_ms,
            "tts_ms": tts_ms,
            "metrics": tracker.summary(),
            **perception_meta,
            **proactive_meta,
        }

    def run_proactive_nudge(
        self,
        *,
        session_id: str = "voice-session",
        work_minutes: float | None = None,
        play: bool = True,
        language: str = "zh",
        out_dir: Path | None = None,
    ) -> dict:
        """US-5 agent-initiated: evaluate proactive speech → TTS (no user input)."""
        nudge_turn = self._get_proactive().maybe_proactive_nudge(
            session_id=session_id,
            work_minutes=work_minutes,
            natural_pause=True,
        )
        meta = self._get_proactive().turn_metadata(nudge_turn)
        if not nudge_turn.proactive_nudge:
            return {
                "proactive_allowed": nudge_turn.proactive_allowed,
                "reason_code": nudge_turn.reason_code,
                "reply_text": "",
                **meta,
            }
        return self.run_text_turn(
            "",
            language=language,
            play=play,
            out_dir=out_dir,
            session_id=session_id,
            forced_reply=nudge_turn.proactive_nudge,
        )

    def run_audio_turn(
        self,
        wav_path: str | Path,
        *,
        language_hint: str | None = None,
        play: bool = True,
        barge_in: bool | None = None,
        out_dir: Path | None = None,
        session_id: str | None = None,
    ) -> dict:
        tracker = LatencyTracker()
        tracker.start("asr")
        text, lang = self._asr_router().transcribe(wav_path, language=language_hint)
        tracker.stop("asr")
        result = self.run_text_turn(
            text,
            language=lang,
            play=play,
            barge_in=barge_in,
            out_dir=out_dir,
            session_id=session_id,
        )
        result["asr_text"] = text
        result["asr_language"] = lang
        return result

    def run_mic_turn(
        self,
        seconds: float | None = None,
        *,
        play: bool = True,
        barge_in: bool | None = None,
        out_dir: Path | None = None,
        session_id: str | None = None,
    ) -> dict:
        mic_cfg = self.cfg["mic"]
        vad_cfg = self.cfg["vad"]
        sr = vad_cfg["sample_rate"]
        seconds = seconds or mic_cfg["record_seconds"]
        out_dir = out_dir or Path("/tmp/agent_voice_smoke/turns")

        pcm = record_mic(seconds, sr, mic_cfg.get("device"))
        save_wav_16k_mono(out_dir / "input_raw.wav", pcm)

        spans = self._vad_segments(pcm)
        if not spans:
            raise RuntimeError("no speech detected — speak louder or increase duration")

        s0, s1 = spans[0]
        seg_wav = out_dir / "input_seg0.wav"
        save_wav_16k_mono(seg_wav, pcm[s0:s1])
        return self.run_audio_turn(
            seg_wav,
            play=play,
            barge_in=barge_in,
            out_dir=out_dir,
            session_id=session_id,
        )

    def run_wake_then_turn(
        self,
        *,
        wake_timeout_s: float | None = None,
        play: bool = True,
        barge_in: bool | None = None,
        out_dir: Path | None = None,
    ) -> dict:
        """Wait for wake word, then record + full turn."""
        tracker = LatencyTracker()
        wc = self.cfg.get("wake", {})
        timeout = wake_timeout_s or wc.get("listen_timeout_s", 30.0)

        tracker.start("wake_listen")
        hit = listen_for_wake(
            self._get_wake(),
            timeout_s=timeout,
            device=self.cfg["mic"].get("device"),
        )
        wake_ms = tracker.stop("wake_listen")

        if hit is None:
            return {
                "wake": False,
                "wake_ms": wake_ms,
                "metrics": tracker.summary(),
            }

        tracker.start("wake_to_vad_ready")
        self._get_vad()  # load VAD after wake (M1.6 metric)
        wake_vad_ms = tracker.stop("wake_to_vad_ready")

        result = self.run_mic_turn(play=play, barge_in=barge_in, out_dir=out_dir)
        result["wake"] = True
        result["wake_model"] = hit.model_name
        result["wake_score"] = hit.score
        result["wake_ms"] = wake_ms
        result["wake_to_vad_ready_ms"] = wake_vad_ms
        return result

    def run_barge_in_recovery(
        self,
        *,
        record_seconds: float = 3.0,
        out_dir: Path | None = None,
    ) -> dict:
        """After barge-in during TTS: capture new utterance and respond."""
        return self.run_mic_turn(
            seconds=record_seconds,
            play=True,
            barge_in=True,
            out_dir=out_dir,
        )
