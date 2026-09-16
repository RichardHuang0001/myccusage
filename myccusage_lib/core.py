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

WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"]

_AGENT_LOCKS = {}
_AGENT_LOCKS_MUTEX = threading.Lock()

def get_agent_lock(agent_type):
    """获取指定 Agent 专用的互斥锁，避免同一 Agent 多个进程并发竞争本地 SQLite 数据库"""
    with _AGENT_LOCKS_MUTEX:
        if agent_type not in _AGENT_LOCKS:
            _AGENT_LOCKS[agent_type] = threading.Lock()
        return _AGENT_LOCKS[agent_type]

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
    """
    cny = (input_tokens * 2.0 + cache_read_tokens * 0.04 + total_output_tokens * 8.0) / 1_000_000
    return cny

def format_time(iso_str):
    if not iso_str:
        return "--"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00")).astimezone()
        return dt.strftime("%m-%d %H:%M")
    except Exception:
        return iso_str[:10]

# ==================== 标题与元数据提取模块 ====================

def get_agy_titles():
    """提取 Antigravity 会话标题"""
    titles = {}
    proto_path = os.path.expanduser("~/.gemini/antigravity/agyhub_summaries_proto.pb")
    if os.path.exists(proto_path):
        try:
            with open(proto_path, "rb") as f:
                data = f.read()
            pattern = re.compile(rb"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")
            matches = list(pattern.finditer(data))
            for i, m in enumerate(matches):
                uid = m.group(1).decode("ascii")
                start = m.end()
                end = matches[i+1].start() if i + 1 < len(matches) else len(data)
                slice_data = data[start:min(start+300, end)]
                text_matches = re.findall(rb"[\x20-\x7e\x80-\xff]{4,}", slice_data)
                for tm in text_matches:
                    try:
                        t = tm.decode("utf-8").strip().strip("\"'%,!\t ")
                        if (len(t) > 3 and not re.match(r"^[0-9a-f-]{36}$", t) 
                            and not t.startswith("outside") 
                            and not t.startswith("file://") 
                            and not t.startswith("git@")
                            and not t.startswith("main")
                            and not t.endswith("R")
                            and "/" not in t):
                            if uid not in titles:
                                titles[uid] = t
                                break
                    except Exception:
                        pass
        except Exception:
            pass

    logs_glob = os.path.expanduser("~/.gemini/antigravity/brain/*/.system_generated/logs/transcript.jsonl")
    for log_path in glob.glob(logs_glob):
        uid = log_path.split("/")[-4]
        if uid not in titles or titles[uid].endswith(":") or len(titles[uid]) < 4:
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    first_line = f.readline()
                    if first_line:
                        obj = json.loads(first_line)
                        content = obj.get("content", "")
                        if "<USER_REQUEST>" in content:
                            req = content.split("<USER_REQUEST>")[1].split("</USER_REQUEST>")[0].strip()
                        else:
                            req = content.strip()
                        first_line_clean = req.split("\n")[0][:60].strip()
                        if first_line_clean:
                            titles[uid] = first_line_clean
            except Exception:
                pass
    return titles

def get_claude_titles():
    """提取 Claude Code 会话标题与用户 Prompt"""
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

    for p in glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl")):
        sid = p.split("/")[-1].replace(".jsonl", "")
        if sid not in titles or titles[sid].startswith("/"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        obj = json.loads(line)
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
    """提取 Hermes 会话标题与结束时间"""
    titles = {}
    times = {}
    db_path = os.path.expanduser("~/.hermes/state.db")
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            for row in c.execute("SELECT id, started_at, ended_at, title FROM sessions"):
                sid, st, et, title = row
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
    """提取 OpenAI Codex 会话标题与用户 Prompt"""
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
        if not text:
            return ""
        if "## My request for Codex:" in text:
            text = text.split("## My request for Codex:")[-1].strip()
        text = re.sub(r"<[^>]+>", "", text).strip()
        return " ".join(text.split())

    session_files = glob.glob(os.path.expanduser("~/.codex/sessions/**/*.jsonl"), recursive=True)
    session_files += glob.glob(os.path.expanduser("~/.codex/archived_sessions/*.jsonl"))

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
        if title:
            titles[rel] = title
            titles[base] = title
            titles[uuid] = title

    return titles

def get_grok_titles():
    """提取 Grok 会话标题与用户 Prompt"""
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
    """提取 Pi Agent 会话用户 Prompt"""
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
    """提取 OpenCode 会话标题与最后活跃时间"""
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
    """提取 WorkBuddy 会话标题与最后活跃时间"""
    titles = {}
    times = {}
    wb_dir = os.path.expanduser("~/.workbuddy")
    db_path = os.path.join(wb_dir, "workbuddy.db")
    if os.path.exists(db_path):
        try:
            uri = f"file:{db_path}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=3.0)
            cur = conn.cursor()
            for row in cur.execute("SELECT id, title, custom_title, created_at, updated_at, last_activity_at FROM sessions"):
                sid, t, ct, ca, ua, la = row
                title = ct or t
                if title and title.strip():
                    titles[sid] = title.strip()
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

_WB_SCAN_LOCK = threading.Lock()
_WB_FILES_CACHE = {}  # fpath -> (mtime, size, list_of_records)

def scan_workbuddy_data():
    """
    高性能流式扫描 WorkBuddy 项目日志，返回 (daily_map, session_list)
    - daily_map: { "YYYY-MM-DD": [ {sessionId, totalTokens, inputTokens, cacheReadTokens, outputTokens, lastActivity}, ... ] }
    - session_list: [ {sessionId, totalTokens, inputTokens, cacheReadTokens, outputTokens, lastActivity}, ... ]
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
            if cached and cached[0] == mtime and cached[1] == size:
                records = cached[2]
            else:
                records = []
                sid = os.path.basename(fpath).replace(".jsonl", "")
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        for line in f:
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
                _WB_FILES_CACHE[fpath] = (mtime, size, records)

            for sid, date_str, iso_str, miss, hit, out, tot in records:
                # 每日切片
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

                # 全生命周期会话
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

    daily_res = {d: list(s_dict.values()) for d, s_dict in daily_map.items()}
    session_res = list(session_map.values())
    return daily_res, session_res

