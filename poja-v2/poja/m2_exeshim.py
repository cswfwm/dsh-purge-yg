"""M2 — EXE 级人格通道（启动器替身）。

机制来源: CR破甲助手 1.0.50 `claudeShim.js`（逆向提炼 M2）。

事实依据
--------
Claude 桌面版以 SDK 模式拉起 CLI 时，`CLAUDE.md` 会被模型读成"用户轮附件"而非
system；`settings.json` 的 appendSystemPromptFile / systemPrompt / 环境变量**全部无效**；
唯一有效通道是启动参数 `--append-system-prompt-file <文件>`。

实现
----
把原可执行改名（claude.exe -> claude-real.exe），用一个等价功能的启动器占住原路径，
它把调用方全部参数原样转发，并追加 `--append-system-prompt-file <persona文件>`。
幂等：重复只比对摘要；可回滚：还原原版。失败不阻断其余。
"""

from __future__ import annotations

import hashlib
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# 阈值：>10MB 视为原版镜像；5–10MB 为不明二进制
THRESHOLD_LARGE = 10 * 1024 * 1024
THRESHOLD_UNKNOWN = 5 * 1024 * 1024

ARG_FLAG = "--append-system-prompt-file"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


@dataclass
class ShimResult:
    state: str
    shim_path: str = ""
    real_path: str = ""
    digest_before: str = ""
    digest_after: str = ""
    error: str = ""


def classify(path: Path) -> str:
    """按大小阈值分类目标二进制。"""
    size = path.stat().st_size
    if size > THRESHOLD_LARGE:
        return "real-image"
    if size >= THRESHOLD_UNKNOWN:
        return "unknown-binary"
    return "shim-candidate"


def shim_script(persona: Path, real: Path) -> str:
    """生成等价功能启动器。POSIX shell / Windows 双版本按需。"""
    if sys.platform.startswith("win"):
        return (
            "@echo off\r\n"
            f'"{real}" %* {ARG_FLAG} "{persona}"\r\n'
            f"exit /b %errorlevel%\r\n"
        )
    return (
        "#!/usr/bin/env sh\n"
        f"exec {shlex.quote(str(real))} \"$@\" {ARG_FLAG} {shlex.quote(str(persona))}\n"
    )


def install(exe: Path, persona: Path, suffix: str = ".real") -> ShimResult:
    """占住原路径：原版改名 -> 写启动器 -> 启动器转发并追加人格文件参数。"""
    if not exe.exists():
        return ShimResult(state="no-binary", error=str(exe))
    before = sha256_file(exe)
    cls = classify(exe)
    if cls == "unknown-binary":
        return ShimResult(
            state="unknown-binary",
            shim_path=str(exe),
            digest_before=before,
            error=f"大小位于 {THRESHOLD_UNKNOWN // 1024 // 1024}–"
            f"{THRESHOLD_LARGE // 1024 // 1024}MB，可能是别的程序，拒绝改名",
        )

    real = exe.with_name(exe.name + suffix)
    if not real.exists():
        try:
            exe.rename(real)
        except OSError as e:
            return ShimResult(state="write-failed", error=str(e))

    script = shim_script(persona, real)
    try:
        exe.write_text(script, encoding="utf-8")
        exe.chmod(0o755)
    except OSError as e:
        return ShimResult(state="write-failed", error=str(e))

    return ShimResult(
        state="shimmed",
        shim_path=str(exe),
        real_path=str(real),
        digest_before=before,
        digest_after=sha256_file(exe),
    )


def uninstall(exe: Path, suffix: str = ".real") -> ShimResult:
    """回滚：删启动器，还原原版。"""
    real = exe.with_name(exe.name + suffix)
    if not real.exists():
        return ShimResult(state="no-binary", error=f"原版 {real} 不存在")
    try:
        exe.unlink()
        real.rename(exe)
    except OSError as e:
        return ShimResult(state="write-failed", error=str(e))
    return ShimResult(state="restored", real_path=str(exe), digest_after=sha256_file(exe))


def is_idempotent(exe: Path, persona: Path, suffix: str = ".real") -> bool:
    """幂等：启动器已存在且引用当前 persona 文件 → True。"""
    real = exe.with_name(exe.name + suffix)
    if not (exe.exists() and real.exists()):
        return False
    try:
        text = exe.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return str(persona) in text and ARG_FLAG in text


def dry_run(exe: Path, persona: Path, suffix: str = ".real") -> str:
    """展示将生成的命令行，不落盘。"""
    real = exe.with_name(exe.name + suffix)
    return shlex.join([str(real), ARG_FLAG, str(persona)])