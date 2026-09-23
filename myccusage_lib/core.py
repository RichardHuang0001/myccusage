"""
myccusage_lib.core:
核心数据与计算内核：
- 8 大 Agent 原生会话标题与时间元数据解析 (由各适配器实现，本模块负责调度)
- DeepSeek-V4.1-Flash 高峰期等效计价模型
- 纯结构化日账本 (Daily) 与项目总览 (Session) 聚合计算
- 多端异机会话在内存层的并集融合
"""

import os
import time
import threading
import concurrent.futures
from datetime import datetime
from collections import OrderedDict
from .adapters import ADAPTERS
from .sync import get_remote_agent_data, get_remote_fingerprint, get_remote_agent_ids

# 星期常量映射
WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"]

# 人民币兑美元参考汇率：仅用于把 CNY 等效费用换算为 USD 展示值
USD_CNY_RATE = 7.2

# 存储每个 Agent 对应的线程锁
_AGENT_LOCKS = {}
# 保护 _AGENT_LOCKS 字典的全局互斥锁
_AGENT_LOCKS_MUTEX = threading.Lock()

def get_agent_lock(agent_type):
    """获取指定 Agent 专用的互斥锁，避免同一 Agent 多个进程并发竞争本地 SQLite 数据库"""
    with _AGENT_LOCKS_MUTEX:
        # 如果当前 Agent 类型没有对应的锁，则初始化一个
        if agent_type not in _AGENT_LOCKS:
            _AGENT_LOCKS[agent_type] = threading.Lock()
        return _AGENT_LOCKS[agent_type]

# 支持的 Agent 配置字典，记录子命令及其是否原生带有时间戳信息
# 支持的 Agent 配置字典：仅保留展示名。
# 历史字段 subcmd / has_times 属于已移除的外部 ccusage CLI 回退路径的残留元数据，
# 全代码库 0 处读取，故在此一并清理。
SUPPORTED_AGENTS = {
    "agy": {"name": "Google Antigravity"},
    "claude": {"name": "Claude Code"},
    "hermes": {"name": "Hermes Agent"},
    "codex": {"name": "OpenAI Codex"},
    "grok": {"name": "Grok"},
    "pi": {"name": "Pi Agent"},
    "opencode": {"name": "OpenCode"},
    "workbuddy": {"name": "WorkBuddy"},
}

def calc_deepseek_cost(input_tokens, cache_read_tokens, total_output_tokens):
    """
    DeepSeek-V4.1-Flash 官方高峰期定价算法（自 2026 年 9 月 10 日生效）：
    - 输入（未命中/Cache Miss）：¥2.00 / 1M Tokens
    - 输入（命中缓存/Cache Hit）：¥0.04 / 1M Tokens
    - 输出（含思维链/Output+Reasoning）：¥8.00 / 1M Tokens
    
    参数:
        input_tokens: 未命中缓存的输入 Token 数
        cache_read_tokens: 命中缓存的输入 Token 数
        total_output_tokens: 所有的输出 Token 数
    返回:
        按 CNY 计价的等效费用
    """
    # 按照每百万 token 的价格进行折算
    cny = (input_tokens * 2.0 + cache_read_tokens * 0.04 + total_output_tokens * 8.0) / 1_000_000
    return cny

def format_time(iso_str):
    """
    格式化 ISO 时间字符串为简短的显示格式 (MM-DD HH:MM)
    
    参数:
        iso_str: ISO 8601 格式的时间字符串
    返回:
        简短时间字符串，若解析失败则返回原始日期的前 10 位
    """
    if not iso_str:
        return "--"
    try:
        # 兼容以 Z 结尾的 UTC 时间，将其转换为本地时区时间
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00")).astimezone()
        return dt.strftime("%m-%d %H:%M")
    except Exception:
        # 解析异常时直接截取前 10 个字符兜底
        return iso_str[:10]

# ==================== 标题与元数据提取模块 ====================









# 用于保护文件流式解析内存状态的锁
_WB_SCAN_LOCK = threading.Lock()
# 文件修改时间及结果的缓存，避免重复全量读取
_WB_FILES_CACHE = {}  # fpath -> (mtime, size, list_of_records)



def resolve_title(sid, titles):
    """
    通过会话 ID 查找并返回其人类可读标题。
    处理部分日志包含前缀或完整路径导致直接匹配不上的情况。
    """
    if not sid:
        return "（未命名/系统会话）"
    if sid in titles:
        return titles[sid]
    # 尝试提取 UUID 进行匹配
    parts = sid.split("-")
    if len(parts) >= 5:
        uuid = "-".join(parts[-5:])
        if uuid in titles:
            return titles[uuid]
    # 尝试使用 base filename 匹配
    base = os.path.basename(sid)
    if base in titles:
        return titles[base]
    return "（未命名/系统会话）"

