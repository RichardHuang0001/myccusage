import os
import subprocess
from PIL import Image, ImageDraw

# 以脚本自身所在目录为基准解析输出路径。
# 旧实现使用 "macos/AppIcon.icns" 这类相对当前工作目录的路径，
# 一旦从 pip 安装位置( site-packages )被调用，就会在用户当前目录下乱建 macos/ 目录。
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def create_app_icon():
    size = 1024
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. 绘制外部毛玻璃微光圆角外框 (macOS Squircle)
    margin = 80
    rect = [(margin, margin), (size - margin, size - margin)]
    radius = 190

    # 绘制深色底座
    draw.rounded_rectangle(rect, radius=radius, fill=(15, 23, 42, 255), outline=(56, 189, 248, 120), width=6)

    # 2. 绘制科技感渐变环
    center = (size // 2, size // 2)
    ring_radius = 280
    ring_width = 36
    
    # 环形底色轨道
    draw.ellipse(
        [
            (center[0] - ring_radius, center[1] - ring_radius),
            (center[0] + ring_radius, center[1] + ring_radius)
        ],
        outline=(30, 41, 59, 255),
        width=ring_width
    )

    # 环形高亮进度 (270度圆弧)
    draw.arc(
        [
            (center[0] - ring_radius, center[1] - ring_radius),
            (center[0] + ring_radius, center[1] + ring_radius)
        ],
        start=135,
        end=45,
        fill=(52, 211, 153, 255),
        width=ring_width
    )

    # 3. 中心图标：绘制能量闪电/算力象征
    pts = [
        (center[0] + 30, center[1] - 160),
        (center[0] - 100, center[1] + 20),
        (center[0] - 10, center[1] + 20),
        (center[0] - 40, center[1] + 160),
        (center[0] + 100, center[1] - 20),
        (center[0] + 10, center[1] - 20)
    ]
    draw.polygon(pts, fill=(56, 189, 248, 255))

    # 4. 生成 Apple 规范的 iconset
    iconset_dir = os.path.join(BASE_DIR, "AppIcon.iconset")
    os.makedirs(iconset_dir, exist_ok=True)

    sizes = [
        (16, "icon_16x16.png"),
        (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"),
        (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"),
        (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"),
        (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"),
        (1024, "icon_512x512@2x.png")
    ]

    for s, name in sizes:
        resized = img.resize((s, s), Image.Resampling.LANCZOS)
        resized.save(os.path.join(iconset_dir, name))

    # 调用 iconutil 打包成 .icns
    icns_path = os.path.join(BASE_DIR, "AppIcon.icns")
    subprocess.run(["iconutil", "-c", "icns", iconset_dir, "-o", icns_path], check=True)
    print(f"✅ 已成功生成 macOS 官方图标: {icns_path}")

if __name__ == "__main__":
    create_app_icon()
