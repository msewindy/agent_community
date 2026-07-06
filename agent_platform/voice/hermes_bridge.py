"""Hermes / DeepSeek text bridge (non-interactive ``hermes chat -q``).

``hermes chat`` 会完成本轮对话并打印结果，但在非交互（无 PTY、管道）子进程
场景下进程常**收尾不退出**（疑似常驻线程/子进程不释放句柄）。因此这里不用
``subprocess.run`` 阻塞等待退出，而是：输出重定向到临时文件 + 独立进程组起
``Popen``，轮询到 STDOUT 产出且稳定（一段时间不再增长）即判定完成，回收进程组
并解析结果。既拿到完整回复，又不会被收尾挂起拖死。
"""

from __future__ import annotations

import os
import re
import shutil
import signal
import tempfile
import threading
import time
from dataclasses import dataclass
from typing import Iterator, Optional


class HermesCancelledError(RuntimeError):
    """``ask()`` 被 ``cancel()`` 或客户端中止打断。"""


@dataclass
class HermesReply:
    text: str
    session_id: str | None = None
    elapsed_ms: float = 0.0


@dataclass
class HermesStreamEvent:
    text_delta: str = ""
    session_id: str | None = None
    elapsed_ms: float = 0.0
    done: bool = False
    error: str | None = None