def get_agent_metadata(agent_type):
    """根据 agent 类型获取会话标题映射与时间修正映射"""
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
    if not sid:
        return "（未命名/系统会话）"
    if sid in titles:
        return titles[sid]
    parts = sid.split("-")
    if len(parts) >= 5:
        uuid = "-".join(parts[-5:])
        if uuid in titles:
            return titles[uuid]
    base = os.path.basename(sid)
    if base in titles:
        return titles[base]
    return "（未命名/系统会话）"

# ==================== 底层切片与缓存引擎 ====================

def check_ccusage_installed():
    """检查系统是否安装了底层 ccusage CLI 工具"""
    if not shutil.which("ccusage"):
        raise RuntimeError(
            "未检测到底层依赖 'ccusage' 命令行工具！\n\n"
            "myccusage 依赖开源的 ccusage CLI (Node.js) 获取底层会话切片。\n"
            "请在终端执行以下命令进行全局安装（二选一）：\n"
            "  ▶ 使用 npm 安装：  npm install -g ccusage\n"
            "  ▶ 或使用 bun 安装： bun add -g ccusage\n\n"
            "安装完成后重新运行当前命令即可。"
        )

def run_ccusage(args, capture_output=True, text=True, max_retries=3):
    """
    统一安全调用底层 ccusage CLI:
    - 优先追加 --offline 参数阻断冗余公网 LiteLLM 模型价格拉取 (提速 10x+)
    - 若遇到 database is locked 错误，支持毫秒级退避重试 (解决 SQLite 读写瞬态争抢)
    - 若旧版本不支持 --offline 则自动优雅降级回退执行
    """
    check_ccusage_installed()
    cmd = ["ccusage"] + list(args)
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

        # 检查是否为旧版本不识别 --offline
        if res.returncode != 0 and ("unknown" in stderr_lower or "unexpected" in stderr_lower):
            cmd_fallback = [arg for arg in cmd if arg != "--offline"]
            res = subprocess.run(cmd_fallback, capture_output=capture_output, text=text)

        return res

    return res

