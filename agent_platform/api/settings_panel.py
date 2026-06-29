"""M7 D3 — FastAPI behavior settings panel (US-3: 它的设定 可见可改)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from agent_platform.behavior._config import load_behavior_config, resolve_profile_path, resolve_store_root
from agent_platform.behavior.contracts import BehaviorProfileUpdate, Tone, Verbosity
from agent_platform.behavior.service import BehaviorService
from agent_platform.behavior.store import BehaviorStore

_PANEL_HTML = (Path(__file__).parent / "templates" / "settings_panel.html").read_text(encoding="utf-8")


class ProfileOut(BaseModel):
    tone: str
    verbosity: str
    language: str
    rules: list[str]
    custom_notes: str
    updated_at: Optional[str] = None
    system_prompt: str
    panel_url: str


class ProfileIn(BaseModel):
    tone: Optional[str] = None
    verbosity: Optional[str] = None
    language: Optional[str] = None
    rules: Optional[list[str]] = None
    custom_notes: Optional[str] = Field(default=None)


def _profile_out(svc: BehaviorService) -> ProfileOut:
    p = svc.get_profile()
    return ProfileOut(
        tone=p.tone.value,
        verbosity=p.verbosity.value,
        language=p.language,
        rules=p.rules,
        custom_notes=p.custom_notes,
        updated_at=p.updated_at.isoformat() if p.updated_at else None,
        system_prompt=svc.system_prompt_block(),
        panel_url=svc.panel_url(),
    )


def create_app(config: Optional[dict] = None, service: Optional[BehaviorService] = None) -> FastAPI:
    cfg = config or load_behavior_config()
    if service is not None:
        svc = service
    else:
        root = resolve_store_root(cfg)
        profile_path = resolve_profile_path(cfg)
        store = BehaviorStore(profile_path, default_profile=cfg.get("default_profile") or {})
        svc = BehaviorService(config=cfg, store=store)

    app = FastAPI(title="Agent Behavior Settings", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "component": "behavior_panel"}

    @app.get("/", response_class=HTMLResponse)
    def panel_page() -> str:
        return _PANEL_HTML

    @app.get("/api/behavior/profile", response_model=ProfileOut)
    def get_profile() -> ProfileOut:
        return _profile_out(svc)

    @app.put("/api/behavior/profile", response_model=ProfileOut)
    def put_profile(body: ProfileIn) -> ProfileOut:
        patch = BehaviorProfileUpdate(
            tone=Tone(body.tone) if body.tone else None,
            verbosity=Verbosity(body.verbosity) if body.verbosity else None,
            language=body.language,
            rules=body.rules,
            custom_notes=body.custom_notes,
        )
        svc.update_profile(patch)
        return _profile_out(svc)

    @app.post("/api/behavior/profile/reset", response_model=ProfileOut)
    def reset_profile() -> ProfileOut:
        svc.reset_profile()
        return _profile_out(svc)

    @app.post("/api/behavior/drift")
    def check_drift(body: dict[str, Any]) -> dict[str, Any]:
        text = (body.get("text") or "").strip()
        report = svc.check_drift(text)
        return report.model_dump()

    return app


def main() -> None:
    import uvicorn

    cfg = load_behavior_config()
    panel = cfg.get("panel") or {}
    host = panel.get("host", "127.0.0.1")
    port = int(panel.get("port", 8767))
    uvicorn.run(create_app(cfg), host=host, port=port)


if __name__ == "__main__":
    main()