class HermesBridge:
    def __init__(
        self,
        *,
        provider: str = "deepseek",
        model: str = "deepseek-chat",
        hermes_bin: str | None = None,
        timeout_s: float = 120.0,
        stable_after_s: float = 3.0,
        poll_interval_s: float = 0.3,
        extra_args: list[str] | None = None,
    ) -> None:
        self.provider = provider
        self.model = model
        self.hermes_bin = hermes_bin or shutil.which("hermes") or os.path.expanduser(
            "~/.local/bin/hermes"
        )
        self.timeout_s = timeout_s
        self.stable_after_s = stable_after_s
        self.poll_interval_s = poll_interval_s
        self.extra_args = extra_args or []
        self._active_proc = None
        self._cancel_event = threading.Event()

    def cancel(self) -> bool:
        """终止进行中的 ``ask()``。返回是否确有任务被取消。"""
        had = self._active_proc is not None and self._active_proc.poll() is None
        self._cancel_event.set()
        proc = self._active_proc
        if proc is not None and proc.poll() is None:
            self._terminate(proc)
        return had

    def ask(
        self,
        prompt: str,
        *,
        session_id: str | None = None,
        image: str | None = None,
        env_extra: dict[str, str] | None = None,
    ) -> HermesReply:
        cmd = [
            self.hermes_bin,
            "chat",
            "-q",
            prompt,
            "-Q",
            "--provider",
            self.provider,
            "--model",
            self.model,
        ]
        if session_id:
            cmd += ["--resume", session_id]
        if image:
            cmd += ["--image", image]
        cmd += self.extra_args

        env = os.environ.copy()
        env["PATH"] = f"{os.path.expanduser('~/.local/bin')}:{env.get('PATH', '')}"
        if env_extra:
            env.update(env_extra)

        out_fd, out_path = tempfile.mkstemp(prefix="hermes_out_", suffix=".log")
        err_fd, err_path = tempfile.mkstemp(prefix="hermes_err_", suffix=".log")
        out_f = os.fdopen(out_fd, "w")
        err_f = os.fdopen(err_fd, "w")

        import subprocess

        t0 = time.perf_counter()
        proc = subprocess.Popen(
            cmd,
            stdout=out_f,
            stderr=err_f,
            stdin=subprocess.DEVNULL,
            env=env,
            cwd=os.path.expanduser("~"),
            start_new_session=True,
        )

        self._cancel_event.clear()
        self._active_proc = proc
        timed_out = False
        cancelled = False
        try:
            while True:
                if self._cancel_event.is_set():
                    cancelled = True
                    break
                if proc.poll() is not None:
                    break
                if (time.perf_counter() - t0) > self.timeout_s:
                    timed_out = True
                    break
                try:
                    size = os.path.getsize(out_path)
                    mtime = os.path.getmtime(out_path)
                except FileNotFoundError:
                    size, mtime = 0, 0.0
                # 回复已产出且 STDOUT 停止增长 => 本轮完成（即便进程不肯退出）
                if size > 0 and (time.time() - mtime) > self.stable_after_s:
                    self._terminate(proc)
                    break
                time.sleep(self.poll_interval_s)
        finally:
            self._terminate(proc)
            self._active_proc = None
            out_f.close()
            err_f.close()

        elapsed_ms = (time.perf_counter() - t0) * 1000
        if cancelled:
            raise HermesCancelledError("hermes chat cancelled")
        stdout = _read(out_path)
        stderr = _read(err_path)
        _unlink(out_path)
        _unlink(err_path)

        if timed_out and not stdout.strip():
            raise RuntimeError(
                f"hermes chat timed out after {self.timeout_s}s with no output; "
                f"stderr tail: {stderr.strip()[-400:]}"
            )

        text = _reply_body(stdout)
        sid = _find_session_id(stdout, stderr)
        if not text:
            raise RuntimeError(
                f"hermes chat produced no reply; stderr tail: {stderr.strip()[-400:]}"
            )
        return HermesReply(text=text, session_id=sid, elapsed_ms=elapsed_ms)

    def stream_ask(
        self,
        prompt: str,
        *,
        session_id: str | None = None,
        image: str | None = None,
        env_extra: dict[str, str] | None = None,
    ) -> Iterator[HermesStreamEvent]:
        """流式产出回复增量（轮询 hermes 输出文件，非 LLM token 级）。"""
        import subprocess

        cmd = [
            self.hermes_bin,
            "chat",
            "-q",
            prompt,
            "-Q",
            "--provider",
            self.provider,
            "--model",
            self.model,
        ]
        if session_id:
            cmd += ["--resume", session_id]
        if image:
            cmd += ["--image", image]
        cmd += self.extra_args

        env = os.environ.copy()
        env["PATH"] = f"{os.path.expanduser('~/.local/bin')}:{env.get('PATH', '')}"
        if env_extra:
            env.update(env_extra)

        out_fd, out_path = tempfile.mkstemp(prefix="hermes_out_", suffix=".log")
        err_fd, err_path = tempfile.mkstemp(prefix="hermes_err_", suffix=".log")
        out_f = os.fdopen(out_fd, "w")
        err_f = os.fdopen(err_fd, "w")

        t0 = time.perf_counter()
        proc = subprocess.Popen(
            cmd,
            stdout=out_f,
            stderr=err_f,
            stdin=subprocess.DEVNULL,
            env=env,
            cwd=os.path.expanduser("~"),
            start_new_session=True,
        )

        self._cancel_event.clear()
        self._active_proc = proc
        timed_out = False
        cancelled = False
        prev_body = ""
        try:
            while True:
                if self._cancel_event.is_set():
                    cancelled = True
                    break
                if proc.poll() is not None:
                    break
                if (time.perf_counter() - t0) > self.timeout_s:
                    timed_out = True
                    break
                try:
                    size = os.path.getsize(out_path)
                    mtime = os.path.getmtime(out_path)
                except FileNotFoundError:
                    size, mtime = 0, 0.0
                stdout = _read(out_path)
                body = _reply_body(stdout)
                if len(body) > len(prev_body):
                    yield HermesStreamEvent(text_delta=body[len(prev_body) :])
                    prev_body = body
                if size > 0 and (time.time() - mtime) > self.stable_after_s:
                    self._terminate(proc)
                    break
                time.sleep(self.poll_interval_s)
        finally:
            self._terminate(proc)
            self._active_proc = None
            out_f.close()
            err_f.close()

        elapsed_ms = (time.perf_counter() - t0) * 1000
        stdout = _read(out_path)
        stderr = _read(err_path)
        _unlink(out_path)
        _unlink(err_path)

        if cancelled:
            yield HermesStreamEvent(done=True, error="cancelled", elapsed_ms=elapsed_ms)
            raise HermesCancelledError("hermes chat cancelled")
        if timed_out and not prev_body:
            yield HermesStreamEvent(
                done=True,
                error=f"hermes chat timed out after {self.timeout_s}s",
                elapsed_ms=elapsed_ms,
            )
            return

        text = _reply_body(stdout)
        sid = _find_session_id(stdout, stderr)
        if not text:
            yield HermesStreamEvent(
                done=True,
                error="hermes chat produced no reply",
                elapsed_ms=elapsed_ms,
            )
            return
        if len(text) > len(prev_body):
            yield HermesStreamEvent(text_delta=text[len(prev_body) :])
        yield HermesStreamEvent(done=True, session_id=sid, elapsed_ms=elapsed_ms)

    @staticmethod
    def _terminate(proc) -> None:
        if proc.poll() is not None:
            return
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(os.getpgid(proc.pid), sig)
            except (ProcessLookupError, PermissionError):
                return
            try:
                proc.wait(timeout=3)
                return
            except Exception:
                continue


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def _unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _find_session_id(*streams: str) -> str | None:
    for s in streams:
        m = re.search(r"session_id:\s*(\S+)", s)
        if m:
            return m.group(1)
    return None


def _reply_body(stdout: str) -> str:
    """STDOUT 在 -Q 模式下即回复正文；去掉可能混入的 session_id 行。"""
    lines = []
    for line in stdout.strip().splitlines():
        if re.match(r"^session_id:\s*\S+", line.strip()):
            continue
        lines.append(line.rstrip())
    return "\n".join(lines).strip()