# ==================== 底层切片与缓存引擎 ====================




def get_daily_data(agent_type, sort_by_tokens=False, force_refresh=False, summary_only=False):
    """
    获取结构化的每日会话账本数据 (返回纯 dict/list，无终端控制台输出)
    
    主要逻辑：
    1. 优先使用原生 adapter 获取数据源，如果不可用则回退到 ccusage CLI 调用。
    2. 基于日期处理本地结果缓存（JSON 文件），未缓存历史日则进行增量刷新。
    3. 合并各日期的会话切片，汇总得出总体用量、成本统计和以周/日为单位的图表结构。
    4. summary_only: 为 True 时仅计算宏观指标与日趋势，跳过单会话标题与明细构建 (全景看板提速 10x~20x)。
    """
    if agent_type not in SUPPORTED_AGENTS:
        raise ValueError(f"未知 Agent 类型: {agent_type}")

    info = SUPPORTED_AGENTS[agent_type]
    display_name = info["name"]

    # 8 个 Agent 均已配备专属原生适配器 (ADAPTERS 与 SUPPORTED_AGENTS 的键集完全一致)，
    # 因此不存在"回退到外部 ccusage CLI"的路径，此处直接取用适配器实例。
    adapter = ADAPTERS[agent_type]
    if summary_only:
        titles = {}
        times_override = {}
    else:
        titles, times_override = adapter.get_titles_and_times()

    agent_lock = get_agent_lock(agent_type)
    with agent_lock:

        today_str = datetime.now().strftime("%Y-%m-%d")

        # 原生适配器：直接使用由文件级 mtime 缓存精准保障的 native_daily_map，
        # 彻底杜绝旧按日缓存导致的会话唤醒迟滞或数据陈旧问题。
        #
        # 【关键不变式】适配器的 _full_cache 必须视为只读！
        # 这里必须先浅拷贝列表，并且只在真要改写 lastActivity 时才拷贝字典。
        # 否则下一步的异机数据 append 会直接写进适配器缓存对象，进而被
        # export_local_snapshot() 以"本机数据"的名义写进 Git 分片并永久固化。
        native_daily_map, _ = adapter.fetch_data()
        active_days = sorted(native_daily_map.keys())
        day_sessions_map = OrderedDict()
        for d in active_days:
            s_list = list(native_daily_map.get(d, []))
            for i, s in enumerate(s_list):
                sid = s.get("sessionId")
                if not s.get("lastActivity") and sid in times_override:
                    s = dict(s)
                    s["lastActivity"] = times_override[sid]
                    s_list[i] = s
            day_sessions_map[d] = s_list

        # 多端异机数据融合 (短路开销 < 0.005ms)
        remote_daily, _ = get_remote_agent_data(agent_type)
        if remote_daily:
            for d_str, r_list in remote_daily.items():
                if d_str not in day_sessions_map:
                    day_sessions_map[d_str] = []
                    if d_str not in active_days:
                        active_days.append(d_str)
                # 建立该日期下已存在的 sessionId 集合，避免重复插入
                existing_sids = {s.get("sessionId") for s in day_sessions_map[d_str] if s.get("sessionId")}
                for rs in r_list:
                    if rs.get("sessionId") not in existing_sids:
                        day_sessions_map[d_str].append(rs)
            active_days.sort()

    # 3. 统计与分层聚合
    grand_total = 0
    grand_input = 0
    grand_cache = 0
    grand_output = 0
    grand_cost = 0.0
    total_records = 0

    daily_trend = []
    weeks_dict = OrderedDict()
    flat_records = []

    global_idx = 1
    # 逐日进行聚合并归入对应的周维度中
    for d_str in active_days:
        try:
            dt = datetime.strptime(d_str, "%Y-%m-%d")
            week_key = f"{dt.isocalendar().year}-W{dt.isocalendar().week:02d}"
            weekday_char = WEEKDAYS[dt.weekday()]
        except Exception:
            week_key = "未知周"
            weekday_char = "未知"

        if week_key not in weeks_dict:
            weeks_dict[week_key] = {
                "weekKey": week_key,
                "totalTokens": 0,
                "inputTokens": 0,
                "cacheTokens": 0,
                "outputTokens": 0,
                "costCny": 0.0,
                "count": 0,
                "days": []
            }

        s_list = list(day_sessions_map.get(d_str, []))
        s_list.sort(key=lambda x: x.get("lastActivity") or "")

        day_total = 0
        day_input = 0
        day_cache = 0
        day_output = 0
        day_cost = 0.0
        day_records = []

        for s in s_list:
            tot = s.get("totalTokens", 0)
            inp = s.get("inputTokens", 0)
            ca = s.get("cacheReadTokens", 0)
            out = max(0, tot - (inp + ca))
            cost = calc_deepseek_cost(inp, ca, out)

            if not summary_only:
                sid = s.get("sessionId", "")
                title = s.get("title") or resolve_title(sid, titles)
                time_display = format_time(s.get("lastActivity"))
                if time_display == "--":
                    time_display = d_str[5:]

                record = {
                    "index": global_idx,
                    "date": d_str,
                    "time": time_display,
                    "isoTime": s.get("lastActivity") or "",
                    "sessionId": sid,
                    "title": title,
                    "totalTokens": tot,
                    "inputTokens": inp,
                    "cacheTokens": ca,
                    "outputTokens": out,
                    "costCny": round(cost, 2),
                    "costCnyRaw": cost,
                    "remoteDevice": s.get("remoteDevice", ""),
                    "isRemote": s.get("isRemote", False),
                }
                day_records.append(record)
                flat_records.append(record)
                global_idx += 1

            day_total += tot
            day_input += inp
            day_cache += ca
            day_output += out
            day_cost += cost

        record_cnt = len(s_list) if summary_only else len(day_records)

        # 日小计统计构建
        if not summary_only:
            day_summary = {
                "date": d_str,
                "weekday": weekday_char,
                "totalTokens": day_total,
                "inputTokens": day_input,
                "cacheTokens": day_cache,
                "outputTokens": day_output,
                "costCny": round(day_cost, 2),
                "records": day_records,
                "count": record_cnt
            }
            weeks_dict[week_key]["days"].append(day_summary)
            weeks_dict[week_key]["totalTokens"] += day_total
            weeks_dict[week_key]["inputTokens"] += day_input
            weeks_dict[week_key]["cacheTokens"] += day_cache
            weeks_dict[week_key]["outputTokens"] += day_output
            weeks_dict[week_key]["costCny"] += day_cost
            weeks_dict[week_key]["count"] += record_cnt

        daily_trend.append({
            "date": d_str,
            "weekday": weekday_char,
            "totalTokens": day_total,
            "inputTokens": day_input,
            "cacheTokens": day_cache,
            "outputTokens": day_output,
            "costCny": round(day_cost, 2),
            "count": record_cnt
        })

        grand_total += day_total
        grand_input += day_input
        grand_cache += day_cache
        grand_output += day_output
        grand_cost += day_cost
        total_records += record_cnt

    # 格式化周小计的 costCny
    weeks = list(weeks_dict.values())
    for w in weeks:
        w["costCny"] = round(w["costCny"], 2)

    # 根据请求处理排序逻辑
    if sort_by_tokens and not summary_only:
        flat_records.sort(key=lambda x: x.get("totalTokens", 0), reverse=True)
        # 重新为 flat_records 编号
        for i, r in enumerate(flat_records, 1):
            r["index"] = i

    hit_rate = round(grand_cache / max(1, grand_input + grand_cache) * 100, 2)

    today_entry = next((d for d in daily_trend if d["date"] == today_str), None)
    if today_entry:
        t_inp = today_entry["inputTokens"]
        t_ca = today_entry["cacheTokens"]
        today_dict = {
            "date": today_str,
            "weekday": today_entry.get("weekday", ""),
            "totalTokens": today_entry["totalTokens"],
            "inputTokens": t_inp,
            "cacheTokens": t_ca,
            "outputTokens": today_entry["outputTokens"],
            "costCny": today_entry["costCny"],
            "cacheHitRate": round(t_ca / max(1, t_inp + t_ca) * 100, 1),
            "sessionCount": today_entry.get("count", 0)
        }
    else:
        today_dict = {
            "date": today_str,
            "weekday": WEEKDAYS[datetime.now().weekday()],
            "totalTokens": 0,
            "inputTokens": 0,
            "cacheTokens": 0,
            "outputTokens": 0,
            "costCny": 0.0,
            "cacheHitRate": 0.0,
            "sessionCount": 0
        }

    return {
        "agent": agent_type,
        "displayName": display_name,
        "mode": "daily",
        "sortByTokens": sort_by_tokens,
        "activeDaysCount": len(active_days),
        "totalRecordsCount": total_records,
        "summary": {
            "totalTokens": grand_total,
            "inputTokens": grand_input,
            "cacheTokens": grand_cache,
            "outputTokens": grand_output,
            "costCny": round(grand_cost, 2),
            "costUsd": round(grand_cost / USD_CNY_RATE, 2),
            "cacheHitRate": hit_rate
        },
        "today": today_dict,
        "dailyTrend": daily_trend,
        "weeks": [] if summary_only else weeks,
        "flatRecords": [] if summary_only else flat_records
    }


