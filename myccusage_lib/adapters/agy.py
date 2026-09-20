"""
myccusage_lib.adapters.agy:
Google Antigravity 100% 纯 Python 原生适配器:
- 零外部依赖 (Zero dependencies): 无需安装 Node.js、ccusage 或 protobuf pip 包
- 直连 ~/.gemini/antigravity/conversations/*.db SQLite 数据库 (只读模式)
- 内置轻量级 Protobuf Varint 解码器，精准提取每一次交互的毫秒时间戳与 Token 用量
- 精准自然日切片 (Daily Slices)，彻底消除历史跨日长会话累积移位的重大数据漂移
- 会话全生命周期汇总 (Session Lifetime) 保持与日切片 100% 守恒
- 基于 agyhub_summaries_proto.pb 原生提取纯净标题，修复 varint 长度字节污染 (如 'i' 前缀)
"""

from __future__ import annotations

import os
import re
import glob
import sqlite3
from datetime import datetime, timezone
from .base import BaseAgentAdapter, ts_to_iso, ts_to_date_str, scan_files_fast

def parse_proto(b: bytes) -> list[tuple[int, int, any]]:
    """
    轻量原生 Protobuf 二进制解码器:
    解析 tag 与 wire type，支持 varint (wire 0)、length-delimited (wire 2)、
    64-bit (wire 1)、32-bit (wire 5)。
    零依赖，无需引入外部 protobuf 包。
    """
    pos = 0
    fields = []
    length = len(b)
    while pos < length:
        res = 0
        shift = 0
        while True:
            if pos >= length:
                break
            byte = b[pos]
            pos += 1
            res |= (byte & 0x7F) << shift
            shift += 7
            if not (byte & 0x80):
                break
        wire = res & 7
        field_no = res >> 3
        if wire == 0:  # varint
            val = 0
            s = 0
            while True:
                if pos >= length:
                    break
                byte = b[pos]
                pos += 1
                val |= (byte & 0x7F) << s
                s += 7
                if not (byte & 0x80):
                    break
            fields.append((field_no, wire, val))
        elif wire == 2:  # length-delimited (string, bytes, embedded message)
            val = 0
            s = 0
            while True:
                if pos >= length:
                    break
                byte = b[pos]
                pos += 1
                val |= (byte & 0x7F) << s
                s += 7
                if not (byte & 0x80):
                    break
            data = b[pos : pos + val]
            pos += val
            fields.append((field_no, wire, data))
        elif wire == 1:  # 64-bit fixed
            fields.append((field_no, wire, b[pos : pos + 8]))
            pos += 8
        elif wire == 5:  # 32-bit fixed
            fields.append((field_no, wire, b[pos : pos + 4]))
            pos += 4
        else:
            break
    return fields


def extract_smart_title(req: str, default_title: str = "") -> str:
    """
    智能提取会话标题：
    - 针对子任务、多行批量任务、以冒号结尾的通用引导句，自动向下探查具体目标文件/模块
    - 自动去除括号内的冗余说明，格式化为 [子任务] 动作: 目标
    - 避免多个并行子 Agent 会话出现完全相同的标题
    """
    lines = [l.strip() for l in req.split("\n") if l.strip() and not l.startswith("<")]
    if not lines:
        return default_title or "（未命名会话）"
    first = lines[0]
    is_generic = (
        first.endswith(":") or first.endswith("：") or
        "请为以下文件" in first or "需要注释的文件" in first or
        "请执行以下" in first or "子任务" in first or
        len(first) < 6
    )
    if is_generic and len(lines) > 1:
        for sub in lines[1:6]:
            m = re.search(r'(?:文件路径|文件|file):\s*(?:[^\n]*/)?([a-zA-Z0-9_\-\.]+\.[a-zA-Z0-9]+)', sub, re.I)
            if m:
                target = m.group(1)
                if "注释" in first:
                    return f"[子任务] 注释: {target}"
                action = re.sub(r'[（(].*?[）)]', '', first).rstrip("：:").strip()[:15]
                return f"[子任务] {action}: {target}"
            m2 = re.search(r'^\d+[\.、]\s*(?:[^\s—\n]*/)?([a-zA-Z0-9_\-\.]+\.[a-zA-Z0-9]+)', sub)
            if m2:
                target = m2.group(1)
                if "注释" in first:
                    return f"[子任务] 注释: {target}"
                action = re.sub(r'[（(].*?[）)]', '', first).rstrip("：:").strip()[:15]
                return f"[子任务] {action}: {target}"
            m3 = re.search(r'(?:目标|任务|task|role):\s*([^\n]{3,30})', sub, re.I)
            if m3:
                return f"[子任务] {m3.group(1).strip()}"
    clean_first = first.rstrip("：:").strip()
    return clean_first[:60]


