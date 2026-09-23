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
import subprocess
import unicodedata

# Windows 原生终端输出 UTF-8 编码兼容防护 (对 macOS / Linux 零开销)
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        else:
            import io
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

from .core import (
    SUPPORTED_AGENTS,
    get_daily_data,
    get_session_data,
    get_today_quick_summary,
)

def display_len(s):
    """
    计算字符串在终端中的实际显示宽度。
    基于 East Asian Width（东亚宽度）属性，全角字符（如中文、日文、宽标点等）
    在终端中通常占据 2 个字符宽度，而半角字符占据 1 个字符宽度。
    """
    length = 0
    for ch in s:
        # 获取字符的东亚宽度属性
        w = unicodedata.east_asian_width(ch)
        # "F" 代表 Fullwidth（全角），"W" 代表 Wide（宽字符）
        # 满足这两种情况的字符在终端占2列宽，否则占1列宽
        length += 2 if w in ("F", "W") else 1
    return length

def pad_str(s, width, align="left"):
    """
    按指定宽度和对齐方式填充字符串，确保中英文混合情况下的严格对齐。
    """
    # 获取字符串的实际显示宽度
    dlen = display_len(s)
    # 计算需要填充的空格数，若字符串宽度已超过指定宽度则不填充
    pad = max(0, width - dlen)
    
    if align == "right":
        # 右对齐：在左侧填充空格
        return " " * pad + s
    elif align == "center":
        # 居中对齐：将空格均分到左右两侧
        left = pad // 2
        right = pad - left
        return " " * left + s + " " * right
    else:
        # 左对齐（默认）：在右侧填充空格
        return s + " " * pad

def format_tokens(n):
    """
    将 Token 数量格式化为易读的缩写形式（如 K、M）。
    """
    if n is None or n == 0:
        return "0"
    
    # 大于等于一百万的数字使用 "M"（兆）后缀
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    # 大于等于一千的数字使用 "K"（千）后缀
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    
    return str(n)

def format_hitrate(cache, inp):
    """
    计算并格式化缓存命中率，以百分比形式展示。
    公式：缓存 Token 数 / (缓存 Token 数 + 输入 Token 数)
    """
    # 计算总输入量（缓存项加新输入项），防范 None 值情况
    denom = (cache or 0) + (inp or 0)
    
    if denom <= 0:
        return "0.0%"
        
    # 计算百分比并保留一位小数
    rate = (cache / denom) * 100.0
    return f"{rate:.1f}%"

def truncate_title(title, max_w):
    """
    智能截断标题以适应终端列宽。
    考虑中英文混合长度，并在截断末尾添加省略号 "…" 提示。
    """
    # 仅当标题实际显示宽度大于最大宽度限制时才进行截断
    if display_len(title) > max_w:
        truncated = ""
        for ch in title:
            # 预判：若加入当前字符及省略号后的总宽超限，则停止添加
            if display_len(truncated + ch + "…") > max_w:
                break
            truncated += ch
        return truncated + "…"
    
    return title

