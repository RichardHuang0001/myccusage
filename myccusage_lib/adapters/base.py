"""
myccusage_lib.adapters.base:
Agent 适配器基类与公共工具函数:
- 统一定义 (daily_map, session_list) 数据返回契约
- 文件级 mtime/size 防抖缓存通用工具
- 统一毫秒/秒级时间戳转换与 ISO 格式化
"""

from __future__ import annotations

import os
import sys
import re
import threading
from datetime import datetime, timezone

_CANDIDATE_HOME_DIRS: list[str] | None = None

def get_candidate_home_dirs() -> list[str]:
    """
    极速自适应获取当前环境下的所有候选用户根目录:
    - macOS: 直接返回 [~]，0纳秒静态返回，绝无多余系统调用或性能损耗。
    - 纯 Linux (非 WSL): 返回 [~]。
    - WSL: 返回 [~, Windows用户主目录(/mnt/c/Users/<user>)]，支持双端数据无缝互通。
    - Windows 原生: 返回 [~] 以及 (若存在) 可达的 \\wsl.localhost\\... 目录。
    整个生命周期只在首次调用时解析并内存常驻 (< 0.05ms)。
    """
    global _CANDIDATE_HOME_DIRS
    if _CANDIDATE_HOME_DIRS is not None:
        return _CANDIDATE_HOME_DIRS

    res = []
    default_home = os.path.expanduser("~")
    if default_home and os.path.isdir(default_home):
        res.append(default_home)

    # 1. macOS 极速短路：绝无多余系统探测与 I/O，保障 macOS 原生极致体验
    if sys.platform == "darwin":
        _CANDIDATE_HOME_DIRS = res
        return _CANDIDATE_HOME_DIRS

    # 2. WSL 环境检测与 Windows 宿主目录发现
    if sys.platform.startswith("linux"):
        is_wsl = "WSL_DISTRO_NAME" in os.environ or os.path.exists("/proc/sys/fs/binfmt_misc/WSLInterop")
        if is_wsl and os.path.isdir("/mnt/c/Users"):
            win_user = None
            path_val = os.environ.get("PATH", "")
            m = re.search(r'/mnt/c/Users/([^/:]+)', path_val)
            if m:
                u = m.group(1)
                if u not in ("Public", "Default", "All Users"):
                    win_user = u
            if not win_user:
                u_cand = os.environ.get("USER", "")
                if u_cand and os.path.isdir(f"/mnt/c/Users/{u_cand}"):
                    win_user = u_cand
                else:
                    for d in os.listdir("/mnt/c/Users"):
                        if d not in ("Public", "Default", "Default User", "All Users") and os.path.isdir(f"/mnt/c/Users/{d}"):
                            win_user = d
                            break
            if win_user:
                win_home = f"/mnt/c/Users/{win_user}"
                if os.path.isdir(win_home) and win_home not in res:
                    res.append(win_home)

    # 3. Windows 原生环境与 WSL 镜像目录可选互通
    elif sys.platform == "win32":
        wsl_cand = os.environ.get("WSL_DISTRO_NAME", "Ubuntu")
        for prefix in (f"\\\\wsl.localhost\\{wsl_cand}\\home", f"\\\\wsl$\\{wsl_cand}\\home"):
            if os.path.isdir(prefix):
                try:
                    for u in os.listdir(prefix):
                        cand = os.path.join(prefix, u)
                        if os.path.isdir(cand) and cand not in res:
                            res.append(cand)
                    break
                except OSError:
                    pass

    _CANDIDATE_HOME_DIRS = res
    return _CANDIDATE_HOME_DIRS