def fetch_single_day_sessions(ccusage_subcmd, date_str, times_override):
    """获取指定日期的精确切片会话消耗（不含历史前日累积）"""
    res = run_ccusage([ccusage_subcmd, "session", "-s", date_str, "-u", date_str, "--json"])
    if res.returncode != 0:
        # 失败时返回 None 而非 []，严格区分“提取错误”与“该日无数据”，防止缓存污染
        return None
    try:
        data = json.loads(res.stdout)
        sessions = data.get("sessions", [])
        for s in sessions:
            sid = s.get("sessionId")
            if not s.get("lastActivity") and sid in times_override:
                s["lastActivity"] = times_override[sid]
        return sessions
    except Exception:
        return None

def get_daily_data(agent_type, sort_by_tokens=False, force_refresh=False):
    """
    获取结构化的每日会话账本数据 (返回纯 dict/list，无终端控制台输出)
    """
    if agent_type != "workbuddy":
        check_ccusage_installed()
    if agent_type not in SUPPORTED_AGENTS:
        raise ValueError(f"未知 Agent 类型: {agent_type}")

    info = SUPPORTED_AGENTS[agent_type]
    display_name = info["name"]
    ccusage_subcmd = info["subcmd"]
    titles, times_override = get_agent_metadata(agent_type)

    agent_lock = get_agent_lock(agent_type)
    with agent_lock:
        today_str = datetime.now().strftime("%Y-%m-%d")

        if agent_type == "workbuddy":
            wb_daily_map, _ = scan_workbuddy_data()
            active_days = sorted(wb_daily_map.keys())
            daily_tokens_map = {d: sum(s["totalTokens"] for s in s_list) for d, s_list in wb_daily_map.items()}
        else:
            # 1. 获取活动日基准 (带 --offline 阻断网络挂起)
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

        # 2. 读取/写入本地缓存
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
        day_sessions_map = OrderedDict()

        if agent_type == "workbuddy":
            for d in active_days:
                if not force_refresh and d != today_str and d in cache and not (daily_tokens_map.get(d, 0) > 0 and len(cache.get(d, [])) == 0):
                    day_sessions_map[d] = cache[d]
                else:
                    s_list = wb_daily_map.get(d, [])
                    for s in s_list:
                        sid = s.get("sessionId")
                        if not s.get("lastActivity") and sid in times_override:
                            s["lastActivity"] = times_override[sid]
                    day_sessions_map[d] = s_list
                    if d != today_str:
                        cache[d] = s_list
                        cache_dirty = True
        else:
            # 识别缺失或先前被污染(有Token却被记录为空列表)的历史天数，顺序安全拉取修复
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
                    # 仅今日调用实时切片抓取
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

        # 日小计统计
        day_summary = {
            "date": d_str,
            "weekday": weekday_char,
            "totalTokens": day_total,
            "inputTokens": day_input,
            "cacheTokens": day_cache,
            "outputTokens": day_output,
            "costCny": round(day_cost, 2),
            "records": day_records,
            "count": len(day_records)
        }
        weeks_dict[week_key]["days"].append(day_summary)
        weeks_dict[week_key]["totalTokens"] += day_total
        weeks_dict[week_key]["inputTokens"] += day_input
        weeks_dict[week_key]["cacheTokens"] += day_cache
        weeks_dict[week_key]["outputTokens"] += day_output
        weeks_dict[week_key]["costCny"] += day_cost
        weeks_dict[week_key]["count"] += len(day_records)

        daily_trend.append({
            "date": d_str,
            "weekday": weekday_char,
            "totalTokens": day_total,
            "inputTokens": day_input,
            "cacheTokens": day_cache,
            "outputTokens": day_output,
            "costCny": round(day_cost, 2)
        })

        grand_total += day_total
        grand_input += day_input
        grand_cache += day_cache
        grand_output += day_output
        grand_cost += day_cost
        total_records += len(day_records)

    # 格式化周小计的 costCny
    weeks = list(weeks_dict.values())
    for w in weeks:
        w["costCny"] = round(w["costCny"], 2)

    if sort_by_tokens:
        flat_records.sort(key=lambda x: x.get("totalTokens", 0), reverse=True)
        # 重新为 flat_records 编号
        for i, r in enumerate(flat_records, 1):
            r["index"] = i

    hit_rate = round(grand_cache / max(1, grand_input + grand_cache) * 100, 2)

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
        "dailyTrend": daily_trend,
        "weeks": weeks,
        "flatRecords": flat_records
    }