def render_daily_table(data):
    """渲染每日账本模式的终端表格"""
    # 动态获取终端宽度，预设后备大小为 (118列, 24行)
    term_width = shutil.get_terminal_size((118, 24)).columns
    
    # 预设各个数据列的固定宽度
    w_rank = 5
    w_time = 13
    w_total = 8
    w_input = 8
    w_output = 8
    w_cache = 8
    w_hit = 7
    w_cost = 11
    
    # 计算非标题列的总宽度（包含列之间的分隔符宽度等预估常数 24）
    fixed_width = w_rank + w_time + w_total + w_input + w_output + w_cache + w_hit + w_cost + 24
    
    # 将剩余空间全部分配给会话标题列，并保证最小宽度为 24
    w_title = max(24, term_width - fixed_width)
    
    # 确定整个表格的最终总宽度，避免超出终端边界
    total_table_width = min(term_width, fixed_width + w_title)

    display_name = data["displayName"]
    sort_by_tokens = data["sortByTokens"]
    sum_info = data["summary"]

    # 分支一：按 Token 消耗量排序的展示逻辑（不分层级，平铺展示）
    if sort_by_tokens:
        flat_records = data["flatRecords"]
        print("=" * total_table_width)
        print(f"  {display_name} 单日会话消耗排行 (共 {len(flat_records)} 条日度会话记录 - 按当日消耗排序)")
        print("  * 模式：[-d / --daily] 每日会话账本（不混淆前日用量，仅算当日实际消耗）")
        print("=" * total_table_width)
        
        # 拼接表头，严格使用之前分配的各列宽度进行居中或对齐
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

        # 遍历扁平化的记录进行单行渲染
        for r in flat_records:
            # 根据动态分配的标题列宽进行智能截断
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
        
        # 打印全周期合计行
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

    # 分支二：默认按时间正序排列的三级层次渲染（记录 → 日小计 → 周小计 → 全周期合计）
    print("=" * total_table_width)
    print(f"  {display_name} 每日会话账本 (共 {data['activeDaysCount']} 个活动日, {data['totalRecordsCount']} 笔日度会话)")
    print("  * 模式：[-d / --daily 默认] 不混淆前日用量，精准分列“此日、此 Session”的实际发生额")
    print("  * 计价：DeepSeek-V4.1-Flash 高峰期 (未命中 ¥2/M | 缓存命中 ¥0.04/M | 输出 ¥8/M)")
    print("=" * total_table_width)

    # 渲染主表头
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

    # 层级遍历：周 -> 日 -> 记录
    for week in data["weeks"]:
        for day in week["days"]:
            # 渲染第一级：最细粒度的单笔会话记录
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

            # 渲染第二级：日小计（统计当日内所有会话的消耗汇总）
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
            # 使用弱分隔符表示日结束
            print("·" * total_table_width)

        # 渲染第三级：周小计（统计当周内所有活动日的消耗汇总）
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
        # 使用强分隔符表示周结束
        print("─" * total_table_width)

    # 渲染第四级：全周期合计（对所有历史数据的全局统计汇总）
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
    # 动态获取终端宽度，实现响应式排版
    term_width = shutil.get_terminal_size((118, 24)).columns
    
    # 预设固定的字段宽度
    w_rank = 5
    w_time = 13
    w_total = 8
    w_input = 8
    w_output = 8
    w_cache = 8
    w_hit = 7
    w_cost = 11
    
    # 计算并分配标题列所需的剩余宽度
    fixed_width = w_rank + w_time + w_total + w_input + w_output + w_cache + w_hit + w_cost + 24
    w_title = max(24, term_width - fixed_width)
    total_table_width = min(term_width, fixed_width + w_title)

    display_name = data["displayName"]
    sort_by_tokens = data["sortByTokens"]
    sum_info = data["summary"]
    sessions = data["flatRecords"]

    # 排行榜分支：按 Token 全局排序平铺展示
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

        # 遍历汇总后的会话进行展示
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
        
        # 打印全周期合计行
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

    # 时序浏览分支：默认按最近访问时间正序，分级统计渲染
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

    # 全局累加的序号，用作总览展示时的唯一编号
    global_idx = 1
    
    # 嵌套遍历：周 -> 日 -> Session记录
    for week in data["weeks"]:
        for day in week["days"]:
            # 第一级：呈现单个项目的累计统计概况
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

            # 第二级：日小计
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

        # 第三级：周小计
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

    # 第四级：全周期合计
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

def render_quick_summary(summary):
    """
    零参数运行或速览模式下渲染今日多 Agent 消耗速报卡片。
    """
    total_table_width = min(88, shutil.get_terminal_size((88, 20)).columns)
    total_table_width = max(total_table_width, 70)

    print("=" * total_table_width)
    print(f"  myccusage 今日用量速报 ({summary['date']})")
    print(f"  * 计价基准：DeepSeek-V4.1-Flash 高峰期 (未命中 ¥2/M | 缓存命中 ¥0.04/M | 输出 ¥8/M)")
    print("=" * total_table_width)

    tot_str = format_tokens(summary.get("totalTokens", 0)).strip()
    hit_str = f"{summary.get('cacheHitRate', 0.0):.1f}%"
    cost_str = f"¥{summary.get('costCny', 0.0):.2f}"
    usd_str = f"~${summary.get('costUsd', 0.0):.2f} USD"

    print(f"  今日总消耗: {tot_str} Tokens │ 缓存命中率: {hit_str} │ 参考花费: {cost_str} ({usd_str})")
    print("─" * total_table_width)

    agents = summary.get("agents", [])
    if not agents:
        print("  今日暂无活动会话记录。")
    else:
        w_name = 24
        w_tok = 12
        w_hit = 10
        w_cost = 12
        w_sess = 10
        hdr = (
            pad_str("Agent 名称", w_name, "left") + " │ " +
            pad_str("今日Token", w_tok, "right") + " │ " +
            pad_str("缓存率", w_hit, "right") + " │ " +
            pad_str("等效费用", w_cost, "right") + " │ " +
            pad_str("会话数", w_sess, "right")
        )
        print(hdr)
        print("─" * total_table_width)
        for a in agents:
            row = (
                pad_str(a["name"], w_name, "left") + " │ " +
                pad_str(format_tokens(a["totalTokens"]), w_tok, "right") + " │ " +
                pad_str(f"{a['hitRate']:.1f}%", w_hit, "right") + " │ " +
                pad_str(f"¥{a['costCny']:.2f}", w_cost, "right") + " │ " +
                pad_str(f"{a['sessionCount']} 笔", w_sess, "right")
            )
            print(row)

    print("=" * total_table_width)
    print("  💡 常用极简命令 (支持 ccu 或 myccusage):")
    print("     ccu agy         # 查看 Antigravity 每日明细账本")
    print("     ccu agy -s      # 查看 Antigravity 项目累计总览")
    print("     ccu claude      # 查看 Claude Code 每日账本")
    print("     ccu codex       # 查看 OpenAI Codex 每日账本")
    print("     ccu web         # 打开本地 Web 仪表盘")
    print("     ccu --help      # 查看完整参数帮助")
    print("=" * total_table_width)

