"""
myccusage_lib.adapters.codex:
OpenAI Codex 原生适配器:
- 读取 ~/.codex/session_index.jsonl 提取标题
- 流式解析 ~/.codex/sessions/**/*.jsonl 与 archived_sessions/*.jsonl
- 捕获 payload.type == "token_count" 获取各轮增量与会话大计
"""

from __future__ import annotations

import os
import glob
import json
import re
from datetime import datetime, timezone
from .base import BaseAgentAdapter

class CodexAdapter(BaseAgentAdapter):
    """OpenAI Codex 的本地日志数据适配器"""
    agent_id = "codex"
    display_name = "OpenAI Codex"
    has_times = False

    def __init__(self):
        """初始化目录结构"""
        super().__init__()
        self.base_dir = os.path.expanduser("~/.codex")
        self.sessions_dir = os.path.join(self.base_dir, "sessions")

    def is_available(self) -> bool:
        """检查 codex 配置目录是否存在"""
        return os.path.exists(self.base_dir)

    def get_titles_and_times(self) -> tuple[dict[str, str], dict[str, str]]:
        """从 session_index.jsonl 和会话文件中提取标题和时间"""
        titles = {}
        times = {}
        if not self.is_available():
            return titles, times

        index_map = {}
        index_file = os.path.join(self.base_dir, "session_index.jsonl")
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
            """内部辅助方法：提取 Codex prompt 文本"""
            if not text:
                return ""
            if "## My request for Codex:" in text:
                text = text.split("## My request for Codex:")[-1].strip()
            text = re.sub(r"<[^>]+>", "", text).strip()
            return " ".join(text.split())

        session_files = glob.glob(os.path.join(self.sessions_dir, "**/*.jsonl"), recursive=True)
        session_files += glob.glob(os.path.join(self.base_dir, "archived_sessions/*.jsonl"))

        for p in session_files:
            rel = p.replace(self.sessions_dir + "/", "").replace(".jsonl", "")
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
                titles[rel] = title[:60]
                titles[base] = title[:60]
                titles[uuid] = title[:60]

        return titles, times

    def fetch_data(self) -> tuple[dict[str, list[dict]], list[dict]]:
        """
        提取 Codex 消耗数据。
        通过捕获 token_count 的累计增量进行差分计算。
        """
        if not self.is_available():
            return {}, []

        daily_map = {}
        session_map = {}

        session_files = glob.glob(os.path.join(self.sessions_dir, "**/*.jsonl"), recursive=True)
        session_files += glob.glob(os.path.join(self.base_dir, "archived_sessions/*.jsonl"))

        with self._lock:
            for fpath in session_files:
                try:
                    stat = os.stat(fpath)
                except OSError:
                    continue

                mtime, size = stat.st_mtime, stat.st_size
                cached = self._file_cache.get(fpath)
                # 使用 mtime 和 size 作为判断条件，避免重复解析已处理过的日志
                if cached and cached[0] == mtime and cached[1] == size:
                    records = cached[2]
                else:
                    records = []
                    rel = fpath.replace(self.sessions_dir + "/", "").replace(".jsonl", "")
                    base = os.path.basename(fpath).replace(".jsonl", "")
                    parts = base.split("-")
                    uuid = "-".join(parts[-5:]) if len(parts) >= 5 else base
                    sid = rel

                    prev_raw_inp = 0
                    prev_cached = 0
                    prev_out = 0

                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            for line in f:
                                if "total_token_usage" not in line:
                                    continue
                                try:
                                    obj = json.loads(line)
                                except Exception:
                                    continue
                                pl = obj.get("payload") or {}
                                info = pl.get("info") or {}
                                tot = info.get("total_token_usage")
                                if not tot:
                                    continue

                                ts_str = obj.get("timestamp") or ""
                                if ts_str:
                                    try:
                                        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                                        date_str = dt.astimezone().strftime("%Y-%m-%d")
                                        iso_str = dt.astimezone(timezone.utc).isoformat()
                                    except Exception:
                                        date_str = "1970-01-01"
                                        iso_str = ts_str
                                else:
                                    date_str = "1970-01-01"
                                    iso_str = ""

                                cur_raw_inp = tot.get("input_tokens", 0)
                                cur_cached = tot.get("cached_input_tokens", 0)
                                cur_out = tot.get("output_tokens", 0)

                                # 计算累计增量差分
                                delta_raw_inp = max(0, cur_raw_inp - prev_raw_inp)
                                delta_cached = max(0, cur_cached - prev_cached)
                                delta_out = max(0, cur_out - prev_out)

                                delta_inp = max(0, delta_raw_inp - delta_cached)
                                delta_tot = delta_inp + delta_cached + delta_out

                                if delta_tot > 0:
                                    records.append((sid, date_str, iso_str, delta_inp, delta_cached, delta_out, delta_tot))
                                    prev_raw_inp = cur_raw_inp
                                    prev_cached = cur_cached
                                    prev_out = cur_out
                    except Exception:
                        pass
                    # 将提取到的增量记录计入防抖缓存
                    self._file_cache[fpath] = (mtime, size, records)

                for sid, date_str, iso_str, delta_inp, delta_cached, delta_out, delta_tot in records:
                    # 每日切片数据聚合
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
                    ds["inputTokens"] += delta_inp
                    ds["cacheReadTokens"] += delta_cached
                    ds["outputTokens"] += delta_out
                    ds["totalTokens"] += delta_tot
                    if iso_str > ds["lastActivity"]:
                        ds["lastActivity"] = iso_str

                    # 项目生命周期汇总 (全生命周期累加计算)
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
                    ss["inputTokens"] += delta_inp
                    ss["cacheReadTokens"] += delta_cached
                    ss["outputTokens"] += delta_out
                    ss["totalTokens"] += delta_tot
                    if iso_str > ss["lastActivity"]:
                        ss["lastActivity"] = iso_str

        daily_res = {d: list(s_dict.values()) for d, s_dict in daily_map.items()}
        session_res = list(session_map.values())
        return daily_res, session_res
