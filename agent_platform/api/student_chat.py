"""切片06/12 — 孩子聊天 UI 后端（FastAPI）。

复用 `voice.hermes_bridge.HermesBridge` 接到完整 hermes agent：
memory / calibration / proactive / agent-student 插件均在，
`pre_llm_student_context_hook` 会按 default_student_id 自动注入学情 + vision 上下文。

切片12：拍照走 `/api/vision/understand`（理解型 VLM），Vision 卡片 + 用户意图 → Agent 编排。
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Optional

from agent_platform.perception.vision_session import VISION_ID_ENV


def _load_hermes_env() -> None:
    """把 ~/.hermes/.env 的 key 载入进程环境（in-process 的 VLM 需要 DASHSCOPE_API_KEY）。"""
    env_path = Path(os.path.expanduser("~/.hermes/.env"))
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_hermes_env()

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from agent_platform.learning.bootstrap_family_alpha import ensure_family_alpha_content
from agent_platform.learning.profile_onboarding import (
    assistant_name_for_student,
    build_welcome_message,
    ensure_onboarding_stage_if_needed,
    maybe_advance_from_onboarding,
    snapshot_for_student,
)
from agent_platform.memory.assistant_identity import DEFAULT_ASSISTANT_NAME

from agent_platform.perception.vision_session import VisionSessionStore
from agent_platform.perception.vision_understand import understand_image
from agent_platform.voice._config import load_voice_config
from agent_platform.voice.hermes_bridge import HermesBridge, HermesCancelledError
from agent_platform.voice.tts import synthesize_to_file_sync

_OCR_PROMPT = (
    "这是一张小学作业照片。请把图片里的题目【原文一字不差地】抄写出来，"
    "保留数字、运算符号和题号；如果有多道题，每道题单独一行。"
    "只输出题目本身，不要解答、不要解释。看不清的字用□代替。"
)

_TEMPLATES = Path(__file__).parent / "templates"
_CHAT_HTML = (_TEMPLATES / "student_chat.html").read_text(encoding="utf-8")

_EMOJI_RE = re.compile(
    "[" "\U0001f300-\U0001faff" "\U00002600-\U000027bf" "\U0001f1e6-\U0001f1ff" "\u2640-\u2642" "]+",
    flags=re.UNICODE,
)


def _speakable(text: str) -> str:
    t = re.sub(r"[*_`#>~]", "", text)
    t = re.sub(r"^\s*[-•]\s*", "", t, flags=re.M)
    t = _EMOJI_RE.sub("", t)
    t = re.sub(r"\n{2,}", "。", t)
    t = re.sub(r"[ \t]+", " ", t)
    return t.strip()


class ChatIn(BaseModel):
    message: str = Field(min_length=1)
    session_id: Optional[str] = None
    vision_id: Optional[str] = None


class ChatOut(BaseModel):
    reply: str
    session_id: Optional[str] = None
    elapsed_ms: float = 0.0


class TtsIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    lang: str = "zh"


class OcrOut(BaseModel):
    text: str
    elapsed_ms: float = 0.0


class VisionItemOut(BaseModel):
    stem: str
    student_answer: str = ""
    is_correct: Optional[bool] = None
    teacher_mark: Optional[str] = None


class VisionUnderstandOut(BaseModel):
    vision_id: str
    image_type: str
    summary: str
    items: list[VisionItemOut]
    stats: dict[str, int]
    card_title: str
    card_subtitle: str
    elapsed_ms: float = 0.0


def _vision_out(record) -> VisionUnderstandOut:
    return VisionUnderstandOut(
        vision_id=record.vision_id,
        image_type=record.image_type,
        summary=record.summary,
        items=[VisionItemOut.model_validate(i.model_dump()) for i in record.items],
        stats=record.stats,
        card_title=record.card_title,
        card_subtitle=record.card_subtitle,
        elapsed_ms=record.elapsed_ms,
    )


def create_app(
    config: Optional[dict] = None,
    bridge: Optional[HermesBridge] = None,
    vision_store: Optional[VisionSessionStore] = None,
) -> FastAPI:
    cfg = config or load_voice_config()
    hermes_cfg = cfg.get("hermes") or {}
    tts_cfg = cfg.get("tts") or {}
    zh_voice = str(tts_cfg.get("zh_voice", "zh-CN-XiaoxiaoNeural"))
    en_voice = str(tts_cfg.get("en_voice", "en-US-AriaNeural"))
    _bridge = bridge or HermesBridge(
        provider=str(hermes_cfg.get("provider", "deepseek")),
        model=str(hermes_cfg.get("model", "deepseek-chat")),
        timeout_s=float(hermes_cfg.get("timeout_s", 120.0)),
    )
    _vision_store = vision_store or VisionSessionStore()

    _vlm_holder: dict = {}

    def get_vlm():
        if "vlm" not in _vlm_holder:
            from agent_platform.perception._config import load_perception_config
            from agent_platform.perception.vlm import build_vlm_adapter

            pcfg = load_perception_config()
            _vlm_holder["vlm"] = build_vlm_adapter({"vision": pcfg.get("vision") or {}})
        return _vlm_holder["vlm"]

    app = FastAPI(title="Student Jarvis Chat", version="0.5.0-family-alpha-p0")

    _bootstrap = ensure_family_alpha_content()

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "bootstrap": _bootstrap.to_dict()}

    @app.get("/", response_class=HTMLResponse)
    def chat_page() -> str:
        return _CHAT_HTML

    def _default_student_id() -> str:
        from agent_platform.learning._config import load_student_learning_config

        cfg = load_student_learning_config()
        return str((cfg.get("hermes") or {}).get("default_student_id") or "g2-stu-01")

    @app.get("/api/chat/welcome")
    def chat_welcome(student_id: Optional[str] = None) -> dict:
        sid = (student_id or _default_student_id()).strip()
        snap = snapshot_for_student(sid)
        assistant = assistant_name_for_student(sid)
        ensure_onboarding_stage_if_needed(sid, snap)
        from agent_platform.learning.student_context import StudentContextService

        stage = "unknown"
        try:
            ctx = StudentContextService().get(sid)
            stage = ctx.pipeline_stage.value
        except FileNotFoundError:
            pass
        return {
            "student_id": sid,
            "message": build_welcome_message(snap, assistant_name=assistant),
            "assistant_name": assistant,
            "assistant_default": DEFAULT_ASSISTANT_NAME,
            "profile_complete": snap.is_complete,
            "missing": snap.missing,
            "display_name": snap.display_name,
            "pipeline_stage": stage,
        }

    @app.post("/api/chat", response_model=ChatOut)
    def chat(body: ChatIn) -> ChatOut:
        env_extra: dict[str, str] = {}
        if body.vision_id:
            rec = _vision_store.get(body.vision_id)
            if rec is None:
                raise HTTPException(status_code=404, detail=f"vision 已过期或不存在: {body.vision_id}")
            env_extra[VISION_ID_ENV] = body.vision_id
        try:
            reply = _bridge.ask(
                body.message,
                session_id=body.session_id,
                env_extra=env_extra or None,
            )
        except HermesCancelledError:
            raise HTTPException(status_code=499, detail="cancelled") from None
        except RuntimeError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=504, detail=f"agent error: {e}") from e
        try:
            maybe_advance_from_onboarding(_default_student_id())
        except Exception:
            pass
        return ChatOut(
            reply=reply.text,
            session_id=reply.session_id,
            elapsed_ms=reply.elapsed_ms,
        )

    @app.post("/api/chat/stream")
    def chat_stream(body: ChatIn) -> StreamingResponse:
        """SSE：轮询 hermes 输出文件，逐段推送回复文本。"""
        import json

        env_extra: dict[str, str] = {}
        if body.vision_id:
            rec = _vision_store.get(body.vision_id)
            if rec is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"vision 已过期或不存在: {body.vision_id}",
                )
            env_extra[VISION_ID_ENV] = body.vision_id

        def event_gen():
            try:
                for ev in _bridge.stream_ask(
                    body.message,
                    session_id=body.session_id,
                    env_extra=env_extra or None,
                ):
                    if ev.text_delta:
                        payload = {"delta": ev.text_delta}
                        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    if ev.done:
                        payload = {
                            "done": True,
                            "session_id": ev.session_id,
                            "elapsed_ms": ev.elapsed_ms,
                            "error": ev.error,
                        }
                        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            except HermesCancelledError:
                payload = {"done": True, "error": "cancelled"}
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            except Exception as exc:  # noqa: BLE001
                payload = {"done": True, "error": str(exc)}
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            event_gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/chat/abort")
    def chat_abort() -> dict[str, bool]:
        """中止进行中的 hermes 子进程，供前端「停止」按钮调用。"""
        return {"cancelled": _bridge.cancel()}

    @app.post("/api/tts")
    def tts(body: TtsIn) -> Response:
        speakable = _speakable(body.text)
        if not speakable:
            raise HTTPException(status_code=400, detail="no speakable text")
        voice = en_voice if body.lang.startswith("en") else zh_voice
        out_path = Path(tempfile.mkstemp(prefix="chat_tts_", suffix=".mp3")[1])
        try:
            synthesize_to_file_sync(speakable, out_path, voice=voice)
            audio = out_path.read_bytes()
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"tts failed: {e}") from e
        finally:
            out_path.unlink(missing_ok=True)
        return Response(content=audio, media_type="audio/mpeg")

    async def _read_upload_image(image: UploadFile) -> tuple[bytes, Path]:
        raw = await image.read()
        if not raw:
            raise HTTPException(status_code=400, detail="空文件")
        suffix = Path(image.filename or "").suffix.lower() or ".png"
        if suffix not in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
            suffix = ".png"
        fd, tmp = tempfile.mkstemp(prefix="chat_img_", suffix=suffix)
        tmp_path = Path(tmp)
        with open(fd, "wb") as f:
            f.write(raw)
        return raw, tmp_path

    @app.post("/api/vision/understand", response_model=VisionUnderstandOut)
    async def vision_understand(image: UploadFile = File(...)) -> VisionUnderstandOut:
        """理解型 VLM：类型 + 题/答案/对错。不入学情，仅供 Vision 卡片 + Agent 编排。"""
        _, tmp_path = await _read_upload_image(image)
        try:
            result = understand_image(tmp_path)
            saved = _vision_store.save(result, image_copy_from=tmp_path)
        except ValueError as e:
            raise HTTPException(status_code=502, detail=f"理解结果解析失败：{e}") from e
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"识图失败：{e}") from e
        finally:
            tmp_path.unlink(missing_ok=True)
        return _vision_out(saved)

    @app.post("/api/ocr", response_model=OcrOut)
    async def ocr(image: UploadFile = File(...)) -> OcrOut:
        """遗留抄题接口（切片05）；学生页已改用 /api/vision/understand。"""
        import time

        _, tmp_path = await _read_upload_image(image)
        try:
            t0 = time.perf_counter()
            text = get_vlm().describe(tmp_path, _OCR_PROMPT)
            elapsed_ms = (time.perf_counter() - t0) * 1000
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"识图失败：{e}") from e
        finally:
            tmp_path.unlink(missing_ok=True)
        return OcrOut(text=text.strip(), elapsed_ms=elapsed_ms)

    return app


app = create_app()


def main() -> None:
    import uvicorn

    cfg = load_voice_config()
    chat_cfg = (cfg.get("chat_panel") or {}) if isinstance(cfg, dict) else {}
    host = str(chat_cfg.get("host", "127.0.0.1"))
    port = int(chat_cfg.get("port", 8771))
    uvicorn.run("agent_platform.api.student_chat:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
