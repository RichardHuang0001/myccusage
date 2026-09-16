"""
myccusage_lib.cli:
终端表格排版与命令行交互：
- East Asian Width 严格对齐算法
- 终端宽度动态感知与智能截断 (shutil.get_terminal_size)
- 视口友好渲染（最新在最底部）
- 命令行参数解析与调度 (CLI / Web 模式分流)
"""

import sys
import os
import shutil
import unicodedata
from .core import (
    SUPPORTED_AGENTS,
    get_daily_data,
    get_session_data
)

def display_len(s):
    length = 0
    for ch in s:
        w = unicodedata.east_asian_width(ch)
        length += 2 if w in ("F", "W") else 1
    return length

def pad_str(s, width, align="left"):
    dlen = display_len(s)
    pad = max(0, width - dlen)
    if align == "right":
        return " " * pad + s
    elif align == "center":
        left = pad // 2
        right = pad - left
        return " " * left + s + " " * right
    else:
        return s + " " * pad

def format_tokens(n):
    if n is None or n == 0:
        return "0"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)

def format_hitrate(cache, inp):
    denom = (cache or 0) + (inp or 0)
    if denom <= 0:
        return "0.0%"
    rate = (cache / denom) * 100.0
    return f"{rate:.1f}%"

def truncate_title(title, max_w):
    if display_len(title) > max_w:
        truncated = ""
        for ch in title:
            if display_len(truncated + ch + "…") > max_w:
                break
            truncated += ch
        return truncated + "…"
    return title

