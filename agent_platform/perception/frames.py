"""Frame persistence — OpenCV JPEG + metadata sidecar (M4 D2)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from agent_platform.perception.contracts import SavedFrame, utc_now


class FrameSaveError(RuntimeError):
    pass


def opencv_available() -> bool:
    try:
        import cv2  # noqa: F401

        return True
    except ImportError:
        return False


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def save_frame_bundle(
    *,
    store_root: Path,
    captures_dir: Path,
    frame: Any,
    trace_id: str,
    scene: Optional[str] = None,
    device_id: Optional[str] = None,
    backend: str = "mock",
    jpeg_quality: int = 92,
    require_opencv: bool = True,
) -> SavedFrame:
    """Write captures/{trace_id}.jpg + .meta.json; return SavedFrame."""
    if require_opencv and not opencv_available():
        raise FrameSaveError(
            "OpenCV required for frame save — pip install opencv-python-headless"
        )
    import cv2
    import numpy as np

    if not isinstance(frame, np.ndarray):
        raise FrameSaveError(f"frame must be numpy ndarray, got {type(frame)}")

    captures_dir.mkdir(parents=True, exist_ok=True)
    stem = trace_id.replace("/", "_")[:36]
    image_name = f"{stem}.jpg"
    image_path = captures_dir / image_name
    meta_name = f"{stem}.meta.json"
    meta_path = captures_dir / meta_name

    if not cv2.imwrite(
        str(image_path),
        frame,
        [int(cv2.IMWRITE_JPEG_QUALITY), max(1, min(100, jpeg_quality))],
    ):
        raise FrameSaveError(f"cv2.imwrite failed: {image_path}")

    if not image_path.is_file() or image_path.stat().st_size == 0:
        raise FrameSaveError(f"empty or missing image: {image_path}")

    h, w = frame.shape[:2]
    digest = file_sha256(image_path)
    captured_at = utc_now()
    meta = {
        "trace_id": trace_id,
        "scene": scene,
        "device_id": device_id,
        "backend": backend,
        "width": int(w),
        "height": int(h),
        "channels": int(frame.shape[2]) if frame.ndim >= 3 else 1,
        "format": "jpeg",
        "sha256": digest,
        "captured_at": captured_at.isoformat(),
        "image_file": image_name,
    }
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    rel_image = image_path.relative_to(store_root).as_posix()
    rel_meta = meta_path.relative_to(store_root).as_posix()
    append_frames_index(store_root, meta)

    return SavedFrame(
        image_path=rel_image,
        meta_path=rel_meta,
        width=int(w),
        height=int(h),
        sha256=digest,
        format="jpeg",
        captured_at=captured_at,
        backend=backend,
    )


def append_frames_index(store_root: Path, meta: dict[str, Any]) -> None:
    index_path = store_root / "captures" / "index.jsonl"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(meta, ensure_ascii=False) + "\n"
    with index_path.open("a", encoding="utf-8") as f:
        f.write(line)


def load_saved_frame(store_root: Path, image_rel: str) -> Optional[SavedFrame]:
    meta_path = store_root / Path(image_rel).with_suffix(".meta.json")
    if not meta_path.is_file():
        # try stem.meta.json when image is captures/foo.jpg
        p = store_root / image_rel
        meta_path = p.parent / f"{p.stem}.meta.json"
    if not meta_path.is_file():
        return None
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    return SavedFrame(
        image_path=image_rel,
        meta_path=meta_path.relative_to(store_root).as_posix(),
        width=int(data["width"]),
        height=int(data["height"]),
        sha256=str(data["sha256"]),
        format=str(data.get("format", "jpeg")),
        captured_at=datetime.fromisoformat(data["captured_at"]),
        backend=str(data.get("backend", "")),
    )


def list_saved_frames(store_root: Path, limit: int = 20) -> list[SavedFrame]:
    index_path = store_root / "captures" / "index.jsonl"
    if not index_path.is_file():
        return []
    lines = index_path.read_text(encoding="utf-8").strip().splitlines()
    out: list[SavedFrame] = []
    for line in reversed(lines[-limit:]):
        if not line.strip():
            continue
        data = json.loads(line)
        rel = f"captures/{data.get('image_file', '')}"
        sf = load_saved_frame(store_root, rel)
        if sf:
            out.append(sf)
    return out


def synthetic_test_frame(width: int = 320, height: int = 240) -> Any:
    """BGR test pattern for mock / CI (no Reachy)."""
    import numpy as np

    y = np.linspace(0, 255, height, dtype=np.uint8)
    x = np.linspace(0, 255, width, dtype=np.uint8)
    yy, xx = np.meshgrid(y, x, indexing="ij")
    b = yy
    g = xx
    r = np.full((height, width), 128, dtype=np.uint8)
    return np.dstack([b, g, r])