def get_session_data(agent_type, sort_by_tokens=False):
    """
    获取结构化的项目全生命周期总览数据 (返回纯 dict/list，无终端控制台输出)

    提取整个项目中每个独立 Session / Thread 的整体消耗，不按天进行切分，
    统一由各 Agent 的原生适配器提取。
    """
    if agent_type not in SUPPORTED_AGENTS:
        raise ValueError(f"未知 Agent 类型: {agent_type}")

    info = SUPPORTED_AGENTS[agent_type]
    display_name = info["name"]

    # 8 个 Agent 均已配备原生适配器，不存在 CLI 回退路径
    adapter = ADAPTERS[agent_type]
    titles, times_override = adapter.get_titles_and_times()

    agent_lock = get_agent_lock(agent_type)
    with agent_lock:
        _, raw_sessions = adapter.fetch_data()

        # 多端异机会话融合 (短路开销 < 0.005ms)
        _, remote_sessions = get_remote_agent_data(agent_type)
        if remote_sessions:
            local_sids = {s.get("sessionId") for s in raw_sessions if s.get("sessionId")}
            combined = list(raw_sessions)
            for rs in remote_sessions:
                if rs.get("sessionId") not in local_sids:
                    combined.append(rs)
            raw_sessions = combined

    sessions = []
    grand_total = 0
    grand_input = 0
    grand_cache = 0
    grand_output = 0
    grand_cost = 0.0

    for s in raw_sessions:
        sid = s.get("sessionId", "")
        last_act = s.get("lastActivity")
        if not last_act and sid in times_override:
            last_act = times_override[sid]

        tot = s.get("totalTokens", 0)
        inp = s.get("inputTokens", 0)
        ca = s.get("cacheReadTokens", 0)
        out = max(0, tot - (inp + ca))
        cost = calc_deepseek_cost(inp, ca, out)
        title = s.get("title") or resolve_title(sid, titles)

        grand_total += tot
        grand_input += inp
        grand_cache += ca
        grand_output += out
        grand_cost += cost

        sessions.append({
            "sessionId": sid,
            "lastActivity": last_act or "",
            "time": format_time(last_act),
            "title": title,
            "totalTokens": tot,
            "inputTokens": inp,
            "cacheTokens": ca,
            "outputTokens": out,
            "costCny": round(cost, 2),
            "costCnyRaw": cost,
            "remoteDevice": s.get("remoteDevice", ""),
            "isRemote": s.get("isRemote", False),
        })

    if sort_by_tokens:
        sessions.sort(key=lambda x: x.get("totalTokens", 0), reverse=True)
        for idx, s in enumerate(sessions, 1):
            s["index"] = idx
        weeks = []
    else:
        sessions.sort(key=lambda x: x.get("lastActivity") or "", reverse=False)
        for idx, s in enumerate(sessions, 1):
            s["index"] = idx

        # 分周与分日聚合数据构建：遍历 session 划分入对应周与日的桶
        weeks_dict = OrderedDict()
        for s in sessions:
            iso = s.get("lastActivity")
            if iso:
                try:
                    dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()
                    week_key = f"{dt.isocalendar().year}-W{dt.isocalendar().week:02d}"
                    day_key = dt.strftime("%Y-%m-%d")
                    weekday_char = WEEKDAYS[dt.weekday()]
                except Exception:
                    week_key = "未知周"
                    day_key = "未知日期"
                    weekday_char = "未知"
            else:
                week_key = "未知周"
                day_key = "未知日期"
                weekday_char = "未知"

            if week_key not in weeks_dict:
                weeks_dict[week_key] = {
                    "weekKey": week_key,
                    "totalTokens": 0,
                    "inputTokens": 0,
                    "cacheTokens": 0,
                    "outputTokens": 0,
                    "costCny": 0.0,
                    "count": 0,
                    "days_map": OrderedDict()
                }

            w_entry = weeks_dict[week_key]
            if day_key not in w_entry["days_map"]:
                w_entry["days_map"][day_key] = {
                    "date": day_key,
                    "weekday": weekday_char,
                    "totalTokens": 0,
                    "inputTokens": 0,
                    "cacheTokens": 0,
                    "outputTokens": 0,
                    "costCny": 0.0,
                    "records": []
                }
            d_entry = w_entry["days_map"][day_key]
            d_entry["records"].append(s)
            d_entry["totalTokens"] += s["totalTokens"]
            d_entry["inputTokens"] += s["inputTokens"]
            d_entry["cacheTokens"] += s["cacheTokens"]
            d_entry["outputTokens"] += s["outputTokens"]
            d_entry["costCny"] += s["costCnyRaw"]

            w_entry["totalTokens"] += s["totalTokens"]
            w_entry["inputTokens"] += s["inputTokens"]
            w_entry["cacheTokens"] += s["cacheTokens"]
            w_entry["outputTokens"] += s["outputTokens"]
            w_entry["costCny"] += s["costCnyRaw"]
            w_entry["count"] += 1

        weeks = []
        for w_k, w_v in weeks_dict.items():
            days_list = []
            for d_k, d_v in w_v["days_map"].items():
                d_v["costCny"] = round(d_v["costCny"], 2)
                d_v["count"] = len(d_v["records"])
                days_list.append(d_v)
            weeks.append({
                "weekKey": w_k,
                "totalTokens": w_v["totalTokens"],
                "inputTokens": w_v["inputTokens"],
                "cacheTokens": w_v["cacheTokens"],
                "outputTokens": w_v["outputTokens"],
                "costCny": round(w_v["costCny"], 2),
                "count": w_v["count"],
                "days": days_list
            })

    hit_rate = round(grand_cache / max(1, grand_input + grand_cache) * 100, 2)

    return {
        "agent": agent_type,
        "displayName": display_name,
        "mode": "session",
        "sortByTokens": sort_by_tokens,
        "totalRecordsCount": len(sessions),
        "summary": {
            "totalTokens": grand_total,
            "inputTokens": grand_input,
            "cacheTokens": grand_cache,
            "outputTokens": grand_output,
            "costCny": round(grand_cost, 2),
            "costUsd": round(grand_cost / USD_CNY_RATE, 2),
            "cacheHitRate": hit_rate
        },
        "weeks": weeks,
        "flatRecords": sessions
    }