def render_daily_table(data):
    """渲染每日账本模式的终端表格"""
    term_width = shutil.get_terminal_size((118, 24)).columns
    w_rank = 5
    w_time = 13
    w_total = 8
    w_input = 8
    w_output = 8
    w_cache = 8
    w_hit = 7
    w_cost = 11
    
    fixed_width = w_rank + w_time + w_total + w_input + w_output + w_cache + w_hit + w_cost + 24
    w_title = max(24, term_width - fixed_width)
    total_table_width = min(term_width, fixed_width + w_title)

    display_name = data["displayName"]
    sort_by_tokens = data["sortByTokens"]
    sum_info = data["summary"]

    if sort_by_tokens:
        flat_records = data["flatRecords"]
        print("=" * total_table_width)
        print(f"  {display_name} 单日会话消耗排行 (共 {len(flat_records)} 条日度会话记录 - 按当日消耗排序)")
        print("  * 模式：[-d / --daily] 每日会话账本（不混淆前日用量，仅算当日实际消耗）")
        print("=" * total_table_width)
        header = (
            pad_str("序号", w_rank, "center") + " │ " +
            pad_str("最近访问", w_time, "center") + " │ " +
            pad_str("总Token", w_total, "right") + " │ " +
            pad_str("Input", w_input, "right") + " │ " +
            pad_str("Output", w_output, "right") + " │ " +
            pad_str("Cache", w_cache, "right") + " │ " +
            pad_str("Hitrate", w_hit, "right") + " │ " +
            pad_str("等效价格", w_cost, "right") + " │ " +
            pad_str("会话标题", w_title, "left")
        )
        print(header)
        print("─" * total_table_width)

        for r in flat_records:
            t_str = truncate_title(r["title"], w_title)
            print(
                pad_str(str(r["index"]), w_rank, "center") + " │ " +
                pad_str(r["time"], w_time, "center") + " │ " +
                pad_str(format_tokens(r["totalTokens"]), w_total, "right") + " │ " +
                pad_str(format_tokens(r["inputTokens"]), w_input, "right") + " │ " +
                pad_str(format_tokens(r["outputTokens"]), w_output, "right") + " │ " +
                pad_str(format_tokens(r["cacheTokens"]), w_cache, "right") + " │ " +
                pad_str(format_hitrate(r["cacheTokens"], r["inputTokens"]), w_hit, "right") + " │ " +
                pad_str(f"¥{r['costCnyRaw']:.2f}", w_cost, "right") + " │ " +
                pad_str(t_str, w_title, "left")
            )
        print("─" * total_table_width)
        print(
            pad_str("汇总", w_rank, "center") + " │ " +
            pad_str("--", w_time, "center") + " │ " +
            pad_str(format_tokens(sum_info["totalTokens"]), w_total, "right") + " │ " +
            pad_str(format_tokens(sum_info["inputTokens"]), w_input, "right") + " │ " +
            pad_str(format_tokens(sum_info["outputTokens"]), w_output, "right") + " │ " +
            pad_str(format_tokens(sum_info["cacheTokens"]), w_cache, "right") + " │ " +
            pad_str(format_hitrate(sum_info["cacheTokens"], sum_info["inputTokens"]), w_hit, "right") + " │ " +
            pad_str(f"¥{sum_info['costCny']:.2f}", w_cost, "right") + " │ " +
            pad_str(f"共 {len(flat_records)} 条日度会话记录 (~${sum_info['costUsd']:.2f} USD)", w_title, "left")
        )
        print("=" * total_table_width)
        return

    # 默认按时间正序
    print("=" * total_table_width)
    print(f"  {display_name} 每日会话账本 (共 {data['activeDaysCount']} 个活动日, {data['totalRecordsCount']} 笔日度会话)")
    print("  * 模式：[-d / --daily 默认] 不混淆前日用量，精准分列“此日、此 Session”的实际发生额")
    print("  * 计价：DeepSeek-V4.1-Flash 高峰期 (未命中 ¥2/M | 缓存命中 ¥0.04/M | 输出 ¥8/M)")
    print("=" * total_table_width)

    header = (
        pad_str("序号", w_rank, "center") + " │ " +
        pad_str("访问时间", w_time, "center") + " │ " +
        pad_str("总Token", w_total, "right") + " │ " +
        pad_str("Input", w_input, "right") + " │ " +
        pad_str("Output", w_output, "right") + " │ " +
        pad_str("Cache", w_cache, "right") + " │ " +
        pad_str("Hitrate", w_hit, "right") + " │ " +
        pad_str("等效价格", w_cost, "right") + " │ " +
        pad_str("会话标题", w_title, "left")
    )
    print(header)
    print("─" * total_table_width)

    for week in data["weeks"]:
        for day in week["days"]:
            for r in day["records"]:
                t_str = truncate_title(r["title"], w_title)
                row = (
                    pad_str(str(r["index"]), w_rank, "center") + " │ " +
                    pad_str(r["time"], w_time, "center") + " │ " +
                    pad_str(format_tokens(r["totalTokens"]), w_total, "right") + " │ " +
                    pad_str(format_tokens(r["inputTokens"]), w_input, "right") + " │ " +
                    pad_str(format_tokens(r["outputTokens"]), w_output, "right") + " │ " +
                    pad_str(format_tokens(r["cacheTokens"]), w_cache, "right") + " │ " +
                    pad_str(format_hitrate(r["cacheTokens"], r["inputTokens"]), w_hit, "right") + " │ " +
                    pad_str(f"¥{r['costCnyRaw']:.2f}", w_cost, "right") + " │ " +
                    pad_str(t_str, w_title, "left")
                )
                print(row)

            # 日小计
            day_short = day["date"][5:] if len(day["date"]) >= 10 else day["date"]
            day_time_label = f"{day_short}({day['weekday']}) 小计"
            day_subtotal_row = (
                pad_str("日计", w_rank, "center") + " │ " +
                pad_str(day_time_label, w_time, "center") + " │ " +
                pad_str(format_tokens(day["totalTokens"]), w_total, "right") + " │ " +
                pad_str(format_tokens(day["inputTokens"]), w_input, "right") + " │ " +
                pad_str(format_tokens(day["outputTokens"]), w_output, "right") + " │ " +
                pad_str(format_tokens(day["cacheTokens"]), w_cache, "right") + " │ " +
                pad_str(format_hitrate(day["cacheTokens"], day["inputTokens"]), w_hit, "right") + " │ " +
                pad_str(f"¥{day['costCny']:.2f}", w_cost, "right") + " │ " +
                pad_str(f"当日净消耗 ({day['count']} 笔会话)", w_title, "left")
            )
            print(day_subtotal_row)
            print("·" * total_table_width)

        # 周小计
        week_subtotal_row = (
            pad_str("周计", w_rank, "center") + " │ " +
            pad_str(f"{week['weekKey']} 小计", w_time, "center") + " │ " +
            pad_str(format_tokens(week["totalTokens"]), w_total, "right") + " │ " +
            pad_str(format_tokens(week["inputTokens"]), w_input, "right") + " │ " +
            pad_str(format_tokens(week["outputTokens"]), w_output, "right") + " │ " +
            pad_str(format_tokens(week["cacheTokens"]), w_cache, "right") + " │ " +
            pad_str(format_hitrate(week["cacheTokens"], week["inputTokens"]), w_hit, "right") + " │ " +
            pad_str(f"¥{week['costCny']:.2f}", w_cost, "right") + " │ " +
            pad_str(f"本周净消耗 ({week['count']} 笔会话)", w_title, "left")
        )
        print(week_subtotal_row)
        print("─" * total_table_width)

    # 全周期合计
    grand_total_row = (
        pad_str("汇总", w_rank, "center") + " │ " +
        pad_str("全周期合计", w_time, "center") + " │ " +
        pad_str(format_tokens(sum_info["totalTokens"]), w_total, "right") + " │ " +
        pad_str(format_tokens(sum_info["inputTokens"]), w_input, "right") + " │ " +
        pad_str(format_tokens(sum_info["outputTokens"]), w_output, "right") + " │ " +
        pad_str(format_tokens(sum_info["cacheTokens"]), w_cache, "right") + " │ " +
        pad_str(format_hitrate(sum_info["cacheTokens"], sum_info["inputTokens"]), w_hit, "right") + " │ " +
        pad_str(f"¥{sum_info['costCny']:.2f}", w_cost, "right") + " │ " +
        pad_str(f"全周期净消耗 (~${sum_info['costUsd']:.2f} USD)", w_title, "left")
    )
    print(grand_total_row)
    print("=" * total_table_width)

