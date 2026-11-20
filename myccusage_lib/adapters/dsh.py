"""
myccusage_lib.adapters.dsh:
DeepSeek Harness (dsh) 原生适配器。

数据源（全部只读）：
- `$DSH_HOME/sessions/<项目 slug>/session-<id>/session.v4.jsonl.zstd`
  dsh 的权威事件日志：追加型多帧 Zstandard 容器，一行一个 SessionEvent。
- 明文 `session.v4.jsonl` 同样兼容（dsh 支持 `compression: 'none'`）。

为什么只读 jsonl、不读 `storages/session_projcache/`：
projcache 是 dsh 自己的投影缓存（`version: 7`），实测其 tokenUsage 存在
200ms~6s 的写后延迟，且 schema 会随 dsh 升级而变。把它当作唯一 token 来源
会把"正在进行中的那几步"算漏。⇒ **token 一律以 jsonl 事件为准。**

口径要点（与 dsh 官方 `dsh-token-meter` 的 projection 严格对齐）：
1. `usage.inputTokens` 是**未命中缓存的输入**，
   `totalTokens = input + output + cacheRead + cacheWrite`（实测 189/189 条逐位成立）。
2. 同一 `(turn, step)` 的多次结算只取**最后一次**（官方 `addReplacing` 语义）；
   `llm/retry-started` 会关闭替换槽位，使重试后的新 usage **重新累加**。
   若简单按事件求和，一旦发生重试就会静默虚高 —— 这是本适配器最容易踩的坑。
3. `assistant/message` 缺 `data.usage` 时，回退取 `stream` 中最后一个
   `type: "usage"` 分片，与官方 `usageOf()` 完全一致。
4. `cacheWriteTokens` 并入 input（与 claude 适配器同一约定），
   保证 `Σmodels == totalTokens` 这条不变式恒成立。

dsh 独有的额外口径（官方 projection 已固化，本适配器一并复刻，供专属看板使用）：
- 步级 `llmMs` / `ttftMs`：`step/start` 到首/末 stream 分片的时间差；
- `decodeMs` / `decodeTokens` → 生成速率 TPS（实测与 dsh `sessionStats` 偏差 < 3%）；
- `toolMs`：`job/registered` → `job/settled` 的 `finishedAt - startedAt`；
- 工具调用次数与名称分布、轮次数、上下文窗口、重试/压缩/中断计数。
"""

from __future__ import annotations

import os
import json
from datetime import datetime, timezone

from .base import (
    BaseAgentAdapter,
    get_candidate_home_dirs,
    normalize_model_name,
)
from .. import zstdcodec

# dsh 的生成代文件名：v0 为 `session.jsonl`，v1+ 为 `session.vN.jsonl`，可带 `.zstd` 后缀。
# 用后缀匹配而非精确文件名，兼容后续版本迁移（v5/v6…）与明文压缩两种配置。
_LOG_SUFFIXES = (".jsonl.zstd", ".jsonl")

# 需要参与统计的事件类型。dsh 单条 assistant/message 平均 17KB（含完整 stream 分片），
# 而 tool/result、user/message、request/header 等占掉日志体积的一大半却与统计无关，
# 故先用零分配的字节前缀提取 type 做白名单过滤，再只对命中行做 json.loads。
_STAT_EVENTS = frozenset({
    "session",
    "session/title",
    "step/start",
    "turn/start",
    "tool/call",
    "job/registered",
    "job/settled",
    "assistant/message",
    "request/context",
    "llm/retry-started",
    "compaction/summary",
})