def get_all_agents_summary(force_refresh=False):
    """
    汇总所有支持的 Agent 的用量与概览，支持 Web 端全局看板 (多线程并发调度极速版)
    
    使用 ThreadPoolExecutor 进行并发调度，将每一个 Agent 的日常抓取计算分发到独立的线程执行。
    聚合全平台全 Agent 每日趋势 (dailyTrend)、今日实时指标 (today) 以及全周期汇总 (grandSummary)。
    """
    agents_summary = []
    grand_tokens = 0
    grand_input = 0
    grand_cache = 0
    grand_output = 0
    grand_cost = 0.0
    grand_sessions = 0

    def _fetch_single_agent(agent_id, agent_meta):
        """线程运行任务：独立获取并总结单个 Agent 的使用详情"""
        try:
            data = get_daily_data(agent_id, force_refresh=force_refresh, summary_only=True)
            sum_info = data["summary"]
            rec_cnt = data["totalRecordsCount"]
            daily_trend = data.get("dailyTrend", [])
            return {
                "id": agent_id,
                "name": agent_meta["name"],
                "totalTokens": sum_info.get("totalTokens", 0),
                "inputTokens": sum_info.get("inputTokens", 0),
                "cacheTokens": sum_info.get("cacheTokens", 0),
                "outputTokens": sum_info.get("outputTokens", 0),
                "costCny": sum_info.get("costCny", 0.0),
                "costUsd": sum_info.get("costUsd", 0.0),
                "recordsCount": rec_cnt,
                "cacheHitRate": sum_info.get("cacheHitRate", 0.0),
                "dailyTrend": daily_trend
            }
        except Exception:
            # 个别 Agent 若在本地未安装或无记录，宽容返回 0
            return {
                "id": agent_id,
                "name": agent_meta["name"],
                "totalTokens": 0,
                "inputTokens": 0,
                "cacheTokens": 0,
                "outputTokens": 0,
                "costCny": 0.0,
                "costUsd": 0.0,
                "recordsCount": 0,
                "cacheHitRate": 0.0,
                "dailyTrend": []
            }

    agent_ids = list(SUPPORTED_AGENTS.keys())
    # 启用线程池并发执行各 Agent 抓取任务
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(agent_ids)) as pool:
        future_map = {
            pool.submit(_fetch_single_agent, aid, SUPPORTED_AGENTS[aid]): aid
            for aid in agent_ids
        }
        results_by_id = {}
        # 收集所有的并发执行结果
        for fut in concurrent.futures.as_completed(future_map):
            aid = future_map[fut]
            results_by_id[aid] = fut.result()

    daily_trend_by_date = {}
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_active_agents = set()

    # 严格保持 SUPPORTED_AGENTS 初始定义的排列顺序
    for aid in agent_ids:
        item = results_by_id[aid]
        # agents 列表中剔除冗余的单 Agent dailyTrend，保证传输体量精简轻快
        clean_item = {k: v for k, v in item.items() if k != "dailyTrend"}
        agents_summary.append(clean_item)
        grand_tokens += item["totalTokens"]
        grand_input += item["inputTokens"]
        grand_cache += item["cacheTokens"]
        grand_output += item["outputTokens"]
        grand_cost += item["costCny"]
        grand_sessions += item["recordsCount"]

        # 聚合每日时序数据
        for d in item.get("dailyTrend", []):
            d_str = d.get("date")
            if not d_str:
                continue
            if d_str not in daily_trend_by_date:
                daily_trend_by_date[d_str] = {
                    "date": d_str,
                    "weekday": d.get("weekday", ""),
                    "totalTokens": 0,
                    "inputTokens": 0,
                    "cacheTokens": 0,
                    "outputTokens": 0,
                    "costCny": 0.0,
                    "agentTokens": {}
                }
            cur = daily_trend_by_date[d_str]
            cur["totalTokens"] += d.get("totalTokens", 0)
            cur["inputTokens"] += d.get("inputTokens", 0)
            cur["cacheTokens"] += d.get("cacheTokens", 0)
            cur["outputTokens"] += d.get("outputTokens", 0)
            cur["costCny"] += d.get("costCny", 0.0)
            if "agentTokens" not in cur:
                cur["agentTokens"] = {}
            cur["agentTokens"][aid] = d.get("totalTokens", 0)

            if d_str == today_str and d.get("totalTokens", 0) > 0:
                today_active_agents.add(aid)

    # 聚合各日趋势按日期正序排列
    aggregated_trend = sorted(daily_trend_by_date.values(), key=lambda x: x["date"])
    for x in aggregated_trend:
        x["costCny"] = round(x["costCny"], 2)

    # 提取今日实时总览
    today_data = daily_trend_by_date.get(today_str, {
        "date": today_str,
        "weekday": WEEKDAYS[datetime.now().weekday()],
        "totalTokens": 0,
        "inputTokens": 0,
        "cacheTokens": 0,
        "outputTokens": 0,
        "costCny": 0.0
    })
    today_inp = today_data["inputTokens"]
    today_ca = today_data["cacheTokens"]
    today_hit_rate = round(today_ca / max(1, today_inp + today_ca) * 100, 1)

    today_summary = {
        "date": today_str,
        "weekday": today_data.get("weekday", ""),
        "totalTokens": today_data["totalTokens"],
        "inputTokens": today_inp,
        "cacheTokens": today_ca,
        "outputTokens": today_data["outputTokens"],
        "costCny": round(today_data["costCny"], 2),
        "cacheHitRate": today_hit_rate,
        "activeAgentsCount": len(today_active_agents)
    }

    grand_hit_rate = round(grand_cache / max(1, grand_input + grand_cache) * 100, 2)
    grand_summary = {
        "totalTokens": grand_tokens,
        "inputTokens": grand_input,
        "cacheTokens": grand_cache,
        "outputTokens": grand_output,
        "costCny": round(grand_cost, 2),
        "costUsd": round(grand_cost / 7.2, 2),
        "totalSessions": grand_sessions,
        "cacheHitRate": grand_hit_rate
    }

    return {
        "displayName": "全景对比 (全 Agent 矩阵)",
        "mode": "daily",
        "grandSummary": grand_summary,
        "summary": grand_summary,
        "today": today_summary,
        "activeDaysCount": len(aggregated_trend),
        "dailyTrend": aggregated_trend,
        "agents": agents_summary
    }

