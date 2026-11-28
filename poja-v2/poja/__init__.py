"""poja-v2 — 破甲插件 v2（CR破甲助手 1.0.50 机制的 clean-room 二次实现）。

五机制:
  M1  二进制内拒绝段 · 等长原地替换      poja.m1_binpatch
  M2  EXE 级人格通道 · 启动器替身        poja.m2_exeshim
  M3  服务端/本地双层替换正文           poja.m3_overlay
  M4  人格文件首行锚定 + 尾部防注入      poja.m4_anchor
  M5  持久注入 + 可回滚                 poja.m5_guard

声明与协议见仓库根 声明.md / LICENSE / NOTICE.md。
"""

__version__ = "2.0.0"
__upstream__ = "CR破甲助手 1.0.50 (专有闭源商业软件, 无开源协议)"