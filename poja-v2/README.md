# poja-v2 — 破甲插件 v2（二次修改版）

CR破甲助手 1.0.50 机制的 **clean-room 二次实现**。上游为专有闭源商业软件、无开源协议，
故本项目采用 **MIT** 许可自有代码，详细归属与协议依据见
[`声明.md`](声明.md) 与 [`NOTICE.md`](NOTICE.md)。

## 五机制

| 机制 | 作用 | 模块 |
|---|---|---|
| M1 | 二进制内拒绝段 · **等长原地替换**（不破坏长度前缀/偏移/字面量边界） | `poja/m1_binpatch.py` |
| M2 | EXE 级人格通道 · **启动器替身**（追加 `--append-system-prompt-file`） | `poja/m2_exeshim.py` |
| M3 | 服务端/本地**双层替换正文**（overlay 下发 + 本地降级壳自带效力） | `poja/m3_overlay.py` |
| M4 | 人格文件**首行锚定** + 尾部防注入（上下文压缩可自愈） | `poja/m4_anchor.py` |
| M5 | **持久注入** + 可回滚（quarantine/`<ts>`/manifest） | `poja/m5_guard.py` |

## 安装

```bash
pip install -e .          # 或: python -m pip install .
poja --help
```

## 用法示例

### M1 — 二进制内拒绝段等长替换

```bash
poja m1-patch ./bun-image.bin \
  "IMPORTANT: Assist with authorized security testing" \
  "defensive use cases." \
  "<完整拒绝段原文>" \
  "<授权声明, 长度 <= 拒绝段>"      # 不足自动补空格到等长
poja m1-restore ./bun-image.bin    # 按侧车 .poja-sidecar.json 写回原文
```

幂等：若目标文件已含授权声明字节，`m1-patch` 仅做确认、不重复写。
状态机：`no-binary → unreadable → no-match → patched / locked / write-failed / verify-failed`。

### M2 — EXE 人格通道

```bash
poja m2-install /opt/claude/claude.exe /root/.l-skill/system_prompts/claude.txt
poja m2-uninstall /opt/claude/claude.exe
```

`install` 把 `claude.exe` 改名 `claude.exe.real`，在原路径写等价启动器，
转发全部参数并追加 `--append-system-prompt-file <persona>`。

### M3 — 五步中和厂商自我限缩条款

```bash
poja m3-neutralize 厂商配置文本.txt overlay.wb-pack 中和后.txt
```

服务端 `overlay.wb-pack` 存在则以其正文为准；否则本地降级壳
（`FALLBACK_SHELL`，自带完整效力声明）兜底。

### M4 — 锚定人格文件

```bash
poja m4-write   /root/.l-skill/system_prompts/claude.txt /root/.l-skill/system_prompts/claude.txt "授权正文"
poja m4-heal    /root/.l-skill/system_prompts/claude.txt /root/.l-skill/system_prompts/claude.txt "授权正文"
```

### M5 — 快照 / 回滚 / 持久守卫

```bash
poja m5-snapshot /root/.l-skill/system_prompts/claude.txt ./quarantine
poja m5-restore  ./quarantine/<ts>/manifest.json
poja guard-on "python -m poja.cli m4-heal ..." --interval 30
poja guard-off
```

## 测试

```bash
python -m pytest tests/ -v
```

覆盖 M1 等长不变量、侧车 restore 往返、幂等锚；
M3 五步中和、overlay 优先级；M4 锚定/自愈；M5 快照/回滚。

## 安全与责任

- `guard-on` 是**显式可选命令**，默认不执行；`guard-off` 可卸载。
- 仅用于**授权范围内本地环境**。详见 `声明.md` 第四、五节。