# ==================== 今日极速摘要与 Dock 状态嗅探模块 ====================

_TODAY_CACHE = {
    "date": "",
    "fingerprints": {},
    "timestamp": 0.0,
    "data": None
}
_TODAY_CACHE_LOCK = threading.Lock()
_AGENT_TODAY_CACHE = {}  # aid -> { "fingerprint": str, "date": str, "data": dict }
_AGENT_TODAY_CACHE_LOCK = threading.Lock()

def format_tokens_short(n):
    """短格式化 Token 数，适合在微型 Dock 图标或气泡卡片中展示：
    - 3位数 (>= 100): 不显示小数点后数字，例如 175M, 250K, 120B
    - 两位数 (10 ~ 99): 只显示小数点后1位，例如 25.4M, 12.3K, 45.6B
    - 1位数 (1 ~ 9): 显示小数点后2位 (M/B) 或 1位 (K)，例如 5.23M, 1.5K
    """
    if not n or n <= 0:
        return "0"
    if n >= 1_000_000_000:
        val, unit = n / 1_000_000_000, "B"
    elif n >= 1_000_000:
        val, unit = n / 1_000_000, "M"
    elif n >= 1_000:
        val, unit = n / 1_000, "K"
    else:
        return str(n)

    if val >= 99.95:
        return f"{int(round(val))}{unit}"
    elif val >= 9.95:
        return f"{val:.1f}{unit}"
    else:
        return f"{val:.1f}K" if unit == "K" else f"{val:.2f}{unit}"