def render_session_table(data):
    """渲染项目总览模式的终端表格"""
    term_width = shutil.get_terminal_size((118, 24)).columns
    w_rank = 5
    w_time = 13
    w_total = 8
    w_input = 8
    w_output = 8
    w_cache = 8
    w_hit = 7
    w_cost = 11
    
    fixed_width = w_rank + w_time + w_total + w_input + w_output + w_cache + w_hit + w_cost + 24
    w_title = max(24, term_width - fixed_width)
    total_table_width = min(term_width, fixed_width + w_title)

    display_name = data["displayName"]
    sort_by_tokens = data["sortByTokens"]
    sum_info = data["summary"]
    sessions = data["flatRecords"]

    if sort_by_tokens:
        print("=" * total_table_width)
        print(f"  {display_name} 项目/会话总用量排行 (共 {len(sessions)} 个 Session - 按全生命周期 Token 消耗降序)")
        print("  * 模式：[-s / --session] 专注每个任务/Project 的全生命周期总耗费")
        print("=" * total_table_width)
        header = (
            pad_str("序号", w_rank, "center") + " │ " +
            pad_str("最近访问", w_time, "center") + " │ " +
            pad_str("总Token", w_total, "right") + " │ " +
            pad_str("Input", w_input, "right") + " │ " +
            pad_str("Output", w_output, "right") + " │ " +
            pad_str("Cache", w_cache, "right") + " │ " +
            pad_str("Hitrate", w_hit, "right") + " │ " +
            pad_str("等效价格", w_cost, "right") + " │ " +
            pad_str("会话标题", w_title, "left")
        )
        print(header)
        print("─" * total_table_width)

        for s in sessions:
            t_str = truncate_title(s["title"], w_title)
            print(
                pad_str(str(s["index"]), w_rank, "center") + " │ " +
                pad_str(s["time"], w_time, "center") + " │ " +
                pad_str(format_tokens(s["totalTokens"]), w_total, "right") + " │ " +
                pad_str(format_tokens(s["inputTokens"]), w_input, "right") + " │ " +
                pad_str(format_tokens(s["outputTokens"]), w_output, "right") + " │ " +
                pad_str(format_tokens(s["cacheTokens"]), w_cache, "right") + " │ " +
                pad_str(format_hitrate(s["cacheTokens"], s["inputTokens"]), w_hit, "right") + " │ " +
                pad_str(f"¥{s['costCnyRaw']:.2f}", w_cost, "right") + " │ " +
                pad_str(t_str, w_title, "left")
            )
        print("─" * total_table_width)
        print(
            pad_str("汇总", w_rank, "center") + " │ " +
            pad_str("--", w_time, "center") + " │ " +
            pad_str(format_tokens(sum_info["totalTokens"]), w_total, "right") + " │ " +
            pad_str(format_tokens(sum_info["inputTokens"]), w_input, "right") + " │ " +
            pad_str(format_tokens(sum_info["outputTokens"]), w_output, "right") + " │ " +
            pad_str(format_tokens(sum_info["cacheTokens"]), w_cache, "right") + " │ " +
            pad_str(format_hitrate(sum_info["cacheTokens"], sum_info["inputTokens"]), w_hit, "right") + " │ " +
            pad_str(f"¥{sum_info['costCny']:.2f}", w_cost, "right") + " │ " +
            pad_str(f"共 {len(sessions)} 个项目会话 (~${sum_info['costUsd']:.2f} USD)", w_title, "left")
        )
        print("=" * total_table_width)
        return

    # 默认时间正序
    print("=" * total_table_width)
    print(f"  {display_name} 项目/会话总览 (共 {len(sessions)} 个 Session - 全生命周期累计消耗)")
    print("  * 模式：[-s / --session] 专注每个任务/Project 的全生命周期总耗费（按最新访问时间排序）")
    print("  * 计价：DeepSeek-V4.1-Flash 高峰期 (未命中 ¥2/M | 缓存命中 ¥0.04/M | 输出 ¥8/M)")
    print("=" * total_table_width)

    header = (
        pad_str("序号", w_rank, "center") + " │ " +
        pad_str("最近访问", w_time, "center") + " │ " +
        pad_str("总Token", w_total, "right") + " │ " +
        pad_str("Input", w_input, "right") + " │ " +
        pad_str("Output", w_output, "right") + " │ " +
        pad_str("Cache", w_cache, "right") + " │ " +
        pad_str("Hitrate", w_hit, "right") + " │ " +
        pad_str("等效价格", w_cost, "right") + " │ " +
        pad_str("会话标题", w_title, "left")
    )
    print(header)
    print("─" * total_table_width)

    global_idx = 1
    for week in data["weeks"]:
        for day in week["days"]:
            for s in day["records"]:
                t_str = truncate_title(s["title"], w_title)
                row = (
                    pad_str(str(global_idx), w_rank, "center") + " │ " +
                    pad_str(s["time"], w_time, "center") + " │ " +
                    pad_str(format_tokens(s["totalTokens"]), w_total, "right") + " │ " +
                    pad_str(format_tokens(s["inputTokens"]), w_input, "right") + " │ " +
                    pad_str(format_tokens(s["outputTokens"]), w_output, "right") + " │ " +
                    pad_str(format_tokens(s["cacheTokens"]), w_cache, "right") + " │ " +
                    pad_str(format_hitrate(s["cacheTokens"], s["inputTokens"]), w_hit, "right") + " │ " +
                    pad_str(f"¥{s['costCnyRaw']:.2f}", w_cost, "right") + " │ " +
                    pad_str(t_str, w_title, "left")
                )
                print(row)
                global_idx += 1

            day_short = day["date"][5:] if len(day["date"]) >= 10 else day["date"]
            day_time_label = f"{day_short}({day['weekday']}) 小计"
            day_subtotal_row = (
                pad_str("日计", w_rank, "center") + " │ " +
                pad_str(day_time_label, w_time, "center") + " │ " +
                pad_str(format_tokens(day["totalTokens"]), w_total, "right") + " │ " +
                pad_str(format_tokens(day["inputTokens"]), w_input, "right") + " │ " +
                pad_str(format_tokens(day["outputTokens"]), w_output, "right") + " │ " +
                pad_str(format_tokens(day["cacheTokens"]), w_cache, "right") + " │ " +
                pad_str(format_hitrate(day["cacheTokens"], day["inputTokens"]), w_hit, "right") + " │ " +
                pad_str(f"¥{day['costCny']:.2f}", w_cost, "right") + " │ " +
                pad_str(f"当日活跃项目 ({day['count']} 个会话)", w_title, "left")
            )
            print(day_subtotal_row)
            print("·" * total_table_width)

        week_subtotal_row = (
            pad_str("周计", w_rank, "center") + " │ " +
            pad_str(f"{week['weekKey']} 小计", w_time, "center") + " │ " +
            pad_str(format_tokens(week["totalTokens"]), w_total, "right") + " │ " +
            pad_str(format_tokens(week["inputTokens"]), w_input, "right") + " │ " +
            pad_str(format_tokens(week["outputTokens"]), w_output, "right") + " │ " +
            pad_str(format_tokens(week["cacheTokens"]), w_cache, "right") + " │ " +
            pad_str(format_hitrate(week["cacheTokens"], week["inputTokens"]), w_hit, "right") + " │ " +
            pad_str(f"¥{week['costCny']:.2f}", w_cost, "right") + " │ " +
            pad_str(f"本周活跃项目 ({week['count']} 个会话)", w_title, "left")
        )
        print(week_subtotal_row)
        print("─" * total_table_width)

    grand_total_row = (
        pad_str("汇总", w_rank, "center") + " │ " +
        pad_str("全周期合计", w_time, "center") + " │ " +
        pad_str(format_tokens(sum_info["totalTokens"]), w_total, "right") + " │ " +
        pad_str(format_tokens(sum_info["inputTokens"]), w_input, "right") + " │ " +
        pad_str(format_tokens(sum_info["outputTokens"]), w_output, "right") + " │ " +
        pad_str(format_tokens(sum_info["cacheTokens"]), w_cache, "right") + " │ " +
        pad_str(format_hitrate(sum_info["cacheTokens"], sum_info["inputTokens"]), w_hit, "right") + " │ " +
        pad_str(f"¥{sum_info['costCny']:.2f}", w_cost, "right") + " │ " +
        pad_str(f"共 {len(sessions)} 个项目会话 (~${sum_info['costUsd']:.2f} USD)", w_title, "left")
    )
    print(grand_total_row)
    print("=" * total_table_width)

