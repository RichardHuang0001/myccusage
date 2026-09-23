#!/usr/bin/env python3
"""
myccusage 命令行入口薄壳 (launcher shim)。

真实实现全部位于 myccusage_lib 包内：参数解析、表格渲染与 Web 调度见 cli.py。
本文件只做一件事——把仓库根目录注入 sys.path，保证通过软链接
（install.sh 会在 ~/.local/bin 建立）或从任意工作目录执行时都能正确导入包，
随后把控制权交给 cli.main()。

- Windows 终端的 UTF-8 编码防护由 myccusage_lib.cli 在导入时统一施加，此处不再重复实现；
- 完整用法请见 README.md，或执行 `myccusage --help`。
"""

import os
import sys

# 解开软链接解析真实路径，确保从任意目录 / 软链接调用都能定位到 myccusage_lib
_REPO_ROOT = os.path.dirname(os.path.realpath(__file__))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from myccusage_lib.cli import main

if __name__ == "__main__":
    main()
