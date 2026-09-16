#!/usr/bin/env python3
"""
myccusage:
多 Agent 会话用量与 DeepSeek-V4.1-Flash 高峰期等效计费工具。
支持双模分流:
  - 默认 [-d / --daily]:   每日会话账本模式（不混淆前日用量，按此日、此 Session 精确分列，日/周小计绝不漂移）
  - 指定 [-s / --session]: 项目总览模式（专注每个 Project / Session 的全生命周期累计总消耗）
  - 网页 [--web / -w]:     启动现代化本地 Web 仪表盘 (默认端口 8488)

支持 Agent:
  - Google Antigravity: --agy, --antigravity
  - Claude Code:        --claude
  - Hermes Agent:       --hermes
  - OpenAI Codex:       --codex
  - Grok:               --grok
  - Pi Agent:           --pi
  - OpenCode:           --opencode
  - WorkBuddy:          --workbuddy
"""

import os
import sys

# 动态解析真实脚本所在目录，确保无论通过软链接、PATH 还是直接调用均能正确导入
real_path = os.path.realpath(__file__)
repo_root = os.path.dirname(real_path)
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from myccusage_lib.cli import main

if __name__ == "__main__":
    main()
