#!/usr/bin/env bash
#
# 兼容入口脚本（转发壳）：
# macOS 程序坞应用的真实源码统一维护在 myccusage_lib/macos/ 下 —— 该目录会随 Wheel 一起发布，
# 是 pip 安装用户与源码检出用户共用的唯一真源。
#
# 本脚本只做转发，不再持有任何源码副本：历史上仓库同时存在 macos/ 与 myccusage_lib/macos/
# 两份完全相同的 main.swift / build_app.sh，靠人手 cp 保持同步，任何一次漏同步都会导致
# 「仓库里是新的、用户装到的是旧的」这类难以察觉的漂移。保留此壳是为了让 README 中的
# `bash macos/build_app.sh` 用法与开发者习惯继续可用。
#
set -e

CALLER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CANONICAL="${CALLER_DIR}/../myccusage_lib/macos/build_app.sh"

if [ ! -f "${CANONICAL}" ]; then
    echo "❌ 未找到 macOS 源码构建脚本: ${CANONICAL}" >&2
    exit 1
fi

exec bash "${CANONICAL}" "$@"