class AntigravityAdapter(BaseAgentAdapter):
    """Google Antigravity 100% 纯 Python 原生数据适配器"""
    agent_id = "agy"
    display_name = "Google Antigravity"
    has_times = False

    def __init__(self):
        super().__init__()
        self.base_dir = os.path.expanduser("~/.gemini/antigravity")
        self.conv_dir = os.path.join(self.base_dir, "conversations")
        self.cache_dir = os.path.expanduser("~/.cache/myccusage")

    def is_available(self) -> bool:
        """检测本地 Antigravity 目录或会话目录是否存在"""
        return os.path.exists(self.base_dir) and (
            os.path.exists(self.conv_dir) or os.path.exists(os.path.join(self.base_dir, "brain"))
        )

    def get_titles_and_times(self) -> tuple[dict[str, str], dict[str, str]]:
        """
        提取 Antigravity 会话的原生纯净标题与最近活跃时间:
        1. 优先从 agyhub_summaries_proto.pb 精准解码 Protobuf 结构，彻底剔除 varint 长度杂字符 (如 'i')
        2. 若标题以冒号结尾或属于批量/子任务通用引导句，向下深度检索 transcript.jsonl 提取精确靶标
        3. 兜底读取 brain/*/.system_generated/logs/transcript.jsonl
        """
        titles = {}
        times = {}
        if not self.is_available():
            return titles, times

        # 1. 结构化解码 agyhub_summaries_proto.pb
        proto_path = os.path.join(self.base_dir, "agyhub_summaries_proto.pb")
        if os.path.exists(proto_path):
            try:
                with open(proto_path, "rb") as f:
                    data = f.read()
                for fno, wire, val in parse_proto(data):
                    if fno == 1 and wire == 2 and isinstance(val, bytes):
                        entry = dict((sf[0], sf[2]) for sf in parse_proto(val))
                        sid_raw = entry.get(1)
                        sub2_raw = entry.get(2)
                        if sid_raw and sub2_raw and isinstance(sub2_raw, bytes):
                            sid = sid_raw.decode("utf-8", errors="ignore").strip()
                            summary_flds = dict((sf[0], sf[2]) for sf in parse_proto(sub2_raw))
                            title_raw = summary_flds.get(1)
                            if title_raw and isinstance(title_raw, bytes):
                                t = title_raw.decode("utf-8", errors="ignore").strip()
                                if t and sid:
                                    titles[sid] = t
            except Exception:
                pass

        # 2. 从 transcript.jsonl 中补充或精确细化子任务标题
        logs_glob = os.path.join(self.base_dir, "brain/*/.system_generated/logs/transcript.jsonl")
        for log_path in glob.glob(logs_glob):
            parts = os.path.normpath(log_path).split(os.sep)
            uid = ""
            for idx, p in enumerate(parts):
                if p == "brain" and idx + 1 < len(parts):
                    uid = parts[idx + 1]
                    break
            if not uid and len(parts) >= 4:
                uid = parts[-4]

            existing_t = titles.get(uid, "")
            needs_refinement = (
                not existing_t
                or existing_t.endswith(("：", ":"))
                or "请为以下文件" in existing_t
                or "需要注释的文件" in existing_t
                or "请执行以下" in existing_t
                or len(existing_t) < 4
            )

            if uid and needs_refinement:
                try:
                    with open(log_path, "r", encoding="utf-8") as f:
                        first_line = f.readline()
                        if first_line:
                            import json
                            obj = json.loads(first_line)
                            content = obj.get("content", "")
                            if "<USER_REQUEST>" in content:
                                req = content.split("<USER_REQUEST>")[1].split("</USER_REQUEST>")[0].strip()
                            else:
                                req = content.strip()
                            smart_t = extract_smart_title(req, default_title=existing_t)
                            if smart_t:
                                titles[uid] = smart_t
                except Exception:
                    pass

        return titles, times


    def get_source_fingerprint(self) -> str:
        """极速获取 conversations 目录下数据库文件的修改状态指纹 (< 1ms)"""
        if not self.is_available():
            return ""
        max_mtime = 0
        file_count = 0
        try:
            with os.scandir(self.conv_dir) as it:
                for entry in it:
                    if entry.name.endswith(".db"):
                        file_count += 1
                        try:
                            mt = entry.stat().st_mtime_ns
                            if mt > max_mtime:
                                max_mtime = mt
                        except OSError:
                            pass
        except OSError:
            return ""
        return f"{file_count}:{max_mtime}"

    def fetch_data(self, today_only: bool = False) -> tuple[dict[str, list[dict]], list[dict]]:
        """
        100% 纯原生提取 Antigravity 消费数据:
        - 直连 ~/.gemini/antigravity/conversations/*.db (只读模式，不争抢写锁)
        - 支持 today_only: 仅扫描今日凌晨以后修改的热文件 (性能提速 50x)
        - 遍历 steps 表中 step_type = 15 的模型输出轮次
        - 利用内置 Protobuf Varint 解码器解析 Field 1 (时间戳) 与 Field 9 (Token用量)
        - 将跨天长会话的 Token 精准拆解到每一次实际发生的自然日 (彻底杜绝多日堆积至当天)
        - 使用 mtime + size 内存防抖缓存，保障后续读取 < 10ms 极致速度
        """
        if not self.is_available():
            return {}, []

        fp = self.get_source_fingerprint()

        # 全量模式下检查整体缓存
        if not today_only:
            with self._lock:
                if self._full_cache[0] == fp and self._full_cache[1][0] is not None:
                    return self._full_cache[1]

        daily_map = {}
        session_map = {}

        db_files = scan_files_fast(self.conv_dir, extensions=(".db",), recursive=False, today_only=today_only)

        with self._lock:
            if not self._file_cache:
                self._load_persisted_file_cache()
            cache_modified = False

            for fpath in db_files:
                try:
                    stat = os.stat(fpath)
                except OSError:
                    continue

                mtime, size = stat.st_mtime, stat.st_size
                cached = self._file_cache.get(fpath)


                # mtime + size 防抖缓存命中
                if cached and cached[0] == mtime and cached[1] == size:
                    records = cached[2]
                else:
                    records = []
                    sid = os.path.basename(fpath).replace(".db", "")
                    try:
                        uri = f"file:{fpath}?mode=ro"
                        conn = sqlite3.connect(uri, uri=True, timeout=2.0)
                        c = conn.cursor()
                        c.execute("SELECT metadata FROM steps WHERE step_type = 15 AND metadata IS NOT NULL")
                        for (meta,) in c.fetchall():
                            if not meta:
                                continue
                            flds = dict((f[0], f[2]) for f in parse_proto(meta))
                            ts_sec = 0
                            if 1 in flds and isinstance(flds[1], bytes):
                                ts_f = dict((f[0], f[2]) for f in parse_proto(flds[1]))
                                ts_sec = ts_f.get(1, 0)
                            if 9 in flds and isinstance(flds[9], bytes):
                                u_f = dict((f[0], f[2]) for f in parse_proto(flds[9]))
                                inp = u_f.get(2, 0)
                                cr = u_f.get(5, 0)
                                out = u_f.get(3, 0)
                                tot = inp + cr + out
                                if tot > 0 and ts_sec > 0:
                                    dt = datetime.fromtimestamp(ts_sec)
                                    date_str = dt.strftime("%Y-%m-%d")
                                    iso_str = datetime.fromtimestamp(ts_sec, timezone.utc).isoformat()
                                    records.append((sid, date_str, iso_str, inp, cr, out, tot))
                        conn.close()
                    except Exception:
                        # 保护性退避：若读取发生碰撞（如 Agent 正在排他写库锁死），安全回退使用上次成功快照，避免空数据污染
                        records = cached[2] if cached else []
                    else:
                        # 仅在读取完全成功时才更新文件防抖缓存
                        self._file_cache[fpath] = (mtime, size, records)
                        cache_modified = True


                # 聚合计算
                for sid, date_str, iso_str, inp, cr, out, tot in records:
                    # 1. 每日精准切片
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
                            "lastActivity": iso_str,
                        }
                    ds = daily_map[date_str][sid]
                    ds["inputTokens"] += inp
                    ds["cacheReadTokens"] += cr
                    ds["outputTokens"] += out
                    ds["totalTokens"] += tot
                    if iso_str > ds["lastActivity"]:
                        ds["lastActivity"] = iso_str

                    # 2. 全周期会话累计
                    if sid not in session_map:
                        session_map[sid] = {
                            "sessionId": sid,
                            "inputTokens": 0,
                            "cacheReadTokens": 0,
                            "outputTokens": 0,
                            "totalTokens": 0,
                            "lastActivity": iso_str,
                        }
                    ss = session_map[sid]
                    ss["inputTokens"] += inp
                    ss["cacheReadTokens"] += cr
                    ss["outputTokens"] += out
                    ss["totalTokens"] += tot
                    if iso_str > ss["lastActivity"]:
                        ss["lastActivity"] = iso_str

            if cache_modified and not today_only:
                self._save_persisted_file_cache()

        daily_res = {d: list(s_dict.values()) for d, s_dict in daily_map.items()}
        session_res = list(session_map.values())
        if not today_only:
            with self._lock:
                self._full_cache = (fp, (daily_res, session_res))
        return daily_res, session_res