def print_usage_hint():
    """打印 CLI 使用帮助信息"""
    print("=" * 78)
    print("  myccusage: 多 Agent 会话用量与 DeepSeek-V4.1-Flash 等效计费工具")
    print("=" * 78)
    print("用法:")
    print("  ccu [agent名称] [模式选项] [排序选项]     # 极简命令")
    print("  myccusage <agent参数> [模式选项] [排序选项]")
    print("  ccu web [--port <端口>]                  # 启动网页前端仪表盘\n")
    print("支持的 Agent (直接输入名称即可，无需 --):")
    print("  agy, antigravity        Google Antigravity (App + CLI + IDE)")
    print("  claude                  Claude Code")
    print("  codex                   OpenAI Codex")
    print("  workbuddy               WorkBuddy (腾讯旗下 AI 编程 Agent)")
    print("  grok                    Grok")
    print("  hermes                  Hermes Agent")
    print("  opencode                OpenCode")
    print("  pi                      Pi Agent\n")
    print("模式选项 (双模分流):")
    print("  -d, --daily             [默认] 每日会话账本模式")
    print("                          不混淆前日用量，按“此日、此 Session”精确分列，日/周小计绝不漂移")
    print("  -s, --session           项目总览模式")
    print("                          专注每个 Project / Session 的全生命周期累计总消耗（体现整体任务成本）\n")
    print("常用极简示例:")
    print("  ccu                           # 今日多 Agent 消耗速报")
    print("  ccu agy                       # Antigravity 每日会话账本")
    print("  ccu agy -s                    # Antigravity 项目全生命周期总览")
    print("  ccu claude                    # Claude Code 每日会话账本")
    print("  ccu codex -s                  # Codex 项目全生命周期总览")
    print("  ccu web                       # 一键启动 Web 仪表盘")
    print("=" * 78)

def launch_macos_dock_app():
    """在 macOS 下启动或构建并启动原生程序坞常驻应用"""
    if sys.platform != "darwin":
        print("❌ 错误: macOS 程序坞常驻应用仅支持在 macOS 系统上运行。")
        return

    # 1. 寻找可能已构建的 app
    candidates = [
        os.path.expanduser("~/Applications/myccusage.app"),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "dist/myccusage.app"),
        os.path.expanduser("~/.local/share/myccusage/myccusage.app"),
    ]
    app_path = None
    for c in candidates:
        if os.path.exists(c):
            app_path = c
            break

    # 2. 如果未找到已构建的 app，自动执行构建脚本
    if not app_path:
        script_candidates = [
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "macos/build_app.sh"),
            os.path.join(os.path.dirname(__file__), "macos/build_app.sh"),
        ]
        build_script = None
        for s in script_candidates:
            if os.path.exists(s):
                build_script = s
                break

        if build_script:
            print("⚡️ 检测到首次运行，正在自动构建原生 macOS 程序坞应用 (约需 2~3 秒)...")
            res = subprocess.run(["bash", build_script])
            if res.returncode == 0:
                for c in candidates:
                    if os.path.exists(c):
                        app_path = c
                        break
        else:
            print("❌ 未找到编译构建脚本 macos/build_app.sh")
            return

    if app_path and os.path.exists(app_path):
        print(f"🚀 正在启动 macOS 程序坞常驻微型应用: {app_path}")
        subprocess.run(["open", app_path])
    else:
        print("❌ 启动失败，未找到可运行的 myccusage.app")

