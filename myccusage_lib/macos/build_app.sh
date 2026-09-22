#!/usr/bin/env bash
set -e

# 定位脚本所在目录与项目根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "=================================================="
echo "  🚀 正在构建 myccusage 原生 macOS 常驻应用..."
echo "=================================================="

# 0. 确保退出旧版本常驻进程与后台守护服务
echo "🛑 正在退出旧版本常驻进程与后台守护..."
killall myccusage 2>/dev/null || true
pkill -f "myccusage_lib.cli.*--daemon" 2>/dev/null || true
sleep 0.5

# 1. 确保图标资源已生成
if [ ! -f "${SCRIPT_DIR}/AppIcon.icns" ]; then
    echo "🎨 正在生成应用高分辨率图标..."
    python3 "${SCRIPT_DIR}/generate_icon.py"
fi

# 2. 编译原生 Swift 宿主
echo "⚡️ 正在使用 Apple Swift 编译器构建原生二进制..."
cd "${ROOT_DIR}"
swiftc -O -parse-as-library \
    -framework Cocoa \
    -framework SwiftUI \
    -framework Combine \
    "${SCRIPT_DIR}/main.swift" \
    -o "${SCRIPT_DIR}/myccusage-bin"

# 3. 创建 App Bundle 结构
APP_NAME="myccusage.app"
if [ -f "${ROOT_DIR}/pyproject.toml" ]; then
    DIST_DIR="${ROOT_DIR}/dist"
else
    DIST_DIR="${HOME}/Applications"
fi
APP_DIR="${DIST_DIR}/${APP_NAME}"
CONTENTS_DIR="${APP_DIR}/Contents"
MACOS_DIR="${CONTENTS_DIR}/MacOS"
RESOURCES_DIR="${CONTENTS_DIR}/Resources"

echo "📦 正在组装 ${APP_NAME} 到 ${DIST_DIR}..."
rm -rf "${APP_DIR}"
mkdir -p "${MACOS_DIR}"
mkdir -p "${RESOURCES_DIR}"

# 4. 拷贝可执行文件并赋予执行权限
cp "${SCRIPT_DIR}/myccusage-bin" "${MACOS_DIR}/myccusage"
chmod +x "${MACOS_DIR}/myccusage"

# 5. 拷贝应用图标
cp "${SCRIPT_DIR}/AppIcon.icns" "${RESOURCES_DIR}/AppIcon.icns"

# 6. 生成标准 Info.plist
cat << 'EOF' > "${CONTENTS_DIR}/Info.plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>zh_CN</string>
    <key>CFBundleExecutable</key>
    <string>myccusage</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundleIdentifier</key>
    <string>com.richard.myccusage</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>myccusage</string>
    <key>CFBundleDisplayName</key>
    <string>myccusage</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.5.1</string>
    <key>CFBundleVersion</key>
    <string>1.5.1</string>
    <key>LSMinimumSystemVersion</key>
    <string>13.0</string>
    <key>LSUIElement</key>
    <false/>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSPrincipalClass</key>
    <string>NSApplication</string>
</dict>
</plist>
EOF

# 清理临时编译产物
rm -f "${SCRIPT_DIR}/myccusage-bin"
rm -rf "${SCRIPT_DIR}/AppIcon.iconset"

echo "=================================================="
echo "  🎉 构建成功！"
echo "  📍 应用路径: ${APP_DIR}"
echo "  💡 启动方式: open \"${APP_DIR}\""
echo "=================================================="
