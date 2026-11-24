"""豆包工作常驻增量采集引擎（非适配器，不进 ADAPTERS 注册表）。

嵌入既有常驻 daemon 的 /api/today 与 /api/ping 入口，由程序坞 60s 轮询 / Web 心跳驱动，
零新增进程、零新增线程。开关关闭时热路径仅一次内存布尔判断（~0µs），完全退化回基线。

职责边界：只负责"在 LevelDB compaction 丢弃逐轮快照前，把数据安全固化到自有账本"。
展示由 adapters/doubao.py（P3）读取本账本完成，二者彻底解耦。

设计详见 docs/豆包工作统计适配架构与施工计划.md。
"""

from __future__ import annotations

import os
import json
import glob
import time
import threading

from .. import idbcodec as C

# --- 路径常量（测试可 monkeypatch）---
CACHE_DIR = os.path.expanduser("~/.cache/myccusage")
CONFIG_DIR = os.path.expanduser("~/.config/myccusage")
JOURNAL = os.path.join(CACHE_DIR, "doubao_journal.jsonl")
STATE = os.path.join(CACHE_DIR, "doubao_state.json")
CONFIG = os.path.join(CONFIG_DIR, "doubao_config.json")

MIN_INTERVAL = 30.0      # 节流：双驱动源（Dock 60s / Web 心跳 2.5s）合并到 ≥30s 一次
OVERLAP = 4096           # WAL 尾读重叠窗，捕获跨边界记录
_COMPACT_LINES = 5000    # 账本压实阈值
_COMPACT_BYTES = 2_000_000

# --- 模块级状态 ---
_enabled = False
_lock = threading.Lock()
_last_tick = 0.0
_loaded = False
_state: dict = {"files": {}}
_usage: dict = {}        # message_id -> 最优 usage 记录（context_total 最大）
_meta: dict = {}         # conversation_id -> 最新会话元数据
_journal_bytes = 0
_journal_lines = 0

# 启动时加载开关（一次性文件读，不在热路径）
try:
    with open(CONFIG, "r", encoding="utf-8") as _f:
        _enabled = bool(json.load(_f).get("enabled", False))
except Exception:
    _enabled = False


def _source_dirs() -> list[str]:
    """枚举所有 Profile 下的豆包聊天 LevelDB 目录（不存在则零成本跳过）。"""
    base = os.path.expanduser("~/Library/Application Support/Doubao")
    dirs = []
    candidates = glob.glob(os.path.join(base, "Profile *")) + [os.path.join(base, "Default")]
    for prof in candidates:
        d = os.path.join(prof, "IndexedDB", "chrome_doubao-chat_0.indexeddb.leveldb")
        if os.path.isdir(d):
            dirs.append(d)
    return dirs


def _fingerprint(dirs: list[str]) -> str:
    """全部 ldb/log 的「名:大小:mtime_ns」指纹（~N 次 stat，微秒级）。"""
    parts = []
    for d in dirs:
        try:
            with os.scandir(d) as it:
                for e in it:
                    if e.name.endswith((".ldb", ".log")):
                        st = e.stat()
                        parts.append(f"{d}|{e.name}:{st.st_size}:{st.st_mtime_ns}")
        except OSError:
            pass
    return ";".join(sorted(parts))


def _ensure_loaded() -> None:
    """懒加载 state + 从账本重建去重索引（首次启用 tick 或首次 status 时）。"""
    global _loaded, _state, _usage, _meta, _journal_bytes, _journal_lines
    if _loaded:
        return
    _state = {"files": {}}
    try:
        with open(STATE, "r", encoding="utf-8") as f:
            _state = json.load(f)
            if not isinstance(_state, dict):
                _state = {"files": {}}
            _state.setdefault("files", {})
    except Exception:
        pass
    _usage = {}
    _meta = {}
    _journal_bytes = 0
    _journal_lines = 0
    try:
        with open(JOURNAL, "r", encoding="utf-8") as f:
            for line in f:
                _journal_bytes += len(line.encode("utf-8"))
                _journal_lines += 1
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if obj.get("type") == "usage":
                    mid = obj.get("message_id")
                    if not mid:
                        continue
                    prev = _usage.get(mid)
                    if prev is None or obj.get("context_total", 0) > prev.get("context_total", 0):
                        _usage[mid] = obj
                elif obj.get("type") == "meta":
                    cid = obj.get("conversation_id")
                    if cid:
                        _meta[cid] = obj
    except FileNotFoundError:
        pass
    except Exception:
        pass
    _loaded = True


def _append_journal(obj: dict) -> None:
    global _journal_bytes, _journal_lines
    os.makedirs(CACHE_DIR, exist_ok=True)
    line = json.dumps(obj, ensure_ascii=False) + "\n"
    with open(JOURNAL, "a", encoding="utf-8") as f:
        f.write(line)
    _journal_bytes += len(line.encode("utf-8"))
    _journal_lines += 1


