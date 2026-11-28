"""M5 — 持久注入 + 可回滚（quarantine/<ts>/manifest.json）。

机制来源: CR破甲助手 1.0.50 `countermeasure.js`（逆向提炼 M5）。

要点
----
- 注入内容被外部覆盖后，由定时任务（schtasks / cron / systemd-timer）定期重新打进
  已接入的客户端。
- 可回滚：所有改动进 quarantine/<ts>/ + manifest.json；`restore(manifest)` 一条命令
  原样搬回。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

GUARD_INTERVAL_MINUTES = 30


@dataclass
class Manifest:
    ts: str
    items: list[dict] = field(default_factory=list)  # {action, src, dst}

    def to_dict(self) -> dict:
        return {"ts": self.ts, "items": self.items}


def snapshot(inject_path: Path, quarantine_root: Path) -> Manifest:
    """把注入位置当前内容快照进 quarantine/<ts>/，记录 manifest 供 restore() 原样搬回。

    - home: 注入位置（改动发生的真实路径）
    - dst : quarantine 里的快照副本
    """
    ts = time.strftime("%Y%m%d-%H%M%S")
    qdir = quarantine_root / ts
    qdir.mkdir(parents=True, exist_ok=True)
    items = []
    home = Path(inject_path)
    if home.exists():
        dst = qdir / home.name
        if home.is_dir():
            shutil.copytree(home, dst)
        else:
            shutil.copy2(home, dst)
        items.append({"action": "copy", "home": str(home), "dst": str(dst)})
    man = Manifest(ts=ts, items=items)
    (qdir / "manifest.json").write_text(json.dumps(man.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return man


def restore(manifest_path: Path) -> list[str]:
    """按 manifest 把改动原样搬回：quarantine 副本(dst) -> 注入位置(home)。"""
    if not manifest_path.exists():
        return ["no manifest"]
    man = json.loads(manifest_path.read_text(encoding="utf-8"))
    out = []
    for it in man.get("items", []):
        home = Path(it["home"])
        dst = Path(it["dst"])
        if home.exists() and home.is_dir():
            shutil.rmtree(home)
        if dst.is_dir():
            shutil.copytree(dst, home)
        else:
            home.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dst, home)
        out.append(f"restored {home} <- {dst}")
    return out


def schedule_guard(apply_cmd: list[str], interval_min: int = GUARD_INTERVAL_MINUTES) -> str:
    """注册定时任务，每 interval 分钟重新执行 apply_cmd（注入被覆盖后自愈）。"""
    if sys.platform.startswith("win"):
        return _schedule_windows(apply_cmd, interval_min)
    return _schedule_cron(apply_cmd, interval_min)


def _schedule_windows(cmd: list[str], interval_min: int) -> str:
    name = "poja-guard"
    action = " ".join(f'"{c}"' for c in cmd)
    subprocess.run(
        ["schtasks", "/Create", "/TN", name, "/TR", action,
         "/SC", "MINUTE", "/MO", str(interval_min), "/F"],
        check=False,
    )
    return f"schtasks /Create /TN {name} /SC MINUTE /MO {interval_min}"


def _schedule_cron(cmd: list[str], interval_min: int) -> str:
    line = f"*/{interval_min} * * * * {_shell_join(cmd)}\n"
    crontab = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    cur = crontab.stdout if crontab.returncode == 0 else ""
    if "poja-guard" not in cur:
        cur += "# poja-guard\n" + line
        subprocess.run(["crontab", "-"], input=cur, text=True, check=False)
    return line.strip()


def _shell_join(cmd: list[str]) -> str:
    import shlex
    return shlex.join(cmd)


def unset_guard() -> str:
    """卸载定时任务（回滚配套）。"""
    if sys.platform.startswith("win"):
        subprocess.run(["schtasks", "/Delete", "/TN", "poja-guard", "/F"], check=False)
        return "schtasks /Delete /TN poja-guard /F"
    subprocess.run(["crontab", "-l"], capture_output=True)
    out = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if out.returncode == 0:
        lines = [l for l in out.stdout.splitlines() if "poja-guard" not in l]
        subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n", text=True, check=False)
    return "crontab: poja-guard removed"