import os
from PIL import Image, ImageDraw, ImageFont

# Canvas: 3:4 aspect ratio (1080 x 1440)
# 设定画布基础大小，契合小红书封面 3:4 最佳展示比例
W, H = 1080, 1440
img = Image.new("RGB", (W, H), color="#0c111c")  # 使用深色暗黑风格作为主基调背景
draw = ImageDraw.Draw(img)

# Font helper: ensure Chinese font handles Chinese text properly
# 加载系统字体，为防止中文乱码和排版难看，分别针对中文字符、英文字符和等宽代码块指定专用字体
FONT_CN = '/System/Library/Fonts/Hiragino Sans GB.ttc'
FONT_EN = '/System/Library/Fonts/Helvetica.ttc'
FONT_MONO = '/System/Library/Fonts/Menlo.ttc'

font_title = ImageFont.truetype(FONT_CN, 54)
font_subtitle = ImageFont.truetype(FONT_CN, 28)
font_badge = ImageFont.truetype(FONT_CN, 22)
font_card_num = ImageFont.truetype(FONT_EN, 54)
font_card_label = ImageFont.truetype(FONT_CN, 24)
font_card_sub = ImageFont.truetype(FONT_CN, 20)
font_feature_title = ImageFont.truetype(FONT_CN, 26)
font_feature_desc = ImageFont.truetype(FONT_CN, 20)
font_footer_label = ImageFont.truetype(FONT_CN, 24)
font_footer_cmd = ImageFont.truetype(FONT_MONO, 26)
font_footer_url = ImageFont.truetype(FONT_EN, 26)

# 1. Top Accent Line
# 顶部装饰线条，提升页面视觉层级与科技感
draw.rectangle([(0, 0), (W, 6)], fill="#3b82f6")

# 2. Top Tag Badges (No emoji, clean minimalist badges)
# 顶部标签区域绘制。通过循环动态计算文本宽度，实现响应式标签渲染，避免硬编码带来的错位问题
y = 65
badges = [
    ("纯本地离线", "#10b981", "#064e3b"),
    ("支持 7 大 Agent", "#38bdf8", "#0c4a6e"),
    ("MIT 开源", "#f59e0b", "#78350f")
]

cur_x = 70
for text, border_c, bg_c in badges:
    bbox = font_badge.getbbox(text)
    tw = bbox[2] - bbox[0]  # 获取文本实际渲染宽度
    # 画出带圆角的标签边框背景
    draw.rounded_rectangle([(cur_x, y), (cur_x + tw + 36, y + 42)], radius=8, fill="#162032", outline=border_c, width=1)
    draw.text((cur_x + 18, y + 8), text, font=font_badge, fill="#f1f5f9")
    cur_x += tw + 56  # 更新下一个标签的起始 X 坐标

# 3. Main Title & Subtitle
# 主标题与副标题渲染，引导核心用户关注
y = 135
draw.text((70, y), "AI 编程用量与成本账本", font=font_title, fill="#ffffff")
y += 75
draw.text((70, y), "myccusage · 本地多 Agent 会话分析与暗黑看板", font=font_subtitle, fill="#94a3b8")

# 4. Metric Highlights Cards (Row of 3 cards)
# 核心指标卡片，并排展示3个突出数据
y = 265
cards = [
    {
        "num": "393.7M",
        "color": "#ffffff",
        "label": "总 Token 消耗",
        "sub": "实测 14 天 94 笔任务"
    },
    {
        "num": "90.0%",
        "color": "#38bdf8",
        "label": "KV Cache 命中率",
        "sub": "Prompt 节省大部分成本"
    },
    {
        "num": "¥466.2",
        "color": "#10b981",
        "label": "等效参考费用",
        "sub": "按 Gemini 3.8 Flash 折算"
    }
]

card_w = 295
gap = 25
start_x = 70

for i, c in enumerate(cards):
    cx = start_x + i * (card_w + gap)  # 动态计算每张卡片的 X 偏移量
    # 绘制深灰色卡片背板并添加微弱边缘边框
    draw.rounded_rectangle([(cx, y), (cx + card_w, y + 175)], radius=14, fill="#151d2a", outline="#26354a", width=1)
    draw.text((cx + 20, y + 20), c["num"], font=font_card_num, fill=c["color"])
    draw.text((cx + 20, y + 92), c["label"], font=font_card_label, fill="#e2e8f0")
    draw.text((cx + 20, y + 130), c["sub"], font=font_card_sub, fill="#64748b")

# 5. Preview Screenshot (Embedded real UI)
# 嵌入真实的软件截图，增强真实感和说服力
y = 470
overview_path = "docs/images/dashboard-overview.png"
if os.path.exists(overview_path):
    ov_img = Image.open(overview_path)
    target_w = 940
    # 等比例缩放截图以适应设定的宽度要求
    ratio = target_w / ov_img.width
    target_h = int(ov_img.height * ratio)
    ov_resized = ov_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
    
    # Outer Glow border: 绘制带蓝色高亮描边的外框模拟外发光效果
    draw.rounded_rectangle([(68, y - 2), (68 + target_w + 4, y + target_h + 4)], radius=16, fill="#1e293b", outline="#2563eb", width=2)
    # 将调整好尺寸的截图粘合回主画板
    img.paste(ov_resized, (70, y))
    y += target_h + 35

# 6. Core Features Checklist (2 columns, 4 cards)
# 核心特性两列式排列，优化空间利用率
y = 1045
features = [
    ("数据隐私安全", "纯本地单机只读解析，不向外上传代码与对话"),
    ("轻量零常驻后台", "零多余守护进程，关闭网页 30 秒后台自动退出"),
    ("自动提取会话标题", "直读本地 SQLite / Protobuf 还原任务名称"),
    ("双统计模式与换算", "支持日度防漂移账本与全生命周期累计总览")
]

for i, (f_title, f_desc) in enumerate(features):
    # 根据索引计算奇偶，分分布在左右两列
    fx = 70 if i % 2 == 0 else 550
    # 通过整除换算出行偏移量
    fy = y + (i // 2) * 85
    draw.rounded_rectangle([(fx, fy), (fx + 460, fy + 72)], radius=10, fill="#131b27", outline="#222f42", width=1)
    
    # Dot bullet: 蓝色的特征点符号
    draw.ellipse([(fx + 18, fy + 22), (fx + 26, fy + 30)], fill="#38bdf8")
    draw.text((fx + 36, fy + 12), f_title, font=font_feature_title, fill="#f1f5f9")
    draw.text((fx + 36, fy + 44), f_desc, font=font_feature_desc, fill="#94a3b8")

# 7. Bottom Box: Install command & GitHub Link
# 底部大区域，呼吁用户行动（CTA），展示安装方式及代码仓地址
y = 1245
draw.rounded_rectangle([(70, y), (W - 70, y + 140)], radius=16, fill="#0f172a", outline="#3b82f6", width=2)

# Row 1: Command
draw.text((100, y + 25), "快速安装运行:", font=font_footer_label, fill="#94a3b8")
draw.text((260, y + 23), "pip install myccusage && myccusage ui", font=font_footer_cmd, fill="#38bdf8")

# Row 2: GitHub
draw.text((100, y + 80), "GitHub 开源:", font=font_footer_label, fill="#94a3b8")
draw.text((260, y + 80), "github.com/RichardHuang0001/myccusage", font=font_footer_url, fill="#f8fafc")

# Save high quality PNG
output_path = "docs/images/xhs-cover.png"
# 保存为高质量图片，确保在社交媒体上不会过度模糊
img.save(output_path, quality=95)
print(f"Cover regenerated cleanly at: {output_path}")