def main(raw_args=None):
    """
    命令行参数解析与调度入口。
    根据参数决定执行 CLI 表格渲染还是启动 Web 仪表盘服务。
    """
    if raw_args is None:
        raw_args = sys.argv[1:]

    # 如果存在版本查询标记，输出版本并退出
    if "-v" in raw_args or "--version" in raw_args:
        from . import __version__
        print(f"myccusage v{__version__} (100% Native, Zero-ccusage)")
        return

    # 如果存在帮助标记，直接输出用法信息并退出
    if "-h" in raw_args or "--help" in raw_args:
        print_usage_hint()
        return

    # 初始化配置变量
    agent_type = None
    mode = "daily"  # 默认 -d 每日会话账本模式
    sort_by_tokens = False
    is_web_mode = False
    is_dock_mode = False
    web_port = 8488
    is_daemon = False
    auto_open = True
    clean_args = []

    # 手动解析命令行参数（避免依赖外部库的复杂逻辑，支持灵活标志位置）
    i = 0
    while i < len(raw_args):
        a = raw_args[i]
        # 解析 Dock 模式标记
        if a in ("--dock", "dock"):
            is_dock_mode = True
        # 解析 Web 模式标记
        elif a in ("--web", "-w", "web", "ui"):
            is_web_mode = True
        # 解析常驻守护标记
        elif a == "--daemon":
            is_daemon = True
            is_web_mode = True
        # 解析禁止自动打开浏览器标记
        elif a in ("--no-open", "-n"):
            auto_open = False
        # 解析自定义端口标记
        elif a in ("--port", "-p") and i + 1 < len(raw_args):
            i += 1
            try:
                web_port = int(raw_args[i])
            except ValueError:
                pass
        # 解析 Agent 类型匹配标记 (支持带 -- 或不带 -- 的自然命令)
        elif a in ("--agy", "--antigravity", "agy", "antigravity"):
            agent_type = "agy"
        elif a in ("--claude", "claude"):
            agent_type = "claude"
        elif a in ("--hermes", "hermes"):
            agent_type = "hermes"
        elif a in ("--codex", "codex"):
            agent_type = "codex"
        elif a in ("--grok", "grok"):
            agent_type = "grok"
        elif a in ("--pi", "pi"):
            agent_type = "pi"
        elif a in ("--opencode", "opencode"):
            agent_type = "opencode"
        elif a in ("--workbuddy", "workbuddy"):
            agent_type = "workbuddy"
        # 解析统计视图模式标记（Session总览或每日账本）
        elif a in ("-s", "--session", "session"):
            mode = "session"
        elif a in ("-d", "--daily", "daily"):
            mode = "daily"
        # 解析排序偏好标记（是否按 Token 排列）
        elif a in ("--tokens", "-t", "tokens"):
            sort_by_tokens = True
        else:
            # 收集未被识别的参数，可能传递给底层方法作透传用途
            clean_args.append(a)
        i += 1

    # 如果激活了 Dock 模式，调度到 macOS 原生程序坞构建与拉起逻辑
    if is_dock_mode:
        launch_macos_dock_app()
        return

    # 如果激活了 Web 模式，将调度到服务端代码
    if is_web_mode:
        from .web.server import start_server
        start_server(port=web_port, default_agent=agent_type or "agy", auto_open=auto_open, daemon_mode=is_daemon)
        return

    # CLI 模式下若未指定具体 Agent，直接输出今日多 Agent 消耗速报
    if not agent_type:
        try:
            summary = get_today_quick_summary()
            render_quick_summary(summary)
        except Exception:
            print_usage_hint()
        return

    try:
        # 基于模式选择对应的数据拉取和表格渲染逻辑
        if mode == "session":
            data = get_session_data(agent_type, sort_by_tokens=sort_by_tokens, clean_args=clean_args)
            render_session_table(data)
        else:
            data = get_daily_data(agent_type, sort_by_tokens=sort_by_tokens)
            render_daily_table(data)
    except Exception as e:
        msg = str(e)
        # 对依赖缺失做出友好提醒
        if "未检测到底层依赖" in msg:
            print(f"\n{msg}\n", file=sys.stderr)
        else:
            print(f"错误: {msg}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

