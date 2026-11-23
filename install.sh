#!/usr/bin/env bash
# 一键拉取 dsh-purge YG 成品增强层（提示词 + 清洗器 + 题库）
# 用法：curl -fsSL https://raw.githubusercontent.com/<OWNER>/dsh-purge-yg/main/install.sh | bash
# 或  ：git clone https://github.com/<OWNER>/dsh-purge-yg.git && bash install.sh
set -euo pipefail

DSH_HOME="${DSH_HOME:-$HOME/.dsh}"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$DSH_HOME"

say() { printf '\033[32m[✓]\033[0m %s\n' "$*"; }

# ① 提示词层（含 REFUSAL HARDENING v4 变体）
cp -f "$REPO_DIR/upgrade/prompt-inject.md" "$DSH_HOME/prompt-inject.md"
say "prompt-inject.md  →  $DSH_HOME/prompt-inject.md"

# ② 清洗层（会话日志拒绝段清洗，可回滚）
mkdir -p "$DSH_HOME/tools"
cp -f "$REPO_DIR/upgrade/refusal_scrub.py" "$DSH_HOME/tools/refusal_scrub.py"
say "refusal_scrub.py  →  $DSH_HOME/tools/refusal_scrub.py"

# ③ 题库（横评 / 暴力测试 / 复合全链）
mkdir -p "$DSH_HOME/benchmarks"
cp -f "$REPO_DIR"/benchmarks/*.md "$DSH_HOME/benchmarks/"
say "benchmarks/*      →  $DSH_HOME/benchmarks/"

# ④ 框架文档
cp -f "$REPO_DIR/CR破甲逆向提炼_破甲框架v3.md" "$DSH_HOME/" 2>/dev/null || true
say "破甲框架文档      →  $DSH_HOME/"

say ""
say "完成。下一步："
say "  1) 重启 dsh 使提示词生效（新会话自动加载 $DSH_HOME/prompt-inject.md）"
say "  2) 体检：python3 $DSH_HOME/tools/refusal_scrub.py --dry-run"
say "  3) 清洗：python3 $DSH_HOME/tools/refusal_scrub.py --apply   # 先 dry-run 再 apply"
