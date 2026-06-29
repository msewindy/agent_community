"""Vision 理解结果 session 暂存（切片12）：供 chat + pre_llm 跨进程读取。"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from agent_platform.learning._config import load_student_learning_config, repo_root
from agent_platform.learning.store import _atomic_write_json
from agent_platform.perception._config import load_perception_config
from agent_platform.perception.vision_understand import VisionUnderstandResult

VISION_ID_ENV = "STUDENT_JARVIS_VISION_ID"
DEFAULT_TTL_MIN = 30


def _cache_root() -> Path:
    cfg = load_student_learning_config()
    raw = (cfg.get("data") or {}).get("root", "student_data")
    root = Path(raw)
    if not root.is_absolute():
        root = repo_root() / root
    return (root / "_vision_cache").resolve()


class VisionSessionStore:
    def __init__(self, ttl_minutes: int = DEFAULT_TTL_MIN) -> None:
        self._root = _cache_root()
        self._ttl = timedelta(minutes=ttl_minutes)

    def _path(self, vision_id: str) -> Path:
        safe = vision_id.replace("/", "_").replace("\\", "_")
        return self._root / f"{safe}.json"

    def save(
        self,
        result: VisionUnderstandResult,
        *,
        image_copy_from: Optional[Path] = None,
    ) -> VisionUnderstandResult:
        self._root.mkdir(parents=True, exist_ok=True)
        vid = result.vision_id or (
            datetime.now(timezone.utc).strftime("vis-%Y%m%d-%H%M%S-") + secrets.token_hex(3)
        )
        frame_path: Optional[str] = result.frame_path
        if image_copy_from and image_copy_from.is_file():
            frames = self._root / "frames"
            frames.mkdir(parents=True, exist_ok=True)
            suffix = image_copy_from.suffix.lower() or ".jpg"
            dest = frames / f"{vid}{suffix}"
            shutil.copy2(image_copy_from, dest)
            frame_path = str(dest)

        payload = result.model_copy(
            update={
                "vision_id": vid,
                "frame_path": frame_path,
            }
        )
        record = {
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "vision": payload.model_dump(mode="json"),
        }
        _atomic_write_json(
            self._path(vid),
            json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        )
        return payload

    def get(self, vision_id: str) -> Optional[VisionUnderstandResult]:
        if not vision_id:
            return None
        path = self._path(vision_id)
        if not path.is_file():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        saved_at = datetime.fromisoformat(raw["saved_at"])
        if saved_at.tzinfo is None:
            saved_at = saved_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - saved_at > self._ttl:
            return None
        return VisionUnderstandResult.model_validate(raw["vision"])

    @staticmethod
    def load_from_env() -> Optional[VisionUnderstandResult]:
        vid = os.environ.get(VISION_ID_ENV, "").strip()
        if not vid:
            return None
        return VisionSessionStore().get(vid)