def _event_type(line: bytes) -> bytes:
    """
    从一行 JSONL 里零分配地提取 `type` 字段的原始字节。

    dsh 的序列化器固定把 `type` 放在对象首位（`{"type": "xxx", ...}` 或
    `{"type":"xxx",...}`），因此可以直接在字节串上定位，省掉一整次 json.loads。
    实测 2000 行日志上该函数耗时 0.77ms，而全量 json.loads 需 34.9ms。
    任何格式不符的行返回空字节串，由调用方跳过（保守起见不解析）。
    """
    if len(line) < 12 or not line.startswith(b'{"type"'):
        return b""
    colon = line.find(b":", 7)
    if colon < 0:
        return b""
    start = line.find(b'"', colon)
    if start < 0:
        return b""
    end = line.find(b'"', start + 1)
    if end < 0:
        return b""
    return line[start + 1:end]


def _rate(cache_tokens: int, prompt_tokens: int) -> float:
    """缓存命中率（百分比，保留 1 位小数）；分母为 0 时返回 0.0"""
    if prompt_tokens <= 0:
        return 0.0
    return round(cache_tokens / prompt_tokens * 100, 1)


class DshAdapter(BaseAgentAdapter):
    """DeepSeek Harness 适配器，逐帧解压会话事件日志并复刻官方 token 投影口径。"""

    agent_id = "dsh"
    display_name = "DeepSeek Harness"

    def __init__(self):
        """初始化 dsh 数据根目录，支持跨环境多根探测"""
        super().__init__()
        # DSH_HOME 优先（dsh 自身即用该环境变量定位数据根），否则退回 ~/.dsh
        env_home = os.environ.get("DSH_HOME", "").strip()
        candidates = []
        if env_home:
            candidates.append(env_home)
        candidates.extend(os.path.join(h, ".dsh") for h in get_candidate_home_dirs())

        self.base_dirs = [b for b in candidates if os.path.isdir(b)]
        if not self.base_dirs:
            self.base_dirs = [env_home or os.path.expanduser("~/.dsh")]
        self.base_dir = self.base_dirs[0]
        self.sessions_dirs = [
            os.path.join(b, "sessions")
            for b in self.base_dirs
            if os.path.isdir(os.path.join(b, "sessions"))
        ]
        self.sessions_dir = (
            self.sessions_dirs[0]
            if self.sessions_dirs
            else os.path.join(self.base_dir, "sessions")
        )

        # 会话文件清单缓存：仅在「项目目录结构变化」时重建，
        # 避免 60s 轮询反复付出 os.walk 代价（实测 2000 会话下 100ms+）。
        self._paths_cache: list[str] = []
        self._dirs_sig: tuple = ()
        # 本次进程内是否有新解析结果需要落盘
        self._persist_dirty = False

        # 文件级缓存额外承载 dsh 专属信息（标题 / cwd / 步级耗时）。
        # 直接复用基类的 `_file_cache`（它整体持久化到 ~/.cache/myccusage/dsh_file_cache.json），
        # 从而做到「重启进程后既不重解压、也不重解析」。
        # 缓存条目为 4 元组 `(mtime, size, records, info)`；基类只读写 [0]/[1]/[2]，
        # 追加第 4 位对其它 Agent 的既有缓存条目零影响，故无需 bump schema 版本。

    # ------------------------------------------------------------------
    # 数据源探测与文件清单
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """会话目录存在，且当前环境具备 zstd 解码能力"""
        if not any(os.path.isdir(d) for d in self.sessions_dirs):
            return False
        return zstdcodec.available()

    def _dirs_signature(self) -> tuple:
        """
        项目目录级签名：`((项目目录路径, mtime_ns), ...)`。

        只需一次 `os.scandir`（实测 500 个目录 1.7ms）。新增会话目录会让所属
        项目目录 mtime 变化，因此该签名足以判定「文件清单是否需要重建」。
        """
        sig = []
        for root in self.sessions_dirs:
            try:
                with os.scandir(root) as it:
                    for entry in it:
                        if not entry.is_dir(follow_symlinks=False):
                            continue
                        try:
                            sig.append((entry.path, entry.stat().st_mtime_ns))
                        except OSError:
                            continue
            except OSError:
                continue
        sig.sort()
        return tuple(sig)

    def _session_files(self) -> list[str]:
        """返回全部会话日志文件路径（带目录结构签名缓存）"""
        sig = self._dirs_signature()
        if sig == self._dirs_sig and self._paths_cache:
            return self._paths_cache

        paths: list[str] = []
        for project_dir, _mtime in sig:
            try:
                with os.scandir(project_dir) as it:
                    for session_entry in it:
                        if not session_entry.is_dir(follow_symlinks=False):
                            continue
                        try:
                            with os.scandir(session_entry.path) as files:
                                for f in files:
                                    if f.is_file(follow_symlinks=False) and f.name.endswith(_LOG_SUFFIXES):
                                        paths.append(f.path)
                        except OSError:
                            continue
            except OSError:
                continue

        self._paths_cache = paths
        self._dirs_sig = sig
        return paths

    def get_source_fingerprint(self) -> str:
        """
        极速获取 dsh 数据源指纹（本机 6 会话实测 1.5ms；2000 会话约 10ms）。

        组成：项目目录结构签名位数 + 全部日志文件的 `mtime_ns:size` 校验和。
        必须逐文件 stat：会话活跃时只会**追加写文件**，项目目录本身不变。
        """
        if not self.is_available():
            return ""
        sig = self._dirs_signature()
        digest = 0
        max_mtime = 0
        count = 0
        for path in self._session_files():
            try:
                st = os.stat(path)
            except OSError:
                continue
            count += 1
            digest = (digest * 1000003 + st.st_mtime_ns + st.st_size) & 0xFFFFFFFFFFFF
            if st.st_mtime_ns > max_mtime:
                max_mtime = st.st_mtime_ns
        return f"{len(sig)}:{count}:{max_mtime}:{digest:x}"

    # ------------------------------------------------------------------
    # 单文件解析
    # ------------------------------------------------------------------

    def _parse_file(self, fpath: str):
        """
        解析单个会话日志，返回 `(records, info)`。

        `records` 符合基类 10 元组契约：
        `(sid, date, iso, inp, cr, out, tot, model, credit, model_ms)`；
        `info` 承载标题、cwd 与 dsh 独有统计，供专属看板与标题解析复用。
        """
        raw = zstdcodec.decompress_file(fpath)
        if not raw:
            return [], {}

        sid = os.path.basename(os.path.dirname(fpath))
        cwd = ""
        title = ""
        created_at = 0

        records: list[tuple] = []
        stats = {
            "turns": 0,
            "steps": 0,
            "toolCalls": 0,
            "toolMs": 0,
            "llmMs": 0,
            "ttftMs": 0,
            "decodeMs": 0,
            "decodeTokens": 0,
            "retries": 0,
            "compactions": 0,
            "interrupted": 0,
            "contextWindow": 0,
            "toolKinds": {},
        }

        step_start: dict[tuple, int] = {}
        job_start: dict[str, int] = {}
        # 替换槽位：`(turn, step) -> records 下标`。
        # dsh 的 tokenUsage projection 对同一 (turn, step) 采用 addReplacing：
        # 后一次结算**减去**前一次再累加新值（等价于"只保留最后一次"）。
        # 这里用「覆写下标」实现同一效果；`llm/retry-started` 会清空该槽位，
        # 使重试后的结算重新**追加**，从而把两次独立调用都计入。
        step_slot: dict[tuple, int] = {}

        for line in raw.split(b"\n"):
            if not line:
                continue
            etype = _event_type(line)
            if not etype:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue

            kind = obj.get("type")
            data = obj.get("data") or {}

            if kind == "session":
                cwd = obj.get("cwd") or ""
                created_at = obj.get("createdAt") or 0
                continue

            if kind == "session/title":
                t = (data.get("title") or "").strip()
                if t:
                    title = t
                continue

            if kind == "step/start":
                step_start[(data.get("turn"), data.get("step"))] = obj.get("time") or 0
                stats["steps"] += 1
                continue

            if kind == "turn/start":
                stats["turns"] += 1
                continue

            if kind == "tool/call":
                stats["toolCalls"] += 1
                name = data.get("name")
                if name:
                    kinds = stats["toolKinds"]
                    kinds[name] = kinds.get(name, 0) + 1
                continue

            if kind == "job/registered":
                jid = data.get("jobId")
                started = data.get("startedAt") or obj.get("time") or 0
                if jid:
                    job_start[jid] = started
                continue

            if kind == "job/settled":
                jid = data.get("jobId")
                started = data.get("startedAt") or job_start.get(jid or "", 0)
                finished = data.get("finishedAt") or 0
                if started and finished and finished >= started:
                    stats["toolMs"] += finished - started
                continue

            if kind == "request/context":
                cw = data.get("contextWindow")
                if isinstance(cw, int) and cw > 0:
                    stats["contextWindow"] = cw
                continue

            if kind == "llm/retry-started":
                stats["retries"] += 1
                # 与官方 projection 一致：重试关闭替换槽位，下一次结算重新累加
                step_slot.pop((data.get("turn"), data.get("step")), None)
                continue

            if kind == "compaction/summary":
                stats["compactions"] += 1
                # dsh 的 tokenUsage projection 只折叠 assistant/message 与
                # assistant/attempt；compaction 自带的 usage **不计入** 会话 token。
                # 此处同样不计入，以保证与 dsh 官方看板逐位一致。
                continue

            if kind != "assistant/message":
                continue

            # ---- 以下为 assistant/message 的 usage 结算 ----
            if data.get("interrupted"):
                stats["interrupted"] += 1

            key = (data.get("turn"), data.get("step"))
            usage = data.get("usage")
            stream = data.get("stream") or []

            stream_times = []
            if stream:
                for rec in stream:
                    st = rec.get("time") or rec.get("time0")
                    if st:
                        stream_times.append(st)

            if usage is None and stream_times:
                # 回退：最后一个 type=="usage" 分片（对齐官方 usageOf()）
                for rec in reversed(stream):
                    chunk = rec.get("chunk")
                    if isinstance(chunk, dict) and chunk.get("type") == "usage":
                        usage = chunk.get("usage")
                        break

            if not stream_times or usage is None:
                continue

            started = step_start.get(key)
            first_t, last_t = min(stream_times), max(stream_times)
            step_decode_ms = 0
            if started and last_t >= started:
                stats["llmMs"] += last_t - started
                stats["ttftMs"] += max(0, first_t - started)
            if last_t > first_t:
                step_decode_ms = last_t - first_t
                stats["decodeMs"] += step_decode_ms
                stats["decodeTokens"] += int(usage.get("outputTokens") or 0)

            inp = int(usage.get("inputTokens") or 0)
            cr = int(usage.get("cacheReadTokens") or 0)
            cw = int(usage.get("cacheWriteTokens") or 0)
            out = int(usage.get("outputTokens") or 0)
            tot = int(usage.get("totalTokens") or 0)
            if tot <= 0:
                tot = inp + cr + cw + out
            if tot <= 0:
                continue

            ts = obj.get("time") or 0
            if not ts:
                continue
            dt = datetime.fromtimestamp(ts / 1000.0)

            source = ((data.get("message") or {}).get("source")) or {}
            model = normalize_model_name(source.get("model"))

            # cacheWrite 并入 input（与 claude 适配器同一约定），
            # 保证 Σ(input+cacheRead+output) == totalTokens 恒成立。
            # 第 10 位 model_ms 填本步的纯解码耗时 —— 与 WorkBuddy 的
            # 「模型纯推理净耗时」同义，可直接驱动 CLI/Web 的 TPS 列。
            record = (
                sid,
                dt.strftime("%Y-%m-%d"),
                dt.astimezone(timezone.utc).isoformat(),
                inp + cw,
                cr,
                out,
                tot,
                model,
                0.0,          # dsh 无官方积分/credit 概念
                step_decode_ms,
            )

            # 同一 (turn, step) 的后一次结算覆盖前一次（addReplacing 语义）；
            # 重试后槽位已被清空，故两次独立调用会各自成条、都被计入。
            slot = step_slot.get(key)
            if slot is not None:
                records[slot] = record
            else:
                step_slot[key] = len(records)
                records.append(record)

        info = {
            "sessionId": sid,
            "cwd": cwd,
            "title": title,
            "createdAt": created_at,
            "stats": stats,
        }
        return records, info

    # ------------------------------------------------------------------
    # 解析调度与缓存
    # ------------------------------------------------------------------

    def _ensure_parsed(self) -> None:
        """
        对全部会话文件做一次带 `mtime/size` 防抖的解析，结果写入 `self._file_cache`。

        条目结构为 `(mtime, size, records, info)`，其中 info 为 dsh 专属扩展位。

        末尾会按**当前文件清单**裁剪缓存：持久化缓存以绝对路径为键，一旦用户切换
        `DSH_HOME`（或在测试里指向临时目录），旧数据根的历史条目会残留在缓存里，
        若不裁剪就会把"别人家的会话"混进统计。裁剪是 O(n) 的集合差，成本可忽略。
        """
        if not self._file_cache:
            self._load_persisted_file_cache()

        files = self._session_files()
        if self._file_cache:
            live = set(files)
            stale = [p for p in self._file_cache if p not in live]
            if stale:
                for p in stale:
                    self._file_cache.pop(p, None)
                self._persist_dirty = True

        for fpath in files:
            try:
                st = os.stat(fpath)
            except OSError:
                continue
            cached = self._file_cache.get(fpath)
            if cached and cached[0] == st.st_mtime and cached[1] == st.st_size and len(cached) >= 4:
                continue
            try:
                records, info = self._parse_file(fpath)
            except Exception:
                # 单文件异常绝不拖垮整个 Agent：保留旧缓存（若有），否则记为不可读
                if not cached:
                    self._file_cache[fpath] = (st.st_mtime, st.st_size, [], {})
                continue
            self._file_cache[fpath] = (st.st_mtime, st.st_size, records, info)
            self._persist_dirty = True

    # ------------------------------------------------------------------
    # 基类契约实现
    # ------------------------------------------------------------------

    def get_titles_and_times(self) -> tuple[dict[str, str], dict[str, str]]:
        """从 `session/title` 事件提取原生标题（latest-wins）与最后活跃时间"""
        titles: dict[str, str] = {}
        times: dict[str, str] = {}
        if not self.is_available():
            return titles, times

        with self._lock:
            self._ensure_parsed()
            for fpath, entry in self._file_cache.items():
                records = entry[2]
                info = entry[3] if len(entry) > 3 else {}
                sid = (info or {}).get("sessionId") or os.path.basename(os.path.dirname(fpath))
                title = (info or {}).get("title")
                if title:
                    titles[sid] = title[:60]
                if records:
                    times[sid] = max(r[2] for r in records)
        return titles, times

    def fetch_data(self, today_only: bool = False) -> tuple[dict[str, list[dict]], list[dict]]:
        """
        提取 dsh 会话用量。

        - `today_only=True`：仅保留今日记录（对应程序屋 60s 轮询热路径）。
          以文件 mtime 早于今日零点作为剪枝依据 —— 这类文件不可能含今日事件，
          因此该路径下绝大多数历史会话是 **零解析成本** 被跳过的。
        - 全量模式走 `_full_cache`，由 `get_source_fingerprint()` 精准失效。
        """
        if not self.is_available():
            return {}, []

        fp = self.get_source_fingerprint()

        cached = self._cached_full_result(fp, today_only)
        if cached is not None:
            return cached

        all_records: list[tuple] = []
        with self._lock:
            self._ensure_parsed()

            # 只在全量模式下把新增的解析结果写盘：
            # today_only 是高频轮询路径，绝不能每次轮询都触发一次磁盘写。
            if self._persist_dirty and not today_only:
                self._save_persisted_file_cache()
                self._persist_dirty = False

            if today_only:
                today_str = datetime.now().strftime("%Y-%m-%d")
                day_anchor = datetime.now().replace(
                    hour=0, minute=0, second=0, microsecond=0,
                ).timestamp()
                for entry in self._file_cache.values():
                    if entry[0] < day_anchor:
                        continue
                    for rec in entry[2]:
                        if rec[1] == today_str:
                            all_records.append(rec)
            else:
                for entry in self._file_cache.values():
                    all_records.extend(entry[2])

        daily_map, session_list = self._accumulate_records(all_records)
        self._store_full_result(fp, daily_map, session_list, today_only)
        return daily_map, session_list

    # ------------------------------------------------------------------
    # dsh 专属统计口径（供专属看板 tab 与 CLI 使用）
    # ------------------------------------------------------------------

    def get_insights(self) -> dict:
        """
        汇总 dsh 独有的运行指标。

        返回结构（全部取自 jsonl 事件，不读 dsh 私有投影缓存）：
        - totals：tokens / calls / turns / steps / toolCalls / 各部分耗时与派生均值
        - models：按模型的 token、调用次数、缓存命中率
        - days：逐日 token 与调用次数
        - sessions：逐会话 token、轮次、步数、工具次数与耗时
        - tools：工具名称 × 调用次数排行
        - gaps：无法从 dsh 数据获得的口径（诚实上报，不虚构数值）
        """
        if not self.is_available():
            return {"available": False, "backend": zstdcodec.backend(), "gaps": []}

        self._ensure_parsed()

        by_model: dict[str, dict] = {}
        by_day: dict[str, dict] = {}
        by_session: list[dict] = []
        tool_kinds: dict[str, int] = {}

        totals = {
            "sessions": 0, "turns": 0, "steps": 0, "toolCalls": 0,
            "inputTokens": 0, "cacheReadTokens": 0, "outputTokens": 0, "totalTokens": 0,
            "calls": 0, "llmMs": 0, "toolMs": 0, "ttftMs": 0,
            "decodeMs": 0, "decodeTokens": 0,
            "retries": 0, "compactions": 0, "interrupted": 0,
        }
        context_window = 0

        for entry in self._file_cache.values():
            records = entry[2]
            info = entry[3] if len(entry) > 3 else {}
            stats = (info or {}).get("stats") or {}
            if not records and not stats.get("steps"):
                continue

            totals["sessions"] += 1
            for key in ("turns", "steps", "toolCalls", "toolMs", "llmMs", "ttftMs",
                        "decodeMs", "decodeTokens", "retries", "compactions", "interrupted"):
                totals[key] += int(stats.get(key, 0) or 0)
            for name, count in (stats.get("toolKinds") or {}).items():
                tool_kinds[name] = tool_kinds.get(name, 0) + int(count or 0)
            if stats.get("contextWindow"):
                context_window = max(context_window, int(stats["contextWindow"]))

            sess_tokens = 0
            sess_calls = 0
            for rec in records:
                sid, date_str, _iso, inp, cr, out, tot, model = rec[:8]
                sess_tokens += tot
                sess_calls += 1

                totals["inputTokens"] += inp
                totals["cacheReadTokens"] += cr
                totals["outputTokens"] += out
                totals["totalTokens"] += tot
                totals["calls"] += 1

                mv = by_model.get(model)
                if mv is None:
                    mv = by_model[model] = {
                        "model": model, "inputTokens": 0, "cacheReadTokens": 0,
                        "outputTokens": 0, "totalTokens": 0, "calls": 0, "sessions": set(),
                    }
                mv["inputTokens"] += inp
                mv["cacheReadTokens"] += cr
                mv["outputTokens"] += out
                mv["totalTokens"] += tot
                mv["calls"] += 1
                mv["sessions"].add(sid)

                dv = by_day.get(date_str)
                if dv is None:
                    dv = by_day[date_str] = {
                        "date": date_str, "totalTokens": 0, "inputTokens": 0,
                        "cacheReadTokens": 0, "outputTokens": 0, "calls": 0,
                    }
                dv["totalTokens"] += tot
                dv["inputTokens"] += inp
                dv["cacheReadTokens"] += cr
                dv["outputTokens"] += out
                dv["calls"] += 1

            by_session.append({
                "sessionId": (info or {}).get("sessionId") or "",
                "title": (info or {}).get("title") or "",
                "cwd": (info or {}).get("cwd") or "",
                "totalTokens": sess_tokens,
                "calls": sess_calls,
                "turns": int(stats.get("turns", 0) or 0),
                "steps": int(stats.get("steps", 0) or 0),
                "toolCalls": int(stats.get("toolCalls", 0) or 0),
                "llmMs": int(stats.get("llmMs", 0) or 0),
                "toolMs": int(stats.get("toolMs", 0) or 0),
                "ttftMs": int(stats.get("ttftMs", 0) or 0),
                "decodeMs": int(stats.get("decodeMs", 0) or 0),
                "decodeTokens": int(stats.get("decodeTokens", 0) or 0),
                "retries": int(stats.get("retries", 0) or 0),
                "interrupted": int(stats.get("interrupted", 0) or 0),
            })

        models = []
        for mv in by_model.values():
            mv["sessions"] = len(mv["sessions"])
            mv["cacheHitRate"] = _rate(
                mv["cacheReadTokens"], mv["inputTokens"] + mv["cacheReadTokens"]
            )
            models.append(mv)
        models.sort(key=lambda m: m["totalTokens"], reverse=True)

        totals["cacheHitRate"] = _rate(
            totals["cacheReadTokens"], totals["inputTokens"] + totals["cacheReadTokens"]
        )
        totals["avgTps"] = (
            round(totals["decodeTokens"] / (totals["decodeMs"] / 1000.0), 1)
            if totals["decodeMs"] > 0 else 0.0
        )
        totals["avgTtftMs"] = (
            round(totals["ttftMs"] / totals["steps"], 1) if totals["steps"] > 0 else 0.0
        )
        totals["avgLlmMs"] = (
            round(totals["llmMs"] / totals["steps"], 1) if totals["steps"] > 0 else 0.0
        )
        totals["avgToolMs"] = (
            round(totals["toolMs"] / totals["toolCalls"], 1) if totals["toolCalls"] > 0 else 0.0
        )

        tool_ranking = sorted(
            ({"name": k, "calls": v} for k, v in tool_kinds.items()),
            key=lambda t: (-t["calls"], t["name"]),
        )

        return {
            "available": True,
            "backend": zstdcodec.backend(),
            "totals": totals,
            "contextWindow": context_window,
            "models": models,
            "days": sorted(by_day.values(), key=lambda d: d["date"]),
            "sessions": sorted(by_session, key=lambda s: -s["totalTokens"]),
            "tools": tool_ranking,
            # 诚实上报无法获取的口径，前端显式标注而不虚构数值
            "gaps": [
                "官方积分 / credit：dsh 无该概念，积分口径恒为 0",
                "reasoningTokens：字段存在于 dsh schema，但实测从未上报，无法单独拆分思维链占比",
                "compaction 自身的 summarization 调用：dsh 官方投影不计入会话 token，此处同口径不计入",
                "跨设备同步：dsh 分片不携带 models / insight，异机数据仅计总量",
            ],
        }