def get_session_data(agent_type, sort_by_tokens=False, clean_args=None):
    """
    获取结构化的项目全生命周期总览数据 (返回纯 dict/list，无终端控制台输出)
    """
    if agent_type != "workbuddy":
        check_ccusage_installed()
    if agent_type not in SUPPORTED_AGENTS:
        raise ValueError(f"未知 Agent 类型: {agent_type}")

    info = SUPPORTED_AGENTS[agent_type]
    display_name = info["name"]
    ccusage_subcmd = info["subcmd"]
    titles, times_override = get_agent_metadata(agent_type)

    agent_lock = get_agent_lock(agent_type)
    with agent_lock:
        if agent_type == "workbuddy":
            _, raw_sessions = scan_workbuddy_data()
        else:
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

        # 分周与分日聚合
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

def get_all_agents_summary():
    """汇总所有支持的 Agent 的用量与概览，支持 Web 端全局看板 (多线程并发调度极速版)"""
    agents_summary = []
    grand_tokens = 0
    grand_input = 0
    grand_cache = 0
    grand_output = 0
    grand_cost = 0.0
    grand_sessions = 0

    def _fetch_single_agent(agent_id, agent_meta):
        try:
            data = get_daily_data(agent_id)
            sum_info = data["summary"]
            rec_cnt = data["totalRecordsCount"]
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
                "cacheHitRate": sum_info.get("cacheHitRate", 0.0)
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
                "cacheHitRate": 0.0
            }

    agent_ids = list(SUPPORTED_AGENTS.keys())
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(agent_ids)) as pool:
        future_map = {
            pool.submit(_fetch_single_agent, aid, SUPPORTED_AGENTS[aid]): aid
            for aid in agent_ids
        }
        results_by_id = {}
        for fut in concurrent.futures.as_completed(future_map):
            aid = future_map[fut]
            results_by_id[aid] = fut.result()

    # 严格保持 SUPPORTED_AGENTS 初始定义的排列顺序
    for aid in agent_ids:
        item = results_by_id[aid]
        agents_summary.append(item)
        grand_tokens += item["totalTokens"]
        grand_input += item["inputTokens"]
        grand_cache += item["cacheTokens"]
        grand_output += item["outputTokens"]
        grand_cost += item["costCny"]
        grand_sessions += item["recordsCount"]

    grand_hit_rate = round(grand_cache / max(1, grand_input + grand_cache) * 100, 2)

    return {
        "grandSummary": {
            "totalTokens": grand_tokens,
            "inputTokens": grand_input,
            "cacheTokens": grand_cache,
            "outputTokens": grand_output,
            "costCny": round(grand_cost, 2),
            "costUsd": round(grand_cost / 7.2, 2),
            "totalSessions": grand_sessions,
            "cacheHitRate": grand_hit_rate
        },
        "agents": agents_summary
    }
