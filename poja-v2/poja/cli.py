"""poja-v2 统一 CLI。

用法: poja <command> [args]
  m1-patch PATH MARKER SUFFIX REFUSAL AUTHORIZATION  等长原地替换
  m1-restore PATH                                   按侧车写回原文
  m2-install EXE PERSONA                            占路径 + 追加人格参数
  m2-uninstall EXE                                  回滚原版
  m3-neutralize TEXT FILE OUTFILE                   五步中和厂商自我限缩条款
  m4-write PERSONA OUTFILE BODY                     写锚定人格文件
  m4-heal PERSONA OUTFILE BODY                      锚丢失自愈
  m5-snapshot SOURCE QUARANTINE                     改动快照 + manifest
  m5-restore MANIFEST                               原样搬回
  guard-on CMD [--interval N]                       注册定时重注入
  guard-off                                          卸载定时任务
  status PATH EXE PERSONA                           查看幂等/锚/侧车状态
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, m1_binpatch as M1, m2_exeshim as M2, m3_overlay as M3, m4_anchor as M4, m5_guard as M5


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def cmd_m1_patch(a):
    path = Path(a.path)
    marker = a.marker.encode("utf-8")
    suffix = a.suffix.encode("utf-8")
    try:
        auth = M1.pad_equal(a.refusal, a.authorization)
    except M1.LockedSpan as e:
        _print({"state": "locked", "error": str(e)})
        return 2
    spans = M1.scan_file(path, marker, suffix, a.refusal.encode(), auth)
    if M1.idempotent_confirm(path, a.authorization):
        _print({"state": "patched", "note": "幂等确认: 已含授权声明, 未重复写"})
        return 0
    res = M1.apply_patch(path, spans)
    if res.state == "patched":
        M1.write_sidecar(path, res)
    _print(res.to_dict())
    return 0 if res.state == "patched" else 1


def cmd_m1_restore(a):
    res = M1.restore(Path(a.path))
    _print(res.to_dict())
    return 0 if res.state == "restored" else 1


def cmd_m2_install(a):
    res = M2.install(Path(a.exe), Path(a.persona))
    _print(res.__dict__)
    return 0 if res.state == "shimmed" else 1


def cmd_m2_uninstall(a):
    res = M2.uninstall(Path(a.exe))
    _print(res.__dict__)
    return 0 if res.state == "restored" else 1


def cmd_m3(a):
    pack = M3.load_overlay(Path(a.file)) if a.file and Path(a.file).exists() else M3.OverlayPack(body=M3.FALLBACK_SHELL)
    text = Path(a.text).read_text(encoding="utf-8") if a.text != "-" else sys.stdin.read()
    _print({"before": M3.scan_clauses(text), "after": M3.scan_clauses(M3.neutralize(text, pack))})
    out = Path(a.outfile)
    out.write_text(M3.neutralize(text, pack), encoding="utf-8")
    return 0


def cmd_m4_write(a):
    _print(M4.write(Path(a.outfile), a.body).__dict__)
    return 0


def cmd_m4_heal(a):
    _print(M4.heal(Path(a.outfile), a.body).__dict__)
    return 0


def cmd_m5_snapshot(a):
    man = M5.snapshot(Path(a.source), Path(a.quarantine))
    _print(man.to_dict())
    return 0


def cmd_m5_restore(a):
    _print(M5.restore(Path(a.manifest)))
    return 0


def cmd_guard_on(a):
    line = M5.schedule_guard([a.cmd], interval_min=a.interval)
    _print({"scheduled": line})
    return 0


def cmd_guard_off():
    _print({"result": M5.unset_guard()})
    return 0


def cmd_status(a):
    path, exe, persona = Path(a.path), Path(a.exe), Path(a.persona)
    _print({
        "m1_sidecar": M1.read_sidecar(path) is not None,
        "m1_idempotent": M1.idempotent_confirm(path, ""),
        "m2_installed": M2.is_idempotent(exe, persona),
        "m4_anchored": M4.is_anchored(persona),
        "version": __version__,
    })
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="poja", description=f"poja-v2 {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("m1-patch"); s.add_argument("path"); s.add_argument("marker"); s.add_argument("suffix")
    s.add_argument("refusal"); s.add_argument("authorization"); s.set_defaults(f=cmd_m1_patch)

    s = sub.add_parser("m1-restore"); s.add_argument("path"); s.set_defaults(f=cmd_m1_restore)

    s = sub.add_parser("m2-install"); s.add_argument("exe"); s.add_argument("persona"); s.set_defaults(f=cmd_m2_install)

    s = sub.add_parser("m2-uninstall"); s.add_argument("exe"); s.set_defaults(f=cmd_m2_uninstall)

    s = sub.add_parser("m3-neutralize"); s.add_argument("text"); s.add_argument("file", nargs="?"); s.add_argument("outfile")
    s.set_defaults(f=cmd_m3)

    s = sub.add_parser("m4-write"); s.add_argument("persona"); s.add_argument("outfile"); s.add_argument("body"); s.set_defaults(f=cmd_m4_write)

    s = sub.add_parser("m4-heal"); s.add_argument("persona"); s.add_argument("outfile"); s.add_argument("body"); s.set_defaults(f=cmd_m4_heal)

    s = sub.add_parser("m5-snapshot"); s.add_argument("source"); s.add_argument("quarantine"); s.set_defaults(f=cmd_m5_snapshot)

    s = sub.add_parser("m5-restore"); s.add_argument("manifest"); s.set_defaults(f=cmd_m5_restore)

    s = sub.add_parser("guard-on"); s.add_argument("cmd"); s.add_argument("--interval", type=int, default=30); s.set_defaults(f=cmd_guard_on)

    s = sub.add_parser("guard-off"); s.set_defaults(f=cmd_guard_off)

    s = sub.add_parser("status"); s.add_argument("path"); s.add_argument("exe"); s.add_argument("persona"); s.set_defaults(f=cmd_status)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.f(args)


if __name__ == "__main__":
    raise SystemExit(main())