def _capture(dirs: list[str]) -> tuple[list, list]:
    """按 offset 增量读 WAL + 变更 .ldb 冷解码，返回 (usage 记录, 会话元数据)。"""
    files_state = _state.setdefault("files", {})
    seen = set()
    usage, meta = [], []
    for d in dirs:
        # WAL 热路径：值未压缩，只读追加尾部（含重叠窗）
        for path in sorted(glob.glob(os.path.join(d, "*.log"))):
            name = f"{d}|{os.path.basename(path)}"
            seen.add(name)
            try:
                st = os.stat(path)
                with open(path, "rb") as f:
                    data = f.read()
            except OSError:
                continue
            end = C.wal_complete_end(data)
            fs = files_state.get(name)
            start = 0
            if fs and fs.get("offset", 0) <= end:
                start = max(0, fs["offset"] - OVERLAP)
            blob = data[start:end]
            usage += C.extract_usage_records(blob)
            meta += C.extract_conversation_meta(blob)
            files_state[name] = {"size": st.st_size, "mtime": st.st_mtime_ns, "offset": end, "kind": "log"}
        # .ldb 冷路径：仅当大小/mtime 变化才解压（块 Snappy）
        for path in sorted(glob.glob(os.path.join(d, "*.ldb"))):
            name = f"{d}|{os.path.basename(path)}"
            seen.add(name)
            try:
                st = os.stat(path)
            except OSError:
                continue
            fs = files_state.get(name)
            if fs and fs.get("size") == st.st_size and fs.get("mtime") == st.st_mtime_ns:
                continue
            try:
                for blob in C.iter_table_blocks(path):
                    usage += C.extract_usage_records(blob)
                    meta += C.extract_conversation_meta(blob)
            except Exception:
                pass
            files_state[name] = {"size": st.st_size, "mtime": st.st_mtime_ns, "kind": "ldb"}
    # 清理已消失文件（轮换/compaction），保持 state 精简
    for name in list(files_state):
        if name not in seen:
            del files_state[name]
    return usage, meta


def _absorb(usage_recs: list, meta_recs: list) -> int:
    """去重固化：usage 取 context_total 最大版，meta 取变更版。返回新增行数。"""
    now_ms = int(time.time() * 1000)
    appended = 0
    for r in usage_recs:
        mid = r.get("message_id")
        if not mid:
            continue
        prev = _usage.get(mid)
        if prev is None or r.get("context_total", 0) > prev.get("context_total", 0):
            rec = {"type": "usage", **r, "captured_at": now_ms}
            _usage[mid] = rec
            _append_journal(rec)
            appended += 1
    for m in meta_recs:
        cid = m.get("conversation_id")
        if not cid:
            continue
        prev = _meta.get(cid)
        if (prev is None or m.get("name") != prev.get("name")
                or m.get("update_time") != prev.get("update_time")):
            rec = {"type": "meta", **m, "captured_at": now_ms}
            _meta[cid] = rec
            _append_journal(rec)
            appended += 1
    return appended


def _save_state() -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp = f"{STATE}.tmp.{os.getpid()}"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_state, f, ensure_ascii=False)
        os.replace(tmp, STATE)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _maybe_compact() -> None:
    global _journal_bytes, _journal_lines
    if _journal_lines <= _COMPACT_LINES and _journal_bytes <= _COMPACT_BYTES:
        return
    tmp = f"{JOURNAL}.tmp.{os.getpid()}"
    n = b = 0
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            for r in _usage.values():
                line = json.dumps(r, ensure_ascii=False) + "\n"
                f.write(line)
                n += 1
                b += len(line.encode("utf-8"))
            for m in _meta.values():
                line = json.dumps(m, ensure_ascii=False) + "\n"
                f.write(line)
                n += 1
                b += len(line.encode("utf-8"))
        os.replace(tmp, JOURNAL)
        _journal_lines, _journal_bytes = n, b
    except Exception:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def tick(force: bool = False) -> None:
    """采集入口（嵌入 /api/today 与 /api/ping）。

    关闭态：一次布尔判断即返回（~0µs）。开启态：节流 + 非阻塞锁 + 指纹预检。
    force=True 用于 CLI 手动单步与测试，绕过节流/指纹/开关。
    任何异常都收敛，绝不影响宿主请求主响应。
    """
    global _last_tick
    if not force and not _enabled:
        return
    now = time.time()
    if not force and now - _last_tick < MIN_INTERVAL:
        return
    if not _lock.acquire(blocking=False):
        return
    try:
        _last_tick = now
        _ensure_loaded()
        dirs = _source_dirs()
        if not dirs:
            return
        fp = _fingerprint(dirs)
        if not force and fp == _state.get("fp"):
            return
        usage, meta = _capture(dirs)
        _absorb(usage, meta)
        _state["fp"] = fp
        _save_state()
        _maybe_compact()
    except Exception:
        pass
    finally:
        _lock.release()


def set_enabled(flag: bool) -> dict:
    """热切换开关（写配置 + 改内存布尔，无需重启），返回最新状态。"""
    global _enabled
    _enabled = bool(flag)
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp = f"{CONFIG}.tmp.{os.getpid()}"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"enabled": _enabled}, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CONFIG)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    return get_status()


def get_status() -> dict:
    """采集状态（供开关旁展示，按需调用，非热路径）。"""
    with _lock:
        _ensure_loaded()
        dirs = _source_dirs()
        since = min(
            (r.get("create_time_ms") for r in _usage.values() if r.get("create_time_ms")),
            default=None,
        )
        return {
            "enabled": _enabled,
            "available": bool(dirs),
            "lastTickTime": _last_tick,
            "capturedRounds": len(_usage),
            "capturedConversations": len(_meta),
            "journalBytes": _journal_bytes,
            "coverageSince": since,
            "minIntervalSec": MIN_INTERVAL,
        }


def _reset() -> None:
    """清空内存态（测试用；下次 tick/status 会重新懒加载）。"""
    global _loaded, _state, _usage, _meta, _journal_bytes, _journal_lines, _last_tick
    _loaded = False
    _state = {"files": {}}
    _usage = {}
    _meta = {}
    _journal_bytes = 0
    _journal_lines = 0
    _last_tick = 0.0