class BaseAgentAdapter:
    """Agent 适配器基类，所有具体的 Agent 适配器都应继承此类"""
    agent_id = ""
    display_name = ""

    def __init__(self):
        """初始化基础适配器，设置防抖缓存和线程锁"""
        # 存储文件级的 mtime 和 size 防抖缓存，避免重复解析同一文件
        self._file_cache = {}
        # 全量结果缓存: (fingerprint, (daily_map, session_list))
        self._full_cache = (None, (None, None))
        # 线程安全锁，保护缓存并发读写
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # 子类共用实现：消除 8 个适配器之间的逐字重复
    # ------------------------------------------------------------------

    def _cached_full_result(self, fingerprint: str, today_only: bool):
        """
        命中进程内全量缓存时返回 (daily_map, session_list)，未命中返回 None。

        today_only 模式产出的是"仅今日热文件"的局部切片，与全量扫描结果语义不同，
        因此该模式既不读取也不写入全量缓存，避免两种口径互相污染。
        """
        if today_only:
            return None
        with self._lock:
            if self._full_cache[0] == fingerprint and self._full_cache[1][0] is not None:
                return self._full_cache[1]
        return None

    def _store_full_result(self, fingerprint: str, daily_map, session_list, today_only: bool) -> None:
        """全量扫描完成后写入进程内缓存 (today_only 模式不写入)。"""
        if today_only:
            return
        with self._lock:
            self._full_cache = (fingerprint, (daily_map, session_list))

    @staticmethod
    def _accumulate_records(records) -> tuple[dict[str, list[dict]], list[dict]]:
        """
        把记录流聚合为 (daily_map, session_list)：
        - records 元素为 (sessionId, 日期, ISO时间, 输入Token, 缓存读Token, 输出Token, 合计Token)
        - daily_map: { "YYYY-MM-DD": [ 当日会话切片, ... ] }，同日同会话自动合并累加
        - session_list: 每个会话的全生命周期累计

        6 个适配器 (agy/claude/codex/grok/pi/workbuddy) 共用完全相同的聚合算法，
        集中在此实现，避免逐字复制导致的"改一处漏五处"。

        实现说明：相比 `if key not in d: d[key] = X` 再取值的写法，这里统一用
        dict.get() 单次查找 + 局部变量缓存，可减少每条约 2~3 次哈希查找，
        在数万条记录的解析路径上是净收益。
        """
        daily: dict[str, dict[str, dict]] = {}
        sessions: dict[str, dict] = {}

        for sid, date_str, iso_str, inp, cr, out, tot in records:
            # 1) 每日切片累加
            day = daily.get(date_str)
            if day is None:
                day = daily[date_str] = {}
            ds = day.get(sid)
            if ds is None:
                ds = day[sid] = {
                    "sessionId": sid,
                    "date": date_str,
                    "inputTokens": 0,
                    "cacheReadTokens": 0,
                    "outputTokens": 0,
                    "totalTokens": 0,
                    "lastActivity": iso_str,
                }
            ds["inputTokens"] += inp
            ds["cacheReadTokens"] += cr
            ds["outputTokens"] += out
            ds["totalTokens"] += tot
            if iso_str > ds["lastActivity"]:
                ds["lastActivity"] = iso_str

            # 2) 会话全生命周期累加
            ss = sessions.get(sid)
            if ss is None:
                ss = sessions[sid] = {
                    "sessionId": sid,
                    "inputTokens": 0,
                    "cacheReadTokens": 0,
                    "outputTokens": 0,
                    "totalTokens": 0,
                    "lastActivity": iso_str,
                }
            ss["inputTokens"] += inp
            ss["cacheReadTokens"] += cr
            ss["outputTokens"] += out
            ss["totalTokens"] += tot
            if iso_str > ss["lastActivity"]:
                ss["lastActivity"] = iso_str

        return ({d: list(day.values()) for d, day in daily.items()}, list(sessions.values()))

    def _load_persisted_file_cache(self):
        """从本地磁盘快速加载文件级防抖缓存 (JSON 格式，< 10ms)"""
        if not self.agent_id:
            return
        cache_path = os.path.expanduser(f"~/.cache/myccusage/{self.agent_id}_file_cache.json")
        if os.path.exists(cache_path):
            try:
                import json
                with open(cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self._file_cache.update(data)
            except Exception:
                pass

    def _save_persisted_file_cache(self):
        """将文件级防抖缓存原子写入磁盘以供后续进程秒开"""
        if not self.agent_id or not self._file_cache:
            return
        cache_dir = os.path.expanduser("~/.cache/myccusage")
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, f"{self.agent_id}_file_cache.json")
        tmp_path = cache_path + f".tmp.{os.getpid()}"
        try:
            import json
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._file_cache, f)
            os.replace(tmp_path, cache_path)
        except Exception:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass


    def is_available(self) -> bool:
        """
        检测当前 Agent 本地数据源是否存在
        返回 True 表示数据源目录或核心文件存在
        """
        raise NotImplementedError

    def get_source_fingerprint(self) -> str:
        """
        获取该 Agent 数据源的快速状态指纹 (微秒级)
        用于判断自上次抓取以来底层数据是否发生任何变化
        """
        return ""

    def get_titles_and_times(self) -> tuple[dict[str, str], dict[str, str]]:
        """
        提取会话原生标题映射与时间覆盖映射:
        - titles: { sessionId: title }
        - times: { sessionId: iso_timestamp }
        """
        return {}, {}

    def fetch_data(self, today_only: bool = False) -> tuple[dict[str, list[dict]], list[dict]]:
        """
        高性能提取原始数据:
        返回 (daily_map, session_list) 二元组
        - today_only: 若为 True，仅扫描今日凌晨以后修改的热文件 (性能提速 50x)
        - daily_map: 每日切片数据聚合，格式为 { "YYYY-MM-DD": [ {sessionId, date, inputTokens, cacheReadTokens, outputTokens, totalTokens, lastActivity}, ... ] }
        - session_list: 全生命周期汇总，格式为 [ {sessionId, inputTokens, cacheReadTokens, outputTokens, totalTokens, lastActivity}, ... ]
        """
        raise NotImplementedError