def print_usage_hint():
    print("=" * 78)
    print("  myccusage: 多 Agent 会话用量与 DeepSeek-V4.1-Flash 等效计费工具")
    print("=" * 78)
    print("用法:")
    print("  myccusage <agent参数> [模式选项] [排序选项]")
    print("  myccusage --web [--port <端口>]         # 启动网页前端仪表盘\n")
    print("支持的 Agent 参数:")
    print("  --agy, --antigravity    统计 Google Antigravity (App + CLI)")
    print("  --claude                统计 Claude Code")
    print("  --hermes                统计 Hermes Agent")
    print("  --codex                 统计 OpenAI Codex")
    print("  --grok                  统计 Grok")
    print("  --pi                    统计 Pi Agent")
    print("  --opencode              统计 OpenCode")
    print("  --workbuddy             统计 WorkBuddy (腾讯旗下 AI 编程 Agent)\n")
    print("模式选项 (双模分流):")
    print("  -d, --daily             [默认] 每日会话账本模式")
    print("                          不混淆前日用量，按“此日、此 Session”精确分列，日/周小计绝不漂移")
    print("  -s, --session           项目总览模式")
    print("                          专注每个 Project / Session 的全生命周期累计总消耗（体现整体任务成本）\n")
    print("网页与交互选项:")
    print("  -w, --web               启动本地网页仪表盘 Dashboard (默认端口 8488)")
    print("  -p, --port <端口>       指定 Web 仪表盘端口号 (默认 8488)\n")
    print("排序与通用选项:")
    print("  -t, --tokens            按【Token 消耗量】降序排列（默认按时间正序排列，最新在最底部）")
    print("  -h, --help              查看本帮助信息\n")
    print("示例:")
    print("  myccusage --agy               # Antigravity 每日会话账本 (最新在最底部，小计防漂移)")
    print("  myccusage --claude            # Claude Code 每日会话账本")
    print("  myccusage --agy -s            # Antigravity 项目全生命周期总览")
    print("  myccusage --agy -s -t         # Antigravity 项目总用量大户排行")
    print("  myccusage --opencode          # OpenCode 每日会话账本")
    print("  myccusage --workbuddy         # WorkBuddy 每日会话账本")
    print("  myccusage --web               # 一键启动 Web 前端仪表盘并自动打开浏览器")
    print("=" * 78)

