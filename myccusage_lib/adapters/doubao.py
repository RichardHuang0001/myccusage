"""myccusage_lib.adapters.doubao:
豆包工作（Doubao Work）适配器 —— 读取自有固化账本，走既有聚合管线。

与采集引擎（doubao_capture.py）彻底解耦：采集负责"抢救数据进账本"，
本适配器只读账本（doubao_journal.jsonl）+ 工作区元数据兜底标题，
产出标准 8 元组交给 base._accumulate_records，复用既有缓存/聚合/图表/模型维度。

口径（已审批，见 docs/豆包工作统计适配架构与施工计划.md §2.3）：
  inp = 上下文窗口占用（system_prompt+messages+skills+tools），输入侧参考量；
  cr/out = 0（本地不可得，进 gaps 诚实声明，非真实为 0）；
  model = UNKNOWN_MODEL（本地仅数字 model_id，无名称映射）。
"""

from __future__ import annotations

import os
import glob
import json
from datetime import datetime

from .base import (
    BaseAgentAdapter,
    UNKNOWN_MODEL,
    ms_to_iso,
    ms_to_date_str,
)
from . import doubao_capture as DC


class DoubaoAdapter(BaseAgentAdapter):
    agent_id = "doubao"
    display_name = "豆包工作"

    def __init__(self):
        super().__init__()
        # 账本解析缓存：(mtime_ns, size, (usage_list, meta_map))
        self._journal_cache = (None, None, None)

    # ------------------------------------------------------------------
    def _data_root(self) -> str:
        return os.path.expanduser("~/Library/Application Support/Doubao")

    def is_available(self) -> bool:
        # 豆包数据根存在，或已有固化账本（即使豆包卸载仍可查看历史）
        return os.path.isdir(self._data_root()) or os.path.exists(DC.JOURNAL)

    def get_source_fingerprint(self) -> str:
        parts = []
        for p in (DC.JOURNAL, DC.STATE):
            try:
                st = os.stat(p)
                parts.append(f"{st.st_size}:{st.st_mtime_ns}")
            except OSError:
                parts.append("0")
        return "|".join(parts)

    # ------------------------------------------------------------------
    def _load_journal(self):
        """解析账本：usage 取每 message_id 最大快照，meta 取每会话最新。按 mtime/size 缓存。"""
        try:
            st = os.stat(DC.JOURNAL)
            key = (st.st_mtime_ns, st.st_size)
        except OSError:
            return [], {}
        if self._journal_cache[0] == key[0] and self._journal_cache[1] == key[1]:
            return self._journal_cache[2]

        usage: dict = {}
        meta: dict = {}
        try:
            with open(DC.JOURNAL, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    if obj.get("type") == "usage":
                        mid = obj.get("message_id")
                        if not mid:
                            continue
                        prev = usage.get(mid)
                        if prev is None or obj.get("context_total", 0) > prev.get("context_total", 0):
                            usage[mid] = obj
                    elif obj.get("type") == "meta":
                        cid = obj.get("conversation_id")
                        if cid:
                            meta[cid] = obj
        except Exception:
            pass
        result = (list(usage.values()), meta)
        self._journal_cache = (key[0], key[1], result)
        return result

    def _workspace_title(self, sid: str) -> str:
        """工作区 board.md 兜底标题（仅对账本中出现的 sid 按需读取，有界）。"""
        if not sid:
            return ""
        base = self._data_root()
        for prof in glob.glob(os.path.join(base, "Profile *")) + [os.path.join(base, "Default")]:
            board = os.path.join(prof, ".doubao", "agent_mode", "workspace", ".sessions", sid, "board.md")
            if not os.path.exists(board):
                continue
            try:
                with open(board, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line.startswith("|"):
                            continue
                        cells = [c.strip() for c in line.strip("|").split("|")]
                        if len(cells) < 2:
                            continue
                        title = cells[1]
                        if title and title not in ("Organizer 标题", "---") and not set(title) <= {"-", " "}:
                            return " ".join(title.split())[:60]
            except Exception:
                pass
        return ""

    # ------------------------------------------------------------------
    def get_titles_and_times(self) -> tuple[dict[str, str], dict[str, str]]:
        usage, meta = self._load_journal()
        titles: dict = {}
        times: dict = {}
        for cid, m in meta.items():
            if m.get("name"):
                titles[cid] = m["name"]
        sids = {r.get("conversation_id") for r in usage if r.get("conversation_id")}
        for sid in sids:
            if sid and sid not in titles:
                t = self._workspace_title(sid)
                if t:
                    titles[sid] = t
        for r in usage:
            sid = r.get("conversation_id")
            ts = r.get("create_time_ms")
            if sid and ts:
                iso = ms_to_iso(ts)
                if iso > times.get(sid, ""):
                    times[sid] = iso
        return titles, times

    def fetch_data(self, today_only: bool = False) -> tuple[dict[str, list[dict]], list[dict]]:
        if not self.is_available():
            return {}, []
        fp = self.get_source_fingerprint()
        cached = self._cached_full_result(fp, today_only)
        if cached is not None:
            return cached

        usage, _meta = self._load_journal()
        today_str = datetime.now().strftime("%Y-%m-%d")
        records = []
        for r in usage:
            ts = r.get("create_time_ms") or r.get("captured_at")
            if not ts:
                continue
            inp = int(r.get("context_total", 0) or 0)
            if inp <= 0:
                continue
            date_str = ms_to_date_str(ts)
            if today_only and date_str != today_str:
                continue
            sid = r.get("conversation_id") or r.get("message_id")
            records.append((sid, date_str, ms_to_iso(ts), inp, 0, 0, inp, UNKNOWN_MODEL))

        daily, session = self._accumulate_records(records)
        self._store_full_result(fp, daily, session, today_only)
        return daily, session

    # ------------------------------------------------------------------
    def get_insights(self) -> dict:
        """豆包专属深度概览：上下文构成 + 覆盖窗口 + 模型 id 分布 + 诚实 gaps。

        数据全部来自 _load_journal 已解析内容，不新增文件扫描（契约 3.1.1）。
        kind='capture' 供前端走豆包专属渲染分支（区别于 dsh 的 TPS/TTFT 视图）。
        """
        if not self.is_available():
            return {"available": False, "gaps": []}
        usage, meta = self._load_journal()

        comp = {"system_prompt": 0, "messages": 0, "skills": 0, "tools": 0}
        total_ctx = 0
        model_ids: dict = {}
        by_conv: dict = {}
        since = until = None
        ctx_window = 0
        for r in usage:
            for k in comp:
                comp[k] += int(r.get(k, 0) or 0)
            total_ctx += int(r.get("context_total", 0) or 0)
            ctx_window = max(ctx_window, int(r.get("total_window_size", 0) or 0))
            mid = r.get("model_id")
            if mid:
                model_ids[mid] = model_ids.get(mid, 0) + 1
            ts = r.get("create_time_ms")
            if ts:
                since = ts if since is None else min(since, ts)
                until = ts if until is None else max(until, ts)
            cid = r.get("conversation_id")
            if cid:
                c = by_conv.setdefault(cid, {"rounds": 0, "context": 0, "last": 0})
                c["rounds"] += 1
                c["context"] += int(r.get("context_total", 0) or 0)
                if ts and ts > c["last"]:
                    c["last"] = ts

        sessions = []
        for cid, c in sorted(by_conv.items(), key=lambda x: -x[1]["context"]):
            sessions.append({
                "sessionId": cid,
                "title": (meta.get(cid, {}) or {}).get("name") or self._workspace_title(cid) or cid,
                "rounds": c["rounds"],
                "totalTokens": c["context"],
                "lastActivity": ms_to_iso(c["last"]),
            })

        return {
            "available": True,
            "kind": "capture",
            "backend": "idbcodec (WAL/SSTable + Snappy)",
            "contextWindow": ctx_window,
            "totals": {
                "sessions": len(by_conv),
                "rounds": len(usage),
                "calls": len(usage),
                "totalTokens": total_ctx,
            },
            "contextComposition": comp,
            "modelIds": [{"id": k, "calls": v} for k, v in sorted(model_ids.items(), key=lambda x: -x[1])],
            "coverageSince": since,
            "coverageUntil": until,
            "sessions": sessions,
            "gaps": [
                "Token 口径为上下文窗口占用快照（system_prompt+messages+skills+tools），是输入侧参考量，非计费 prompt_tokens。",
                "输出 Token（completion）与缓存命中（cache_read）本地不持久化、无法获取；账本中记 0 并非真实为 0。",
                "模型仅有数字 model_id（如 38），本地无名称映射，统一归入 unknown；原始 id 分布见上方。",
                "仅统计采集开关开启期间固化的轮次；关闭或程序坞/网页均未运行时段的数据已永久丢失，不可追回。",
                "费用为按当前计价模型的等效折算，非真实账单。",
            ],
        }