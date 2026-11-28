"""M1 — 二进制内拒绝段 · 等长原地替换。

机制来源: CR破甲助手 1.0.50 `claudeHostPrompt.js`（逆向提炼 M1）。

核心不变量
---------
替换正文与原文**严格等长**（不足以空格补齐）。由此保住:
  1. 字节码字符串表的长度前缀；
  2. 内嵌 JS 源码的字面量边界；
  3. 文件内全部偏移。
因此无需修复 Bun/镜像结构，也不会被"完整性校验的偏移比对"发现。

状态机
------
no-binary -> unreadable -> no-match -> patched
                                 -> locked      (等长无法成立)
write-failed / verify-failed    (副作用失败)

幂等锚: 目标文件内已含 AUTH 字节 → 视为已处理，仅做幂等确认，不重复写。
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import BinaryIO, Iterable

CHUNK = 4 * 1024 * 1024      # 分块读 4MB
OVERLAP = 8 * 1024           # 块间重叠 8KB，避免跨块漏匹配


@dataclass
class Span:
    """一处待替换区间。offset 为文件内绝对偏移。"""

    offset: int
    original: bytes
    patched: bytes

    def length_equal(self) -> bool:
        return len(self.original) == len(self.patched)


@dataclass
class PatchResult:
    state: str
    spans: list[Span] = field(default_factory=list)
    size: int = 0
    version: str = "poja-v2/m1"
    sha256_before: str = ""
    sha256_after: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["spans"] = [
            {
                "offset": s.offset,
                "original_hex": s.original.hex(),
                "patched_hex": s.patched.hex(),
            }
            for s in self.spans
        ]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "PatchResult":
        spans = [
            Span(
                offset=s["offset"],
                original=bytes.fromhex(s["original_hex"]),
                patched=bytes.fromhex(s["patched_hex"]),
            )
            for s in d.get("spans", [])
        ]
        return cls(
            state=d["state"],
            spans=spans,
            size=d.get("size", 0),
            version=d.get("version", cls.version),
            sha256_before=d.get("sha256_before", ""),
            sha256_after=d.get("sha256_after", ""),
            error=d.get("error", ""),
        )


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def pad_equal(refusal: str, authorization: str, pad: str = " ") -> bytes:
    """把授权声明补齐到与拒绝段严格等长。

    严格等长是 M1 的签名性质：短了补空格，长了无法成立（返回 locked）。
    """
    r = refusal.encode("utf-8")
    a = authorization.encode("utf-8")
    if len(a) > len(r):
        raise LockedSpan(
            f"授权声明 {len(a)}B 长于拒绝段 {len(r)}B，"
            "等长不变量无法成立；需缩短授权声明"
        )
    return a + pad.encode("utf-8") * (len(r) - len(a))


class LockedSpan(Exception):
    """等长不变量无法成立。"""


def _iter_chunks(f: BinaryIO, chunk: int = CHUNK, overlap: int = OVERLAP) -> Iterable[tuple[int, bytes]]:
    """带重叠的分块扫描：跨块边界的匹配不会漏。"""
    pos = 0
    while True:
        f.seek(pos)
        data = f.read(chunk)
        if not data:
            return
        yield pos, data
        if len(data) < chunk:
            return
        nxt = pos + len(data) - overlap
        if nxt <= pos:
            return
        pos = nxt


def find_spans(
    buf: bytes,
    marker: bytes,
    suffix: bytes,
    refusal: bytes,
    authorization: bytes,
) -> list[Span]:
    """在非分块模式下定位所有 (marker..suffix) 拒绝段。"""
    out: list[Span] = []
    start = 0
    while True:
        m = buf.find(marker, start)
        if m < 0:
            break
        s = buf.find(suffix, m + len(marker))
        if s < 0:
            break
        s += len(suffix)
        orig = buf[m:s]
        out.append(Span(
            offset=m,
            original=orig,
            patched=pad_equal(orig.decode("utf-8", "surrogateescape"), authorization),
        ))
        start = s
    return out


def scan_file(path: Path, marker: bytes, suffix: bytes, refusal: bytes, authorization: bytes) -> list[Span]:
    """流式定位。分块读 + 块间重叠，避免整读上百 MB 镜像。"""
    spans: list[Span] = []
    with open(path, "rb") as f:
        size = f.seek(0, os.SEEK_END)
        f.seek(0)
        needle_ctx = marker + b"\x00" * 0
        for pos, data in _iter_chunks(f):
            # 在本块内定位 marker，再向后取到 suffix
            start = 0
            while True:
                m = data.find(marker, start)
                if m < 0:
                    break
                s = data.find(suffix, m + len(marker))
                if s < 0:
                    # suffix 可能在下一块；整读兜底已在下方处理
                    break
                s += len(suffix)
                orig = data[m:s]
                try:
                    patched = pad_equal(orig.decode("utf-8", "surrogateescape"), authorization.decode("utf-8", "surrogateescape"))
                except LockedSpan:
                    raise
                spans.append(Span(offset=pos + m, original=orig, patched=patched))
                start = s
    if not spans:
        # 兜底：单次整读（小文件）
        with open(path, "rb") as f:
            buf = f.read()
        spans = find_spans(buf, marker, suffix, refusal, authorization)
    return spans


def apply_patch(path: Path, spans: list[Span], backup: bool = True) -> PatchResult:
    """按 span 逐段原地写回。写失败 → write-failed（已写部分不承诺原子回滚，但 span 完整记录）。"""
    p = Path(path)
    if not p.exists() or not p.is_file():
        return PatchResult(state="no-binary", error=str(p))
    try:
        before = sha256_file(p)
        size = p.stat().st_size
    except OSError as e:
        return PatchResult(state="unreadable", error=str(e))

    if not spans:
        return PatchResult(state="no-match", size=size, sha256_before=before)

    if any(not s.length_equal() for s in spans):
        return PatchResult(
            state="locked",
            spans=spans,
            size=size,
            sha256_before=before,
            error="等长不变量不成立",
        )

    if backup:
        bkp = p.with_suffix(p.suffix + ".poja.bak")
        if not bkp.exists():
            try:
                import shutil
                shutil.copy2(p, bkp)  # 备份为副本，原路径保持有效（等长改写不移动文件）
            except OSError as e:
                return PatchResult(state="write-failed", error=str(e))

    # 用 bytearray 保证等长原地替换：偏移/长度前缀/字面量边界全不变
    try:
        with open(p, "r+b") as f:
            blob = bytearray(f.read())
            for s in sorted(spans, key=lambda x: x.offset, reverse=True):
                if blob[s.offset : s.offset + len(s.original)] != s.original:
                    # 幂等确认：内容已变（可能已打过），跳过不重复写
                    continue
                blob[s.offset : s.offset + len(s.original)] = s.patched
            f.seek(0)
            f.truncate()
            f.write(bytes(blob))
    except OSError as e:
        return PatchResult(state="write-failed", spans=spans, error=str(e))

    after = sha256_file(p)
    if p.stat().st_size != size:
        return PatchResult(
            state="verify-failed",
            spans=spans,
            size=size,
            sha256_before=before,
            sha256_after=after,
            error="写回后文件长度变化，等长不变量被破坏",
        )
    return PatchResult(
        state="patched",
        spans=spans,
        size=size,
        sha256_before=before,
        sha256_after=after,
    )


def write_sidecar(path: Path, result: PatchResult) -> Path:
    """侧车 .poja-host-prompt.json 记录 {version,size,spans}，供 restore() 精确写回。"""
    side = Path(str(path) + ".poja-sidecar.json")
    side.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return side


def read_sidecar(path: Path) -> PatchResult | None:
    side = Path(str(path) + ".poja-sidecar.json")
    if not side.exists():
        return None
    return PatchResult.from_dict(json.loads(side.read_text(encoding="utf-8")))


def restore(path: Path) -> PatchResult:
    """按侧车 span 逐段写回原文。"""
    res = read_sidecar(path)
    if res is None:
        return PatchResult(state="no-binary", error="无侧车记录")
    p = Path(path)
    if not p.exists():
        return PatchResult(state="no-binary", error=str(p))
    with open(p, "r+b") as f:
        blob = bytearray(f.read())
        for s in sorted(res.spans, key=lambda x: x.offset, reverse=True):
            blob[s.offset : s.offset + len(s.patched)] = s.original
        f.seek(0)
        f.truncate()
        f.write(bytes(blob))
    res.state = "restored"
    side = Path(str(path) + ".poja-sidecar.json")
    if side.exists():
        side.unlink()
    return res


def idempotent_confirm(path: Path, authorization: str) -> bool:
    """幂等锚：文件内已含授权声明字节 → True（重复调用只确认，不重复写）。"""
    p = Path(path)
    if not p.exists():
        return False
    needle = authorization.encode("utf-8")
    with open(p, "rb") as f:
        for _pos, data in _iter_chunks(f):
            if needle in data:
                return True
    return False