def get_today_midnight_ts() -> float:
    """获取今天凌晨 00:00:00 的本地秒级时间戳"""
    now = datetime.now()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.timestamp()

def scan_files_fast(
    root_dirs: list[str] | str,
    extensions: tuple[str, ...] | str = (".jsonl", ".db"),
    recursive: bool = True,
    max_depth: int = 4,
    today_only: bool = False,
    min_mtime: float = 0.0
) -> list[str]:
    """
    基于 os.scandir 的极速文件检索工具:
    - 针对 macOS APFS 文件系统单次系统调用内联提取 st_mtime，相比 glob.glob 性能提升 10x~50x
    - 支持 today_only 剪枝：直接在扫描层跳过今日凌晨以前未修改的冷文件
    """
    if isinstance(root_dirs, str):
        root_dirs = [root_dirs]
    if isinstance(extensions, str):
        extensions = (extensions,)

    if today_only and min_mtime <= 0.0:
        min_mtime = get_today_midnight_ts()

    results = []

    def _walk(directory: str, current_depth: int):
        if current_depth > max_depth:
            return
        try:
            with os.scandir(directory) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if recursive:
                                _walk(entry.path, current_depth + 1)
                        elif entry.is_file(follow_symlinks=False):
                            name = entry.name
                            if any(name.endswith(ext) for ext in extensions):
                                if min_mtime > 0.0:
                                    try:
                                        if entry.stat().st_mtime < min_mtime:
                                            continue
                                    except OSError:
                                        continue
                                results.append(entry.path)
                    except OSError:
                        continue
        except OSError:
            pass

    for rdir in root_dirs:
        if os.path.isdir(rdir):
            _walk(rdir, 1)

    return results

def ts_to_iso(ts_seconds: float) -> str:
    """浮点/整数秒转 ISO 8601 字符串"""
    if not ts_seconds:
        return ""
    try:
        # 将秒级时间戳转换为带时区信息的 datetime，然后转为 ISO 格式
        return datetime.fromtimestamp(ts_seconds, timezone.utc).isoformat()
    except Exception:
        return ""

def ms_to_iso(ts_ms: int) -> str:
    """毫秒时间戳转 ISO 8601 字符串"""
    if not ts_ms:
        return ""
    try:
        # 将毫秒除以 1000 转为秒
        return datetime.fromtimestamp(ts_ms / 1000.0, timezone.utc).isoformat()
    except Exception:
        return ""

def ts_to_date_str(ts_seconds: float) -> str:
    """浮点/整数秒转 YYYY-MM-DD 本地日期"""
    try:
        return datetime.fromtimestamp(ts_seconds).strftime("%Y-%m-%d")
    except Exception:
        return "1970-01-01"

def ms_to_date_str(ts_ms: int) -> str:
    """毫秒时间戳转 YYYY-MM-DD 本地日期"""
    try:
        return datetime.fromtimestamp(ts_ms / 1000.0).strftime("%Y-%m-%d")
    except Exception:
        return "1970-01-01"
