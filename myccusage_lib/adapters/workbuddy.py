"""
myccusage_lib.adapters.workbuddy:
WorkBuddy (腾讯旗下 AI 编程 Agent) 原生适配器:
- 读取 ~/.workbuddy/workbuddy.db (SQLite 只读模式) 获取会话元数据
- 流式解析 ~/.workbuddy/projects/*/*.jsonl (带 mtime 增量缓存)
"""

from __future__ import annotations

import os
import glob
import json
import sqlite3
from .base import BaseAgentAdapter, ms_to_iso, ms_to_date_str, scan_files_fast, get_candidate_home_dirs, normalize_model_name

class WorkBuddyAdapter(BaseAgentAdapter):
    """WorkBuddy 适配器，结合 SQLite 的元数据与 JSONL 日志文件的用量数据进行分析"""
    agent_id = "workbuddy"
    display_name = "WorkBuddy"

    def __init__(self):
        """初始化 WorkBuddy 基础配置路径，支持跨环境多根探测"""
        super().__init__()
        self.base_dirs = [
            os.path.join(h, ".workbuddy")
            for h in get_candidate_home_dirs()
            if os.path.exists(os.path.join(h, ".workbuddy"))
        ]
        if not self.base_dirs:
            self.base_dirs = [os.path.expanduser("~/.workbuddy")]
        self.base_dir = self.base_dirs[0]
        self.db_paths = [
            os.path.join(b, "workbuddy.db")
            for b in self.base_dirs
            if os.path.exists(os.path.join(b, "workbuddy.db"))
        ]
        self.db_path = self.db_paths[0] if self.db_paths else os.path.join(self.base_dir, "workbuddy.db")

    def is_available(self) -> bool:
        """检查 WorkBuddy 目录是否存在"""
        return any(os.path.exists(b) for b in self.base_dirs)

    def get_titles_and_times(self) -> tuple[dict[str, str], dict[str, str]]:
        """从 SQLite 数据库或通过回退策略扫描日志提取对话的标题及时间戳"""
        titles = {}
        times = {}
        for db in self.db_paths:
            try:
                uri = f"file:{db}?mode=ro"
                conn = sqlite3.connect(uri, uri=True, timeout=3.0)
                cur = conn.cursor()
                for row in cur.execute("SELECT id, title, custom_title, created_at, updated_at, last_activity_at FROM sessions"):
                    sid, t, ct, ca, ua, la = row
                    title = ct or t
                    if title and title.strip():
                        titles[sid] = title.strip()
                    ts = la or ua or ca
                    if ts:
                        times[sid] = ms_to_iso(ts)
                conn.close()
            except Exception:
                pass

        # 兜底补充扫描 projects 目录中未记录在 DB 或 custom-title 的会话
        for b in self.base_dirs:
            project_files = glob.glob(os.path.join(b, "projects/*/*.jsonl"))
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

    def _get_session_metas(self) -> dict[str, tuple[str, str]]:
        """
        获取各会话的元数据 (cwd, title)，用于精准识别跨账号会话克隆。
        优先读取 SQLite 数据库 (< 1ms)，若不可用由 get_titles_and_times 兜底。
        """
        metas: dict[str, tuple[str, str]] = {}
        for db in self.db_paths:
            try:
                uri = f"file:{db}?mode=ro"
                conn = sqlite3.connect(uri, uri=True, timeout=3.0)
                cur = conn.cursor()
                for row in cur.execute("SELECT id, cwd, coalesce(custom_title, title) FROM sessions"):
                    sid, cwd, title = row
                    metas[sid] = (cwd or "", (title or "").strip())
                conn.close()
            except Exception:
                pass

        if not metas:
            titles, _ = self.get_titles_and_times()
            metas = {sid: ("", title) for sid, title in titles.items()}
        return metas

    def _merge_and_dedup_records(self, all_records: list) -> list:
        """
        高性能、零误伤合并通过第三方工具跨账号链接/复制的会话，并消除重复计入的 Token 与积分：
        1. 候选门禁：属于同一工程目录 (cwd) 且具有相同非空业务标题 (len >= 2)
        2. 物理铁证：调用时间戳集合具有非空交集（毫秒级 timestamp 相同证明系同一上下文继承克隆）
        3. 连通分支：采用并查集 (Union-Find) 聚合并选择最新活跃者作为规范会话 ID (canonical_sid)
        4. 记录去重：按 (canonical_sid, iso_str) 进行单会话内调用级去重，消除历史重合调用的重复累加
        """
        if not all_records:
            return all_records

        metas = self._get_session_metas()
        if not metas:
            return all_records

        # 统计每个 sid 的所有调用时间戳集合与最新调用时间
        sid_calls_map: dict[str, set[str]] = {}
        sid_last_call: dict[str, str] = {}
        for rec in all_records:
            sid = rec[0]
            iso = rec[2]
            if sid not in sid_calls_map:
                sid_calls_map[sid] = set()
            sid_calls_map[sid].add(iso)
            if sid not in sid_last_call or iso > sid_last_call[sid]:
                sid_last_call[sid] = iso

        # 并查集：按 (cwd, title) 候选分组并在存在重叠时间戳时联通
        parent: dict[str, str] = {}

        def find(x: str) -> str:
            if parent.setdefault(x, x) != x:
                parent[x] = find(parent[x])
            return parent[x]

        def union(x: str, y: str) -> None:
            rx, ry = find(x), find(y)
            if rx != ry:
                parent[rx] = ry

        cand_groups: dict[tuple[str, str], list[str]] = {}
        for sid in sid_calls_map:
            m = metas.get(sid)
            if not m or not m[1] or len(m[1]) < 2:
                continue
            cand_groups.setdefault(m, []).append(sid)

        has_link = False
        for m, sids in cand_groups.items():
            if len(sids) > 1:
                for i in range(len(sids)):
                    for j in range(i + 1, len(sids)):
                        s1, s2 = sids[i], sids[j]
                        if sid_calls_map[s1] & sid_calls_map[s2]:
                            union(s1, s2)
                            has_link = True

        if not has_link:
            return all_records

        # 聚合成连通分支，并选举最新活跃者作为 canonical_sid
        components: dict[str, list[str]] = {}
        for sid in sid_calls_map:
            root = find(sid)
            components.setdefault(root, []).append(sid)

        canonical_map: dict[str, str] = {}
        for root, members in components.items():
            if len(members) > 1:
                canon = max(members, key=lambda s: (sid_last_call.get(s, ""), s))
                for m in members:
                    canonical_map[m] = canon

        if not canonical_map:
            return all_records

        # 单会话内按 (canonical_sid, iso_str) 进行调用级幂等去重
        seen_calls: set[tuple[str, str]] = set()
        deduped: list = []
        for rec in all_records:
            sid = rec[0]
            c_sid = canonical_map.get(sid, sid)
            iso = rec[2]
            call_key = (c_sid, iso)
            if call_key in seen_calls:
                continue
            seen_calls.add(call_key)
            if c_sid != sid:
                rec = (c_sid,) + tuple(rec[1:])
            deduped.append(rec)

        return deduped

    def get_source_fingerprint(self) -> str:
        """极速获取 WorkBuddy 目录修改状态指纹 (< 1ms)"""
        if not self.is_available():
            return ""
        parts = []
        for db in self.db_paths:
            try:
                st = os.stat(db)
                parts.append(f"{st.st_mtime_ns}:{st.st_size}")
            except OSError:
                pass
        dirs = []
        for b in self.base_dirs:
            p_dir = os.path.join(b, "projects")
            s_dir = os.path.join(b, "sessions")
            if os.path.isdir(p_dir):
                dirs.append(p_dir)
            if os.path.isdir(s_dir):
                dirs.append(s_dir)
        hot = scan_files_fast(dirs, extensions=(".jsonl",), recursive=True, today_only=True)
        parts.append(str(len(hot)))
        max_m = 0
        for h in hot:
            try:
                mt = os.path.getmtime(h)
                if mt > max_m:
                    max_m = mt
            except OSError:
                pass
        parts.append(str(max_m))
        return "|".join(parts)

    def fetch_data(self, today_only: bool = False) -> tuple[dict[str, list[dict]], list[dict]]:
        """
        解析 WorkBuddy 的 jsonl 文件提取消耗数据。
        支持特殊数据格式，如 rawUsage vs usage 的平滑兼容。
        - 支持 today_only: 仅扫描今日活跃文件 (提速 50x)
        """
        if not self.is_available():
            return {}, []

        fp = self.get_source_fingerprint()

        cached = self._cached_full_result(fp, today_only)
        if cached is not None:
            return cached

        dirs = []
        for b in self.base_dirs:
            p_dir = os.path.join(b, "projects")
            s_dir = os.path.join(b, "sessions")
            if os.path.isdir(p_dir):
                dirs.append(p_dir)
            if os.path.isdir(s_dir):
                dirs.append(s_dir)
        files = scan_files_fast(dirs, extensions=(".jsonl",), recursive=True, today_only=today_only)

        all_records = []

        with self._lock:
            if not self._file_cache:
                self._load_persisted_file_cache()
            cache_modified = False

            for fpath in files:
                try:
                    stat = os.stat(fpath)
                except OSError:
                    continue

                mtime, size = stat.st_mtime, stat.st_size
                cached = self._file_cache.get(fpath)

                # 使用 mtime 和 size 的防抖缓存，避免每次全量解析所有 jsonl
                if cached and cached[0] == mtime and cached[1] == size:
                    records = cached[2]
                else:
                    records = []
                    sid = os.path.basename(fpath).replace(".jsonl", "")
                    anchor_ts: int | None = None
                    next_anchor: int | None = None
                    active_call_ids: set[str] = set()
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            for line in f:
                                # 极速字符串预过滤：跳过不含关键事件标记的绝大多数无关行
                                if not line.strip() or (
                                    "user" not in line
                                    and "function_call" not in line
                                    and "usage" not in line
                                    and "rawUsage" not in line
                                ):
                                    continue
                                try:
                                    obj = json.loads(line)
                                except Exception:
                                    continue

                                t = obj.get("type")
                                role = obj.get("role")
                                ts = obj.get("timestamp")
                                if not ts:
                                    continue

                                pd = obj.get("providerData") or {}
                                ru = pd.get("rawUsage")
                                u = pd.get("usage")
                                if not u:
                                    msg = obj.get("message")
                                    if isinstance(msg, dict):
                                        u = msg.get("usage")

                                # 1) 用户 Prompt 输入：重置并设立新一轮模型推理的绝对时间锚点
                                if (t == "message" and role == "user") or t == "user":
                                    anchor_ts = ts
                                    next_anchor = None
                                    active_call_ids.clear()
                                    continue

                                # 2) 跟踪当前轮次模型发起的工具调用 ID
                                if t == "function_call":
                                    cid = obj.get("callId")
                                    if cid:
                                        active_call_ids.add(cid)

                                # 3) 工具执行完成：作为下一轮模型推理的时间锚点
                                if t == "function_call_result":
                                    cid = obj.get("callId")
                                    if (cid and cid in active_call_ids) or (not cid and active_call_ids):
                                        # 本轮模型推理流式输出过程中提前完成的并发工具（如极速文件读取），
                                        # 归属于下一轮的起点，避免污染本轮尚在进行的生成时间
                                        next_anchor = max(next_anchor or 0, ts)
                                    else:
                                        # 上一轮工具调用批次正常执行完成，以最晚完成的工具时间作为下一轮起点
                                        anchor_ts = max(anchor_ts or 0, ts)
                                    continue

                                if not ru and not u:
                                    continue

                                # 4) 模型生成完成：计算纯推理净耗时 (毫秒)
                                model_ms = 0
                                if anchor_ts is not None and ts >= anchor_ts:
                                    delta = ts - anchor_ts
                                    # 防并发竞态：过滤并行 tool call 或极速回显引起的 <100ms 异常尖峰
                                    if delta >= 100:
                                        model_ms = delta

                                # 轮次交接：重置当前轮次工具 ID，并承接本轮生成的工具完成起点
                                anchor_ts = next_anchor
                                next_anchor = None
                                active_call_ids.clear()

                                date_str = ms_to_date_str(ts)
                                iso_str = ms_to_iso(ts)

                                # 兼容 rawUsage 与 usage 两种特殊数据格式并提取官方积分
                                credit = 0.0
                                if ru:
                                    hit = ru.get("prompt_cache_hit_tokens", 0)
                                    miss = ru.get("prompt_cache_miss_tokens", 0)
                                    out = ru.get("completion_tokens", 0)
                                    c_val = ru.get("credit")
                                    if c_val is not None:
                                        try:
                                            credit = float(c_val)
                                        except (ValueError, TypeError):
                                            credit = 0.0
                                else:
                                    if "input_tokens" in u:
                                        inp = u.get("input_tokens", 0)
                                        hit = u.get("cache_read_input_tokens", 0)
                                        miss = max(0, inp - hit)
                                        out = u.get("output_tokens", 0)
                                    else:
                                        inp = u.get("inputTokens", 0)
                                        hit = sum(d.get("cached_tokens", 0) for d in u.get("inputTokensDetails", []))
                                        miss = max(0, inp - hit)
                                        out = u.get("outputTokens", 0)
                                tot = hit + miss + out
                                model = normalize_model_name(pd.get("requestModelName") or pd.get("requestModelId") or pd.get("model"))
                                records.append((sid, date_str, iso_str, miss, hit, out, tot, model, credit, model_ms))
                    except Exception:
                        records = cached[2] if cached else []
                    else:
                        self._file_cache[fpath] = (mtime, size, records)
                        cache_modified = True

                all_records.extend(records)

            if cache_modified and not today_only:
                self._save_persisted_file_cache()

        deduped_records = self._merge_and_dedup_records(all_records)
        daily_res, session_res = self._accumulate_records(deduped_records)
        self._store_full_result(fp, daily_res, session_res, today_only)
        return daily_res, session_res