def main(raw_args=None):
    if raw_args is None:
        raw_args = sys.argv[1:]

    if "-h" in raw_args or "--help" in raw_args:
        print_usage_hint()
        return

    agent_type = None
    mode = "daily"  # 默认 -d 每日会话账本模式
    sort_by_tokens = False
    is_web_mode = False
    web_port = 8488
    clean_args = []

    i = 0
    while i < len(raw_args):
        a = raw_args[i]
        if a in ("--web", "-w", "web"):
            is_web_mode = True
        elif a in ("--port", "-p") and i + 1 < len(raw_args):
            i += 1
            try:
                web_port = int(raw_args[i])
            except ValueError:
                pass
        elif a in ("--agy", "--antigravity"):
            agent_type = "agy"
        elif a == "--claude":
            agent_type = "claude"
        elif a == "--hermes":
            agent_type = "hermes"
        elif a == "--codex":
            agent_type = "codex"
        elif a == "--grok":
            agent_type = "grok"
        elif a == "--pi":
            agent_type = "pi"
        elif a == "--opencode":
            agent_type = "opencode"
        elif a == "--workbuddy":
            agent_type = "workbuddy"
        elif a in ("-s", "--session"):
            mode = "session"
        elif a in ("-d", "--daily"):
            mode = "daily"
        elif a in ("--tokens", "-t"):
            sort_by_tokens = True
        else:
            clean_args.append(a)
        i += 1

    if is_web_mode:
        from .web.server import start_server
        start_server(port=web_port, default_agent=agent_type or "agy")
        return

    if not agent_type:
        print_usage_hint()
        return

    try:
        if mode == "session":
            data = get_session_data(agent_type, sort_by_tokens=sort_by_tokens, clean_args=clean_args)
            render_session_table(data)
        else:
            data = get_daily_data(agent_type, sort_by_tokens=sort_by_tokens)
            render_daily_table(data)
    except Exception as e:
        msg = str(e)
        if "未检测到底层依赖" in msg:
            print(f"\n{msg}\n", file=sys.stderr)
        else:
            print(f"错误: {msg}", file=sys.stderr)
        sys.exit(1)