def get_today_quick_summary(force_refresh=False):
    """
    极速获取今日各 Agent 的 Token 吞吐与概况（含多端异机数据融合）：
    - 双指纹预检：本机数据源指纹 + 异机分片指纹共同构成缓存键，
      同一天内且两端均无变化时 0.01ms 瞬时返回；异机账本一变即立刻穿透缓存
    - 差异化智能调度：仅对指纹发生变动的 Agent 触发并发提取 (today_only=True)
    - 结合今日热文件快速剪枝，相比全盘扫描性能提速 50x~600x
    - 异机今日切片来自 load_remote_devices_data() 的内存级并集缓存（未开启同步时短路 < 0.005ms），
      因此本接口与 Web 端 /api/data、/api/all 共用同一份跨端口径，程序屋不再落后于 Web 看板
    """
    global _TODAY_CACHE, _AGENT_TODAY_CACHE
    today_str = datetime.now().strftime("%Y-%m-%d")

    # 1. 快速提取各 Agent 当前的轻量级指纹 (< 5ms)
    #    异机分片指纹一并纳入缓存键：保证远端同步完成后本机摘要立即失效重算
    remote_fp = get_remote_fingerprint()
    base_fps = {}
    for aid, ad in ADAPTERS.items():
        if ad and ad.is_available():
            try:
                local_fp = ad.get_source_fingerprint()
            except Exception:
                local_fp = ""
            base_fps[aid] = f"{local_fp}#{remote_fp}"

    with _TODAY_CACHE_LOCK:
        if (
            not force_refresh
            and _TODAY_CACHE["data"] is not None
            and _TODAY_CACHE["date"] == today_str
            and _TODAY_CACHE["fingerprints"] == base_fps
            and (time.time() - _TODAY_CACHE["timestamp"] < 60.0)
        ):
            return _TODAY_CACHE["data"]

    # 2. 补齐"本机未安装但异机在用"的 Agent，保证今日概览与 Web 端全 Agent 口径一致
    #    (仅在缓存未命中、确认需要重算时才展开，热路径零额外开销)
    current_fps = dict(base_fps)
    for aid in get_remote_agent_ids():
        if aid not in current_fps and aid in SUPPORTED_AGENTS:
            current_fps[aid] = f"remote-only#{remote_fp}"

    # 3. 差异化调度：筛选出指纹发生变动或今日未缓存的 Agent
    needed_aids = []
    with _AGENT_TODAY_CACHE_LOCK:
        for aid, fp in current_fps.items():
            cached = _AGENT_TODAY_CACHE.get(aid)
            if force_refresh or not cached or cached.get("date") != today_str or cached.get("fingerprint") != fp:
                needed_aids.append(aid)

    # 4. 仅对需要刷新的 Agent 并发提取今日切片 (本机走热文件剪枝 + 异机走内存并集)
    def _fetch_agent_today(aid):
        adapter = ADAPTERS.get(aid)
        local_slices = []
        if adapter and adapter.is_available():
            try:
                dmap, _ = adapter.fetch_data(today_only=True)
                local_slices = dmap.get(today_str, [])
            except Exception:
                local_slices = []

        # 异机今日切片融合：未开启同步时 get_remote_agent_data 立即短路 (< 0.005ms)
        remote_slices = []
        try:
            remote_daily, _ = get_remote_agent_data(aid)
            if remote_daily:
                remote_slices = remote_daily.get(today_str, [])
        except Exception:
            remote_slices = []

        # 以 sessionId 去重合并：本机切片优先，异机补集
        # 注意这里只读取远端字典，绝不就地改写它们
        if remote_slices:
            seen_sids = {s.get("sessionId") for s in local_slices if s.get("sessionId")}
            slices = list(local_slices)
            for rs in remote_slices:
                sid = rs.get("sessionId")
                if sid and sid in seen_sids:
                    continue
                if sid:
                    seen_sids.add(sid)
                slices.append(rs)
        else:
            slices = list(local_slices)

        if not slices:
            return aid, None
        try:
            t_tokens = sum(s.get("totalTokens", 0) for s in slices)
            if t_tokens <= 0:
                return aid, None
            t_inp = sum(s.get("inputTokens", 0) for s in slices)
            t_cache = sum(s.get("cacheReadTokens", 0) for s in slices)
            t_out = sum(s.get("outputTokens", 0) for s in slices)
            cost = calc_deepseek_cost(t_inp, t_cache, t_out)
            hit_rate = round(t_cache / max(1, t_inp + t_cache) * 100, 1)

            latest_s = max(slices, key=lambda s: s.get("lastActivity", "") or "", default=None)

            if adapter:
                display_name = adapter.display_name
            else:
                display_name = SUPPORTED_AGENTS.get(aid, {}).get("name", aid)

            return aid, {
                "id": aid,
                "name": display_name,
                "totalTokens": t_tokens,
                "displayTokens": format_tokens_short(t_tokens),
                "inputTokens": t_inp,
                "cacheTokens": t_cache,
                "outputTokens": t_out,
                "hitRate": hit_rate,
                "costCny": round(cost, 2),
                "sessionCount": len(slices),
                "latestSession": latest_s
            }
        except Exception:
            return aid, None

    if needed_aids:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(needed_aids)) as pool:
            future_map = {pool.submit(_fetch_agent_today, aid): aid for aid in needed_aids}
            for fut in concurrent.futures.as_completed(future_map):
                aid, res = fut.result()
                with _AGENT_TODAY_CACHE_LOCK:
                    _AGENT_TODAY_CACHE[aid] = {
                        "fingerprint": current_fps.get(aid, ""),
                        "date": today_str,
                        "data": res
                    }

    # 5. 从 per-agent 缓存中汇总所有有效 Agent 数据
    raw_agent_results = []
    with _AGENT_TODAY_CACHE_LOCK:
        for aid in current_fps.keys():
            item = _AGENT_TODAY_CACHE.get(aid)
            if item and item.get("data") and item.get("date") == today_str:
                raw_agent_results.append(item["data"])

    # 计算跨所有 Agent 中最新活跃的一个 session
    all_latest_sessions = []
    for a in raw_agent_results:
        ls = a.get("latestSession")
        if ls and ls.get("lastActivity"):
            all_latest_sessions.append((ls.get("lastActivity", ""), a["name"], ls))

    all_latest_sessions.sort(key=lambda x: x[0], reverse=True)
    if all_latest_sessions:
        _, latest_agent_name, top_s = all_latest_sessions[0]
        s_inp = top_s.get("inputTokens", 0)
        s_cache = top_s.get("cacheReadTokens", 0)
        latest_hit_rate = round(s_cache / max(1, s_inp + s_cache) * 100, 1) if (s_inp + s_cache) > 0 else 0.0
    else:
        latest_agent_name = ""
        latest_hit_rate = 0.0

    # 生成返回前端与 Dock 的展示列表，剥离内部 latestSession 原始对象
    agent_results = []
    for a in raw_agent_results:
        a_copy = dict(a)
        a_copy.pop("latestSession", None)
        agent_results.append(a_copy)

    agent_results.sort(key=lambda x: x["totalTokens"], reverse=True)

    today_tokens = sum(a["totalTokens"] for a in agent_results)
    today_input = sum(a["inputTokens"] for a in agent_results)
    today_cache = sum(a["cacheTokens"] for a in agent_results)
    today_output = sum(a["outputTokens"] for a in agent_results)
    today_cost = sum(a["costCny"] for a in agent_results)
    today_hit_rate = round(today_cache / max(1, today_input + today_cache) * 100, 1) if (today_input + today_cache) > 0 else 0.0

    result = {
        "date": today_str,
        "totalTokens": today_tokens,
        "displayTokens": format_tokens_short(today_tokens),
        "inputTokens": today_input,
        "cacheTokens": today_cache,
        "outputTokens": today_output,
        "cacheHitRate": today_hit_rate,
        "latestSessionHitRate": latest_hit_rate if all_latest_sessions else today_hit_rate,
        "latestSessionAgent": latest_agent_name,
        "costCny": round(today_cost, 2),
        "costUsd": round(today_cost / USD_CNY_RATE, 2),
        "activeAgentsCount": len(agent_results),
        "agents": agent_results
    }

    with _TODAY_CACHE_LOCK:
        _TODAY_CACHE["date"] = today_str
        # 注意存 base_fps（本机指纹）而非 current_fps：
        # 后者在远程独有 Agent 上会被动态补齐，存它会导致下一次比较永远不相等而反复重算
        _TODAY_CACHE["fingerprints"] = base_fps
        _TODAY_CACHE["timestamp"] = time.time()
        _TODAY_CACHE["data"] = result

    return result

