"""
myccusage_lib.core:
核心数据与计算内核：
- 8 大 Agent 原生会话标题与时间元数据解析
- DeepSeek-V4.1-Flash 高峰期等效计价模型
- ~/.cache/myccusage 智能切片与两级缓存
- 纯结构化日账本 (Daily) 与项目总览 (Session) 聚合计算
"""

import subprocess
import json
import re
import glob
import sys
import sqlite3
import os
import time
import threading
import shutil
import concurrent.futures
from datetime import datetime, timezone
from collections import OrderedDict
from .adapters import ADAPTERS, get_adapter

# 星期常量映射
WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"]

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
SUPPORTED_AGENTS = {
    "agy": {"name": "Google Antigravity", "subcmd": "antigravity", "has_times": False},
    "claude": {"name": "Claude Code", "subcmd": "claude", "has_times": False},
    "hermes": {"name": "Hermes Agent", "subcmd": "hermes", "has_times": True},
    "codex": {"name": "OpenAI Codex", "subcmd": "codex", "has_times": False},
    "grok": {"name": "Grok", "subcmd": "grok", "has_times": False},
    "pi": {"name": "Pi Agent", "subcmd": "pi", "has_times": False},
    "opencode": {"name": "OpenCode", "subcmd": "opencode", "has_times": True},
    "workbuddy": {"name": "WorkBuddy", "subcmd": "workbuddy", "has_times": True},
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

def get_agy_titles():
    """
    提取 Antigravity 会话标题。
    委托给 AntigravityAdapter 的原生纯净提取逻辑（含精准 Protobuf 解析与子任务靶标智能提炼）。
    """
    adapter = get_adapter("agy")
    if adapter and adapter.is_available():
        titles, _ = adapter.get_titles_and_times()
        return titles
    return {}


def get_claude_titles():
    """
    提取 Claude Code 会话标题与用户 Prompt。
    主要从 history.jsonl 与各个 project 的 jsonl 日志中提取 display 或用户首句。
    """
    titles = {}
    history_file = os.path.expanduser("~/.claude/history.jsonl")
    if os.path.exists(history_file):
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        obj = json.loads(line)
                        sid = obj.get("sessionId")
                        disp = obj.get("display", "").strip()
                        if sid and disp and sid not in titles:
                            titles[sid] = disp[:60]
                    except Exception:
                        pass
        except Exception:
            pass

    # 扫描 projects 目录补充未在 history.jsonl 中的标题
    for p in glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl")):
        sid = os.path.basename(p).replace(".jsonl", "")
        if sid not in titles or titles[sid].startswith("/"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        obj = json.loads(line)
                        # 寻找类型为 user 的消息，提取其中的内容
                        if obj.get("type") == "user":
                            msg = obj.get("message", {})
                            cnt = msg.get("content")
                            if isinstance(cnt, str) and cnt.strip():
                                titles[sid] = cnt.split("\n")[0][:60].strip()
                                break
                            elif isinstance(cnt, list):
                                for item in cnt:
                                    if isinstance(item, dict) and item.get("text"):
                                        titles[sid] = item["text"].split("\n")[0][:60].strip()
                                        break
                                if sid in titles:
                                    break
            except Exception:
                pass
    return titles

def get_hermes_titles_and_times():
    """
    提取 Hermes 会话标题与结束时间。
    解析内部 SQLite 数据库，获取 started_at/ended_at 以及标题字段。
    返回 (标题字典, 时间字典) 的元组。
    """
    titles = {}
    times = {}
    db_path = os.path.expanduser("~/.hermes/state.db")
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            for row in c.execute("SELECT id, started_at, ended_at, title FROM sessions"):
                sid, st, et, title = row
                # 优先使用结束时间作为最后活动时间
                last_t = et or st
                if last_t:
                    iso_time = datetime.fromtimestamp(last_t, timezone.utc).isoformat()
                    times[sid] = iso_time
                if title:
                    titles[sid] = title
            conn.close()
        except Exception:
            pass
    return titles, times

def get_codex_titles():
    """
    提取 OpenAI Codex 会话标题与用户 Prompt。
    包括从 session_index.jsonl 加载以及从归档、现存的 jsonl 日志提取内容。
    """
    titles = {}
    index_map = {}
    index_file = os.path.expanduser("~/.codex/session_index.jsonl")
    if os.path.exists(index_file):
        try:
            with open(index_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        row = json.loads(line)
                        if "id" in row and row.get("thread_name"):
                            index_map[row["id"]] = row["thread_name"].strip()
                    except Exception:
                        pass
        except Exception:
            pass

    def extract_codex_prompt(text):
        """清洗提取 Codex 用户侧原始 prompt"""
        if not text:
            return ""
        if "## My request for Codex:" in text:
            text = text.split("## My request for Codex:")[-1].strip()
        text = re.sub(r"<[^>]+>", "", text).strip()
        return " ".join(text.split())

    session_files = glob.glob(os.path.expanduser("~/.codex/sessions/**/*.jsonl"), recursive=True)
    session_files += glob.glob(os.path.expanduser("~/.codex/archived_sessions/*.jsonl"))

    # 遍历各个会话文件，解析消息以获取标题
    for p in session_files:
        rel = p.replace(os.path.expanduser("~/.codex/sessions/"), "").replace(".jsonl", "")
        base = os.path.basename(p).replace(".jsonl", "")
        parts = base.split("-")
        uuid = "-".join(parts[-5:]) if len(parts) >= 5 else base

        title = index_map.get(uuid)
        if not title:
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            item = json.loads(line)
                            pl = item.get("payload", {})
                            ptype = pl.get("type")
                            if ptype == "user_message":
                                raw = pl.get("message", "")
                                clean = extract_codex_prompt(raw)
                                if clean and not clean.startswith("<environment_context>"):
                                    title = clean
                                    break
                            elif ptype == "message" and pl.get("role") == "user":
                                for part in pl.get("content", []):
                                    if isinstance(part, dict) and part.get("type") == "input_text":
                                        txt = part.get("text", "")
                                        # 过滤系统上下文
                                        if "AGENTS.md" in txt or "<environment_context>" in txt:
                                            continue
                                        clean = extract_codex_prompt(txt)
                                        if clean:
                                            title = clean
                                            break
                                if title:
                                    break
                        except Exception:
                            pass
            except Exception:
                pass
        # 为同个会话的多种可能 ID 添加映射，确保命中
        if title:
            titles[rel] = title
            titles[base] = title
            titles[uuid] = title

    return titles

def get_grok_titles():
    """
    提取 Grok 会话标题与用户 Prompt。
    综合读取 session_search.sqlite、summary.json 和 prompt_history.jsonl 进行标题捕获。
    """
    titles = {}
    db_path = os.path.expanduser("~/.grok/sessions/session_search.sqlite")
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT session_id, title FROM session_docs")
            for sid, t in cur.fetchall():
                if t and t.strip():
                    titles[sid] = t.strip()
            conn.close()
        except Exception:
            pass

    for summary_path in glob.glob(os.path.expanduser("~/.grok/sessions/**/summary.json"), recursive=True):
        try:
            with open(summary_path, "r", encoding="utf-8") as f:
                sdata = json.load(f)
                sid = sdata.get("info", {}).get("id")
                summ = sdata.get("session_summary")
                if sid and summ and summ.strip() and sid not in titles:
                    titles[sid] = summ.strip()
        except Exception:
            pass

    for ph in glob.glob(os.path.expanduser("~/.grok/sessions/*/prompt_history.jsonl")):
        try:
            with open(ph, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        row = json.loads(line)
                        sid = row.get("session_id")
                        p = row.get("prompt")
                        if sid and p and sid not in titles:
                            titles[sid] = p.strip()
                    except Exception:
                        pass
        except Exception:
            pass

    return titles

def get_pi_titles():
    """
    提取 Pi Agent 会话用户 Prompt 作为标题。
    解析对应的 jsonl 文件中的 user 消息。
    """
    titles = {}
    for p in glob.glob(os.path.expanduser("~/.pi/agent/sessions/*/*.jsonl")):
        sid = os.path.basename(p).split("_")[-1].replace(".jsonl", "")
        try:
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        if data.get("type") == "message" and data.get("message", {}).get("role") == "user":
                            content = data["message"].get("content", [])
                            t = ""
                            if isinstance(content, str):
                                t = content.strip()
                            elif isinstance(content, list):
                                parts = [x.get("text", "") for x in content if isinstance(x, dict) and x.get("type") == "text"]
                                t = "".join(parts).strip()
                            if t:
                                clean_t = " ".join(t.split())
                                titles[sid] = clean_t
                                break
                    except Exception:
                        pass
        except Exception:
            pass
    return titles

def get_opencode_titles_and_times():
    """
    提取 OpenCode 会话标题与最后活跃时间。
    解析 opencode.db 数据库获取相关字段信息。
    """
    titles = {}
    times = {}
    db_path = os.path.expanduser("~/.local/share/opencode/opencode.db")
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT id, title, time_created, time_updated FROM session")
            for sid, title, tc, tu in cur.fetchall():
                ts = (tu or tc) / 1000.0 if (tu or tc) else None
                if ts:
                    iso = datetime.fromtimestamp(ts, timezone.utc).isoformat()
                    times[sid] = iso
                if title and title.strip():
                    titles[sid] = title.strip()
            conn.close()
        except Exception:
            pass
    return titles, times

def get_workbuddy_titles_and_times():
    """
    提取 WorkBuddy 会话标题与最后活跃时间。
    从 SQLite 数据库获取主记录，若缺失则从项目的 JSONL 补充扫描。
    """
    titles = {}
    times = {}
    wb_dir = os.path.expanduser("~/.workbuddy")
    db_path = os.path.join(wb_dir, "workbuddy.db")
    if os.path.exists(db_path):
        try:
            # 开启只读模式防止争锁
            uri = f"file:{db_path}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=3.0)
            cur = conn.cursor()
            for row in cur.execute("SELECT id, title, custom_title, created_at, updated_at, last_activity_at FROM sessions"):
                sid, t, ct, ca, ua, la = row
                # 优先使用 custom_title
                title = ct or t
                if title and title.strip():
                    titles[sid] = title.strip()
                # 计算出最后活跃时间并转换为 ISO 格式
                ts = la or ua or ca
                if ts:
                    times[sid] = datetime.fromtimestamp(ts / 1000.0, timezone.utc).isoformat()
            conn.close()
        except Exception:
            pass

    # 兜底补充扫描 projects 目录中未记录在 DB 或 custom-title 的会话
    project_files = glob.glob(os.path.join(wb_dir, "projects/*/*.jsonl"))
    for p in project_files:
        sid = os.path.basename(p).replace(".jsonl", "")
        if sid not in titles or not titles[sid]:
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        if "custom-title" in line or '"role":"user"' in line:
                            obj = json.loads(line)
                            if obj.get("type") == "custom-title" and obj.get("customTitle"):
                                titles[sid] = obj["customTitle"].strip()
                                break
                            elif obj.get("type") == "message" and obj.get("role") == "user":
                                cnt = obj.get("content", [])
                                if isinstance(cnt, list):
                                    for item in cnt:
                                        if isinstance(item, dict) and item.get("text"):
                                            titles[sid] = item["text"].split("\n")[0][:60].strip()
                                            break
                                elif isinstance(cnt, str):
                                    titles[sid] = cnt.split("\n")[0][:60].strip()
                                if sid in titles:
                                    break
            except Exception:
                pass
    return titles, times

# 用于保护文件流式解析内存状态的锁
_WB_SCAN_LOCK = threading.Lock()
# 文件修改时间及结果的缓存，避免重复全量读取
_WB_FILES_CACHE = {}  # fpath -> (mtime, size, list_of_records)

def scan_workbuddy_data():
    """
    高性能流式扫描 WorkBuddy 项目日志，返回 (daily_map, session_list)
    - daily_map: { "YYYY-MM-DD": [ {sessionId, totalTokens, inputTokens, cacheReadTokens, outputTokens, lastActivity}, ... ] }
    - session_list: [ {sessionId, totalTokens, inputTokens, cacheReadTokens, outputTokens, lastActivity}, ... ]
    
    利用文件大小和修改时间 (_WB_FILES_CACHE) 进行缓存感知，大幅降低 IO 压力。
    """
    wb_dir = os.path.expanduser("~/.workbuddy")
    if not os.path.exists(wb_dir):
        return {}, []

    project_globs = [
        os.path.join(wb_dir, "projects/*/*.jsonl"),
        os.path.join(wb_dir, "sessions/*/*.jsonl"),
        os.path.join(wb_dir, "sessions/*.jsonl")
    ]
    files = []
    seen_files = set()
    for g in project_globs:
        for fpath in glob.glob(g):
            if fpath not in seen_files:
                seen_files.add(fpath)
                files.append(fpath)

    daily_map = {}
    session_map = {}

    with _WB_SCAN_LOCK:
        for fpath in files:
            try:
                stat = os.stat(fpath)
            except OSError:
                continue

            mtime, size = stat.st_mtime, stat.st_size
            cached = _WB_FILES_CACHE.get(fpath)
            # 缓存命中：只有修改时间与大小全一致时直接复用解析结果
            if cached and cached[0] == mtime and cached[1] == size:
                records = cached[2]
            else:
                records = []
                sid = os.path.basename(fpath).replace(".jsonl", "")
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        for line in f:
                            # 提前短路判断以加速无关行过滤
                            if not line.strip() or ("usage" not in line and "rawUsage" not in line):
                                continue
                            try:
                                obj = json.loads(line)
                            except Exception:
                                continue
                            pd = obj.get("providerData") or {}
                            ru = pd.get("rawUsage")
                            u = pd.get("usage")
                            if not ru and not u:
                                continue
                            ts = obj.get("timestamp")
                            if not ts:
                                continue

                            dt = datetime.fromtimestamp(ts / 1000.0)
                            date_str = dt.strftime("%Y-%m-%d")
                            iso_str = datetime.fromtimestamp(ts / 1000.0, timezone.utc).isoformat()

                            # 容错处理不同的 usage 数据结构
                            if ru:
                                hit = ru.get("prompt_cache_hit_tokens", 0)
                                miss = ru.get("prompt_cache_miss_tokens", 0)
                                out = ru.get("completion_tokens", 0)
                            else:
                                if "input_tokens" in u:
                                    miss = u.get("input_tokens", 0)
                                    hit = 0
                                    out = u.get("output_tokens", 0)
                                else:
                                    inp = u.get("inputTokens", 0)
                                    hit = sum(d.get("cached_tokens", 0) for d in u.get("inputTokensDetails", []))
                                    miss = max(0, inp - hit)
                                    out = u.get("outputTokens", 0)
                            tot = hit + miss + out
                            records.append((sid, date_str, iso_str, miss, hit, out, tot))
                except Exception:
                    pass
                # 将解析结果写回缓存
                _WB_FILES_CACHE[fpath] = (mtime, size, records)

            for sid, date_str, iso_str, miss, hit, out, tot in records:
                # 每日切片数据构建：累加各项 Token 并更新最后活动时间
                if date_str not in daily_map:
                    daily_map[date_str] = {}
                if sid not in daily_map[date_str]:
                    daily_map[date_str][sid] = {
                        "sessionId": sid,
                        "date": date_str,
                        "inputTokens": 0,
                        "cacheReadTokens": 0,
                        "outputTokens": 0,
                        "totalTokens": 0,
                        "lastActivity": iso_str
                    }
                ds = daily_map[date_str][sid]
                ds["inputTokens"] += miss
                ds["cacheReadTokens"] += hit
                ds["outputTokens"] += out
                ds["totalTokens"] += tot
                if iso_str > ds["lastActivity"]:
                    ds["lastActivity"] = iso_str

                # 全生命周期会话数据构建：累加整个会话的 Token
                if sid not in session_map:
                    session_map[sid] = {
                        "sessionId": sid,
                        "inputTokens": 0,
                        "cacheReadTokens": 0,
                        "outputTokens": 0,
                        "totalTokens": 0,
                        "lastActivity": iso_str
                    }
                ss = session_map[sid]
                ss["inputTokens"] += miss
                ss["cacheReadTokens"] += hit
                ss["outputTokens"] += out
                ss["totalTokens"] += tot
                if iso_str > ss["lastActivity"]:
                    ss["lastActivity"] = iso_str

    # 转化为数组列表形式以适配外层接口
    daily_res = {d: list(s_dict.values()) for d, s_dict in daily_map.items()}
    session_res = list(session_map.values())
    return daily_res, session_res

def get_agent_metadata(agent_type):
    """根据 agent 类型路由调用对应的元数据抓取逻辑，返回 (会话标题映射, 时间修正映射)"""
    titles = {}
    times_override = {}
    if agent_type == "agy":
        titles = get_agy_titles()
    elif agent_type == "claude":
        titles = get_claude_titles()
    elif agent_type == "hermes":
        titles, times_override = get_hermes_titles_and_times()
    elif agent_type == "codex":
        titles = get_codex_titles()
    elif agent_type == "grok":
        titles = get_grok_titles()
    elif agent_type == "pi":
        titles = get_pi_titles()
    elif agent_type == "opencode":
        titles, times_override = get_opencode_titles_and_times()
    elif agent_type == "workbuddy":
        titles, times_override = get_workbuddy_titles_and_times()
    return titles, times_override

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

def check_ccusage_installed():
    """检查系统是否安装了底层 ccusage CLI 工具 (用于未被原生接管的外部工具回退)"""
    return shutil.which("ccusage") is not None

def run_ccusage(args, capture_output=True, text=True, max_retries=3):
    """
    统一安全调用底层 ccusage CLI:
    - 优先追加 --offline 参数阻断冗余公网 LiteLLM 模型价格拉取 (提速 10x+)
    - 若遇到 database is locked 错误，支持毫秒级退避重试 (解决 SQLite 读写瞬态争抢)
    - 若旧版本不支持 --offline 则自动优雅降级回退执行
    
    参数:
        args: 传递给 ccusage 命令的参数列表
        capture_output: 是否捕获输出
        text: 是否以文本模式返回
        max_retries: 最大重试次数
    """
    check_ccusage_installed()
    cmd = ["ccusage"] + list(args)
    # 强制增加离线参数，提升性能
    if "--offline" not in cmd:
        cmd.append("--offline")

    for attempt in range(max_retries):
        res = subprocess.run(cmd, capture_output=capture_output, text=text)
        stderr_lower = (res.stderr or "").lower()

        # 检查是否为 SQLite 瞬态锁冲突，毫秒级退避重试
        if res.returncode != 0 and ("database is locked" in stderr_lower or "code 5" in stderr_lower):
            if attempt < max_retries - 1:
                time.sleep(0.3 * (attempt + 1))
                continue

        # 检查是否为旧版本不识别 --offline 导致报错，降级去掉离线标志并重跑
        if res.returncode != 0 and ("unknown" in stderr_lower or "unexpected" in stderr_lower):
            cmd_fallback = [arg for arg in cmd if arg != "--offline"]
            res = subprocess.run(cmd_fallback, capture_output=capture_output, text=text)

        return res

    return res

def fetch_single_day_sessions(ccusage_subcmd, date_str, times_override):
    """获取指定日期的精确切片会话消耗（不含历史前日累积）"""
    res = run_ccusage([ccusage_subcmd, "session", "-s", date_str, "-u", date_str, "--json"])
    if res.returncode != 0:
        # 失败时返回 None 而非 []，严格区分“提取错误”与“该日无数据”，防止缓存污染 (缓存穿透防护)
        return None
    try:
        data = json.loads(res.stdout)
        sessions = data.get("sessions", [])
        # 将已有的 time 修正补充进 session 数据
        for s in sessions:
            sid = s.get("sessionId")
            if not s.get("lastActivity") and sid in times_override:
                s["lastActivity"] = times_override[sid]
        return sessions
    except Exception:
        return None

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
    ccusage_subcmd = info["subcmd"]

    # 尝试加载高效率原生适配器
    adapter = ADAPTERS.get(agent_type)
    if summary_only:
        titles = {}
        times_override = {}
    elif adapter:
        titles, times_override = adapter.get_titles_and_times()
    else:
        titles, times_override = get_agent_metadata(agent_type)

    agent_lock = get_agent_lock(agent_type)
    with agent_lock:

        today_str = datetime.now().strftime("%Y-%m-%d")

        # 优先通过原生高性能适配器获取数据
        if adapter:
            native_daily_map, _ = adapter.fetch_data()
            active_days = sorted(native_daily_map.keys())
            daily_tokens_map = {d: sum(s["totalTokens"] for s in s_list) for d, s_list in native_daily_map.items()}
        else:
            # 外部回退 (仅当系统安装了 ccusage 时可用)
            if not check_ccusage_installed():
                raise RuntimeError(f"未检测到 {agent_type} 本地数据源或 ccusage 工具")
            res_daily = run_ccusage([ccusage_subcmd, "daily", "--json"])
            if res_daily.returncode != 0:
                raise RuntimeError(f"执行 ccusage {ccusage_subcmd} daily 失败: {res_daily.stderr}")
            try:
                daily_json = json.loads(res_daily.stdout)
            except Exception as e:
                raise RuntimeError(f"无法解析 ccusage {ccusage_subcmd} daily 输出: {e}")
            daily_list = daily_json.get("daily", [])
            active_days = [d.get("date") for d in daily_list if d.get("date")]
            active_days.sort()
            daily_tokens_map = {d.get("date"): d.get("totalTokens", 0) for d in daily_list if d.get("date")}

        day_sessions_map = OrderedDict()

        if adapter:
            # 原生适配器：直接使用由文件级 mtime 缓存精准保障的 native_daily_map
            # 彻底杜绝旧按日缓存导致的会话唤醒迟滞或数据陈旧问题
            for d in active_days:
                s_list = native_daily_map.get(d, [])
                for s in s_list:
                    sid = s.get("sessionId")
                    if not s.get("lastActivity") and sid in times_override:
                        s["lastActivity"] = times_override[sid]
                day_sessions_map[d] = s_list
        else:
            # 2. 外部回退模式：读取/写入本地日期缓存 (避免全量子进程开销)
            cache_dir = os.path.expanduser("~/.cache/myccusage")
            os.makedirs(cache_dir, exist_ok=True)
            cache_file = os.path.join(cache_dir, f"{agent_type}_daily.json")

            cache = {}
            if os.path.exists(cache_file) and not force_refresh:
                try:
                    with open(cache_file, "r", encoding="utf-8") as f:
                        cache = json.load(f)
                except Exception:
                    cache = {}

            cache_dirty = False
            uncached_history_days = [
                d for d in active_days
                if d != today_str and (d not in cache or (daily_tokens_map.get(d, 0) > 0 and len(cache.get(d, [])) == 0))
            ]
            for d in uncached_history_days:
                s_list = fetch_single_day_sessions(ccusage_subcmd, d, times_override)
                if s_list is not None:
                    cache[d] = s_list
                    cache_dirty = True

            for d_str in active_days:
                if d_str != today_str:
                    day_sessions_map[d_str] = cache.get(d_str, [])
                else:
                    s_list = fetch_single_day_sessions(ccusage_subcmd, d_str, times_override)
                    if s_list is not None:
                        day_sessions_map[today_str] = s_list
                    else:
                        day_sessions_map[today_str] = cache.get(today_str, [])

            if cache_dirty:
                try:
                    with open(cache_file, "w", encoding="utf-8") as f:
                        json.dump(cache, f)
                except Exception:
                    pass

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
                title = resolve_title(sid, titles)
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
            "costUsd": round(grand_cost / 7.2, 2),
            "cacheHitRate": hit_rate
        },
        "today": today_dict,
        "dailyTrend": daily_trend,
        "weeks": [] if summary_only else weeks,
        "flatRecords": [] if summary_only else flat_records
    }


def get_session_data(agent_type, sort_by_tokens=False, clean_args=None):
    """
    获取结构化的项目全生命周期总览数据 (返回纯 dict/list，无终端控制台输出)
    
    提取整个项目中每个独立 Session / Thread 的整体消耗，不按天进行切分。
    支持用原生适配器快速构建，或者基于 ccusage CLI 命令提取。
    """
    if agent_type not in SUPPORTED_AGENTS:
        raise ValueError(f"未知 Agent 类型: {agent_type}")

    info = SUPPORTED_AGENTS[agent_type]
    display_name = info["name"]
    ccusage_subcmd = info["subcmd"]

    adapter = ADAPTERS.get(agent_type)
    if adapter:
        titles, times_override = adapter.get_titles_and_times()
    else:
        titles, times_override = get_agent_metadata(agent_type)

    agent_lock = get_agent_lock(agent_type)
    with agent_lock:
        # 分支：优先适配器原生取数据，否则回退执行命令
        if adapter:
            _, raw_sessions = adapter.fetch_data()
        else:
            if not check_ccusage_installed():
                raise RuntimeError(f"未检测到 {agent_type} 本地数据源或 ccusage 工具")
            sub_args = [ccusage_subcmd, "session", "--json"]
            if clean_args:
                sub_args.extend(clean_args)
            res = run_ccusage(sub_args)
            if res.returncode != 0:
                raise RuntimeError(f"执行 ccusage {ccusage_subcmd} session 失败: {res.stderr}")
            try:
                usage_data = json.loads(res.stdout)
            except Exception as e:
                raise RuntimeError(f"无法解析 ccusage {ccusage_subcmd} 输出: {e}")
            raw_sessions = usage_data.get("sessions", [])

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
        title = resolve_title(sid, titles)

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
            "costCnyRaw": cost
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
            "costUsd": round(grand_cost / 7.2, 2),
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
    极速获取今日各 Agent 的 Token 吞吐与概况：
    - 带单 Agent 粒度状态指纹预检：若数据源未发生改动且在同一天内，0.01ms 瞬时返回
    - 差异化智能调度：仅对指纹发生变动的 Agent 触发并发提取 (today_only=True)
    - 结合今日热文件快速剪枝，相比全盘扫描性能提速 50x~600x
    """
    global _TODAY_CACHE, _AGENT_TODAY_CACHE
    today_str = datetime.now().strftime("%Y-%m-%d")

    # 1. 快速提取各 Agent 当前的轻量级指纹 (< 5ms)
    current_fps = {}
    for aid, ad in ADAPTERS.items():
        if ad and ad.is_available():
            try:
                current_fps[aid] = ad.get_source_fingerprint()
            except Exception:
                current_fps[aid] = ""

    with _TODAY_CACHE_LOCK:
        if (
            not force_refresh
            and _TODAY_CACHE["data"] is not None
            and _TODAY_CACHE["date"] == today_str
            and _TODAY_CACHE["fingerprints"] == current_fps
            and (time.time() - _TODAY_CACHE["timestamp"] < 60.0)
        ):
            return _TODAY_CACHE["data"]

    # 2. 差异化调度：筛选出指纹发生变动或今日未缓存的 Agent
    needed_aids = []
    with _AGENT_TODAY_CACHE_LOCK:
        for aid, fp in current_fps.items():
            cached = _AGENT_TODAY_CACHE.get(aid)
            if force_refresh or not cached or cached.get("date") != today_str or cached.get("fingerprint") != fp:
                needed_aids.append(aid)

    # 3. 仅对需要刷新的 Agent 并发提取今日切片 (热文件剪枝)
    def _fetch_agent_today(aid):
        adapter = ADAPTERS.get(aid)
        if not adapter or not adapter.is_available():
            return aid, None
        try:
            dmap, _ = adapter.fetch_data(today_only=True)
            slices = dmap.get(today_str, [])
            if not slices:
                return aid, None
            t_tokens = sum(s.get("totalTokens", 0) for s in slices)
            if t_tokens <= 0:
                return aid, None
            t_inp = sum(s.get("inputTokens", 0) for s in slices)
            t_cache = sum(s.get("cacheReadTokens", 0) for s in slices)
            t_out = sum(s.get("outputTokens", 0) for s in slices)
            cost = calc_deepseek_cost(t_inp, t_cache, t_out)
            hit_rate = round(t_cache / max(1, t_inp + t_cache) * 100, 1)

            latest_s = max(slices, key=lambda s: s.get("lastActivity", "") or "", default=None)

            return aid, {
                "id": aid,
                "name": adapter.display_name,
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

    # 4. 从 per-agent 缓存中汇总所有有效 Agent 数据
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
        "costUsd": round(today_cost / 7.2, 2),
        "activeAgentsCount": len(agent_results),
        "agents": agent_results
    }

    with _TODAY_CACHE_LOCK:
        _TODAY_CACHE["date"] = today_str
        _TODAY_CACHE["fingerprints"] = current_fps
        _TODAY_CACHE["timestamp"] = time.time()
        _TODAY_CACHE["data"] = result

    return result

