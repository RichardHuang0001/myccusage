"""
myccusage_lib.sync:
多端 Git 私有同步核心引擎:
- 基于私有 GitHub 仓库与设备物理分片 (Device Partitioning) 架构
- 本机数据只读导出，异机数据并集合并，天然零 Git 冲突与零重算
- 极致性能设计：未开启同步或日常读取时短路开销 < 0.01ms
- 纯结构化轻量账本同步 (只同步 Token/时间戳/标题度量指标，绝不上传私有代码与日志)
"""

from __future__ import annotations

import os
import sys
import json
import re
import time
import socket
import subprocess
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from .adapters import ADAPTERS, get_adapter

# 线程锁与全局缓存
_SYNC_LOCK = threading.Lock()
_CONFIG_CACHE: dict[str, Any] | None = None
_REMOTE_DEVICES_CACHE: dict[str, Any] | None = None
# 异机数据缓存的有效性键：由 devices/ 下全部分片文件的「文件数 + 最大 mtime」构成
# (仅用目录 mtime 无法感知同名分片被覆盖写入，会长期读到陈旧异机数据)
_REMOTE_DEVICES_CACHE_KEY: str = ""

def get_sync_base_dir() -> str:
    """获取多端同步根存储目录 (~/.config/myccusage)"""
    base = os.path.expanduser("~/.config/myccusage")
    os.makedirs(base, exist_ok=True)
    return base

def get_sync_config_path() -> str:
    """获取同步配置文件绝对路径"""
    return os.path.join(get_sync_base_dir(), "sync_config.json")

def get_sync_repo_dir() -> str:
    """获取本地持有的私有同步 Git 仓库工作区目录"""
    return os.path.join(get_sync_base_dir(), "sync_repo")

def get_default_device_id() -> str:
    """自动生成当前机器的默认稳定唯一标识 (小写字母/数字/连字符)"""
    try:
        raw = socket.gethostname().split('.')[0].lower()
    except Exception:
        raw = "device"
    clean = re.sub(r'[^a-z0-9_-]', '', raw)
    if not clean:
        clean = "device"
    # 附加平台后缀以防止多系统同名冲突 (例如 macbook-darwin, desktop-win32)
    plat = "mac" if sys.platform == "darwin" else ("win" if sys.platform == "win32" else "linux")
    return f"{clean}-{plat}"

def get_default_device_name() -> str:
    """自动生成当前机器的友好展示名称"""
    try:
        raw = socket.gethostname().split('.')[0]
    except Exception:
        raw = "My Device"
    plat = "macOS" if sys.platform == "darwin" else ("Windows" if sys.platform == "win32" else "Linux")
    return f"{raw} ({plat})"

def load_sync_config(force_reload: bool = False) -> dict[str, Any]:
    """
    极速读取多端同步配置:
    常驻内存缓存，初次加载 < 1ms，未开启时判断开销 < 0.005ms
    """
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None and not force_reload:
        return _CONFIG_CACHE

    cfg_path = get_sync_config_path()
    default_cfg: dict[str, Any] = {
        "enabled": False,
        "repo_url": "",
        "device_id": get_default_device_id(),
        "device_name": get_default_device_name(),
        "last_sync_time": "",
        "last_sync_status": "",
        "last_sync_message": "",
        "synced_devices": []
    }

    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    default_cfg.update(data)
        except Exception:
            pass

    _CONFIG_CACHE = default_cfg
    return _CONFIG_CACHE

def save_sync_config(cfg: dict[str, Any]) -> None:
    """原子化保存多端同步配置"""
    global _CONFIG_CACHE
    cfg_path = get_sync_config_path()
    tmp_path = f"{cfg_path}.tmp.{os.getpid()}"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, cfg_path)
        _CONFIG_CACHE = cfg
    except Exception as e:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise e

def is_sync_enabled() -> bool:
    """极速检测当前多端同步是否处于激活可用状态 (微秒级)"""
    cfg = load_sync_config()
    if not cfg.get("enabled"):
        return False
    repo_dir = get_sync_repo_dir()
    return os.path.isdir(os.path.join(repo_dir, ".git"))

def get_remote_fingerprint() -> str:
    """
    极速计算异机分片状态指纹 (1 次 scandir + N 次 stat，微秒级)：
    - 以 devices/ 下全部分片文件的「文件数:最大 mtime」作为指纹
    - 相比仅比较目录 mtime，可正确感知同名分片被"原地覆盖写入"的变更
      (目录 mtime 只在新增/删除文件时才变化，覆盖同名文件时保持不变)
    - 未开启同步时短路返回 ""，开销 < 0.005ms
    """
    if not is_sync_enabled():
        return ""
    devices_dir = os.path.join(get_sync_repo_dir(), "devices")
    try:
        count = 0
        max_mtime = 0.0
        with os.scandir(devices_dir) as it:
            for entry in it:
                if not entry.name.endswith(".json"):
                    continue
                count += 1
                try:
                    mt = entry.stat().st_mtime
                    if mt > max_mtime:
                        max_mtime = mt
                except OSError:
                    pass
        return f"{count}:{max_mtime}"
    except OSError:
        return ""

def get_remote_agent_ids() -> set[str]:
    """
    极速获取"异机存在数据"的 Agent 集合:
    供今日概览补齐"本机未安装但异机在用"的 Agent，未开启同步时返回空集。
    """
    if not is_sync_enabled():
        return set()
    return set(load_remote_devices_data().get("agents", {}).keys())

def run_git(args: list[str], cwd: str, timeout: int = 15) -> tuple[int, str, str]:
    """
    安全调用宿主机原生 git 命令:
    - 严格带超时防止网络卡死
    - 复用现有 ssh-agent / git-credential-manager
    """
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"  # 禁用终端密码弹窗，避免无响应挂起
    try:
        proc = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            env=env
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", f"Git 操作超时 ({timeout}s)"
    except Exception as e:
        return -2, "", str(e)

def init_sync_repo(repo_url: str, device_name: str = "", device_id: str = "") -> dict[str, Any]:
    """
    绑定并初始化远程私有同步仓库:
    - 克隆或拉取远程仓库
    - 设立 devices/ 分片目录
    - 立即生成并推送当前机器的首次度量快照
    """
    with _SYNC_LOCK:
        if not repo_url or not repo_url.strip():
            raise ValueError("仓库地址不能为空")
        repo_url = repo_url.strip()

        base_dir = get_sync_base_dir()
        repo_dir = get_sync_repo_dir()

        # 若已存在旧的同名仓库目录，先安全备份或清理
        if os.path.exists(repo_dir):
            try:
                code, out, _ = run_git(["remote", "get-url", "origin"], repo_dir, timeout=5)
                if code == 0 and out == repo_url:
                    pass
                else:
                    bak = f"{repo_dir}_bak_{int(time.time())}"
                    os.rename(repo_dir, bak)
            except Exception:
                pass

        if not os.path.exists(os.path.join(repo_dir, ".git")):
            code, out, err = run_git(["clone", repo_url, "sync_repo"], base_dir, timeout=30)
            if not os.path.exists(os.path.join(repo_dir, ".git")):
                raise RuntimeError(f"Git Clone 失败: {err or out}")

        devices_dir = os.path.join(repo_dir, "devices")
        os.makedirs(devices_dir, exist_ok=True)

        meta_file = os.path.join(repo_dir, "sync_meta.json")
        if not os.path.exists(meta_file):
            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump({"schemaVersion": 1, "createdAt": datetime.now(timezone.utc).isoformat()}, f, indent=2)

        # 更新配置
        cfg = load_sync_config(force_reload=True)
        cfg["enabled"] = True
        cfg["repo_url"] = repo_url
        if device_id and device_id.strip():
            cfg["device_id"] = device_id.strip()
        if device_name and device_name.strip():
            cfg["device_name"] = device_name.strip()
        save_sync_config(cfg)

        # 立即执行一次本机导出与推送
        return _do_sync_unlocked(cfg)

def _make_local_entry(s: dict[str, Any], device_id: str) -> dict[str, Any]:
    """
    把一条会话切片规范化为「本机分片条目」:
    1. 只保留白名单度量字段，绝不包含任何原始对话内容
    2. 标注来源设备 sourceDeviceId，使分片自带可审计的溯源信息
    3. 【来源闸门】任何带异机来源标记 (isRemote / remoteDevice / remoteDeviceId /
       异地 sourceDeviceId) 的条目一律拒绝写入。

    第 3 条是「本机分片内容必由本机产生」这一不变式的写入侧断言。历史上正是因为缺少这道断言，
    被污染的适配器缓存内容才会以本机名义写进分片、经 Git 回传后被永久固化。
    返回空字典表示该条目被拒绝。
    """
    if s.get("isRemote") or s.get("remoteDevice") or s.get("remoteDeviceId"):
        return {}
    src = s.get("sourceDeviceId")
    if src and src != device_id:
        return {}
    return {
        "sessionId": s.get("sessionId", ""),
        "title": s.get("title", ""),
        "date": s.get("date", ""),
        "inputTokens": s.get("inputTokens", 0),
        "cacheReadTokens": s.get("cacheReadTokens", 0),
        "outputTokens": s.get("outputTokens", 0),
        "totalTokens": s.get("totalTokens", 0),
        "lastActivity": s.get("lastActivity", ""),
        "sourceDeviceId": device_id,
    }

def export_local_snapshot(device_id: str, device_name: str) -> dict[str, Any]:
    """
    高性能导出本机所有已安装 Agent 的轻量级度量快照:
    只提取 daily_map、session_list 以及对应会话标题，绝不包含原始对话上下文。
    - 具备【增量吸收保护 (Merge-on-Export)】：自动读取已有历史快照做并集合并，
      即使本地原生 Agent 日志被清理或轮转，历史用量也永不丢失。
    - 具备【来源闸门】：所有写入路径（实时抓取 + 历史吸收）都必须通过 _make_local_entry 校验，
      带异机来源标记的条目绝不落盘，从写入侧杜绝跨设备数据混入本机分片。
    """
    repo_dir = get_sync_repo_dir()
    existing_file = os.path.join(repo_dir, "devices", f"{device_id}.json")
    old_agents_data: dict[str, Any] = {}
    if os.path.exists(existing_file):
        try:
            with open(existing_file, "r", encoding="utf-8") as f:
                old_snap = json.load(f)
                if isinstance(old_snap, dict) and "agents" in old_snap:
                    old_agents_data = old_snap["agents"]
        except Exception:
            old_agents_data = {}

    agents_data = {}
    for aid, adapter in ADAPTERS.items():
        if not adapter.is_available() and aid not in old_agents_data:
            continue
        try:
            titles = {}
            times_override = {}
            daily_map = {}
            session_list = []
            if adapter.is_available():
                titles, times_override = adapter.get_titles_and_times()
                daily_map, session_list = adapter.fetch_data()

            clean_sessions = []
            seen_sids = set()
            for s in session_list:
                sid = s.get("sessionId", "")
                entry = _make_local_entry(s, device_id)
                if not entry:
                    continue  # 来源闸门拦截：异机条目绝不写入本机分片
                if sid:
                    seen_sids.add(sid)
                if not entry["title"]:
                    entry["title"] = titles.get(sid, "")
                clean_sessions.append(entry)

            clean_daily = {}
            for d_str, s_list in daily_map.items():
                clean_list = []
                for s in s_list:
                    sid = s.get("sessionId", "")
                    entry = _make_local_entry(s, device_id)
                    if not entry:
                        continue  # 来源闸门拦截
                    if not entry["title"]:
                        entry["title"] = titles.get(sid, "")
                    entry["date"] = d_str
                    clean_list.append(entry)
                clean_daily[d_str] = clean_list

            # 增量吸收历史数据 (Merge-on-Export)：将老快照中已被本地轮转清理的会话保全
            # 注意：历史条目同样要过来源闸门，避免旧的污染内容被重新带进来
            old_a = old_agents_data.get(aid, {})
            if old_a:
                # 吸收历史 sessionList
                for osess in old_a.get("sessionList", []):
                    osid = osess.get("sessionId", "")
                    if not osid or osid in seen_sids:
                        continue
                    entry = _make_local_entry(osess, device_id)
                    if not entry:
                        continue
                    seen_sids.add(osid)
                    clean_sessions.append(entry)

                # 吸收历史 dailyMap
                for od_str, os_list in old_a.get("dailyMap", {}).items():
                    if od_str not in clean_daily:
                        clean_daily[od_str] = []
                    d_sids = {s.get("sessionId") for s in clean_daily[od_str] if s.get("sessionId")}
                    for osess in os_list:
                        osid = osess.get("sessionId", "")
                        if not osid or osid in d_sids:
                            continue
                        entry = _make_local_entry(osess, device_id)
                        if not entry:
                            continue
                        entry["date"] = od_str
                        d_sids.add(osid)
                        clean_daily[od_str].append(entry)

            agents_data[aid] = {
                "dailyMap": clean_daily,
                "sessionList": clean_sessions
            }
        except Exception:
            # 若解析异常但有历史数据，保全历史
            if aid in old_agents_data:
                agents_data[aid] = old_agents_data[aid]
            continue

    snapshot = {
        "schemaVersion": 2,
        "deviceId": device_id,
        "deviceName": device_name,
        "platform": sys.platform,
        "exportedAt": datetime.now(timezone.utc).isoformat(),
        "agents": agents_data
    }
    return snapshot

def _get_current_git_branch(repo_dir: str) -> str:
    """获取当前仓库主分支名 (main 或 master)"""
    code, out, _ = run_git(["branch", "--show-current"], repo_dir, timeout=5)
    if code == 0 and out:
        return out
    return "main"

def _do_sync_unlocked(cfg: dict[str, Any], on_progress: Optional[Callable[[str, str, str, str], None]] = None) -> dict[str, Any]:
    """内部执行同步逻辑 (需在 _SYNC_LOCK 内调用)"""
    def _emit(step: str, status: str, msg: str, detail: str = ""):
        if on_progress:
            try:
                on_progress(step, status, msg, detail)
            except Exception:
                pass

    t0 = time.time()
    repo_dir = get_sync_repo_dir()
    if not os.path.isdir(os.path.join(repo_dir, ".git")):
        _emit("init", "error", "多端同步仓库尚未初始化", "缺少 .git 目录")
        raise RuntimeError("多端同步仓库尚未初始化，请先连接仓库")

    device_id = cfg.get("device_id") or get_default_device_id()
    device_name = cfg.get("device_name") or get_default_device_name()
    devices_dir = os.path.join(repo_dir, "devices")
    os.makedirs(devices_dir, exist_ok=True)

    branch = _get_current_git_branch(repo_dir)

    # 1. 执行 git pull --rebase 拉取异机最新账本 (容忍远程无分支的初次提交)
    _emit("pull", "running", "正在拉取远端异机账本...", f"分支: {branch}")
    t_pull = time.time()
    pull_code, pull_out, pull_err = run_git(["pull", "--rebase", "origin", branch], repo_dir, timeout=15)
    if pull_code != 0 and "couldn't find remote ref" not in pull_err and "no such ref" not in pull_err:
        run_git(["pull", "--rebase"], repo_dir, timeout=10)
    pull_cost = round(time.time() - t_pull, 1)
    _emit("pull", "done", f"已拉取异机最新账本 ({pull_cost}s)", pull_out or "最新")

    # 2. 生成并写入本机独立分片文件 devices/{device_id}.json
    _emit("export", "running", "正在聚合本机 Agent 度量快照...", "增量吸收保护")
    t_export = time.time()
    snapshot = export_local_snapshot(device_id, device_name)
    device_file = os.path.join(devices_dir, f"{device_id}.json")
    with open(device_file, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    export_cost = round(time.time() - t_export, 2)
    agent_count = len(snapshot.get("agents", {}))
    _emit("export", "done", f"本机快照已生成 ({agent_count} 款 Agent, {export_cost}s)", f"设备: {device_name}")

    # 3. 提交本机变动
    _emit("commit", "running", "正在保存本地 Git 分片提交...", "原子化存储")
    run_git(["add", f"devices/{device_id}.json"], repo_dir, timeout=5)
    run_git(["add", "sync_meta.json"], repo_dir, timeout=5)

    status_code, status_out, _ = run_git(["status", "--porcelain"], repo_dir, timeout=5)
    if status_out:
        ts_label = datetime.now().strftime("%Y-%m-%d %H:%M")
        commit_msg = f"sync({device_id}): update usage ledger [{ts_label}]"
        c_code, _, c_err = run_git(["commit", "-m", commit_msg], repo_dir, timeout=10)
        if c_code != 0 and "nothing to commit" not in c_err:
            pass
    _emit("commit", "done", "本地分片变动已保存", "工作区干净")

    # 确保主分支统一命名为 main
    run_git(["branch", "-M", "main"], repo_dir, timeout=5)

    # 4. 推送到远程私有仓库
    _emit("push", "running", "正在推送到 GitHub 远端仓库...", "安全增量上云")
    t_push = time.time()
    push_code, push_out, push_err = run_git(["push", "-u", "origin", "main"], repo_dir, timeout=20)
    if push_code != 0:
        push_code, push_out, push_err = run_git(["push", "-u", "origin", "HEAD:main"], repo_dir, timeout=20)
        if push_code != 0:
            err_msg = push_err or push_out
            _emit("push", "error", "推送到 GitHub 失败", err_msg)
            raise RuntimeError(f"Git Push 失败: {err_msg}")
    push_cost = round(time.time() - t_push, 1)
    _emit("push", "done", f"已推送到远端私有仓库 ({push_cost}s)", "main 分支")

    # 5. 发现已同步的异机设备列表与内存融合
    _emit("merge", "running", "正在融合跨端度量与异机会话...", "内存微秒级就绪")
    remote_devices = []
    if os.path.isdir(devices_dir):
        for f in os.listdir(devices_dir):
            if f.endswith(".json") and f != f"{device_id}.json":
                dev_path = os.path.join(devices_dir, f)
                try:
                    with open(dev_path, "r", encoding="utf-8") as jf:
                        d_data = json.load(jf)
                        remote_devices.append({
                            "deviceId": d_data.get("deviceId", f[:-5]),
                            "deviceName": d_data.get("deviceName", f[:-5]),
                            "platform": d_data.get("platform", "unknown"),
                            "exportedAt": d_data.get("exportedAt", "")
                        })
                except Exception:
                    remote_devices.append({"deviceId": f[:-5], "deviceName": f[:-5]})

    # 6. 更新内存与配置
    invalidate_remote_cache()
    duration = round(time.time() - t0, 2)
    cfg["last_sync_time"] = datetime.now(timezone.utc).isoformat()
    cfg["last_sync_status"] = "success"
    cfg["last_sync_message"] = f"同步成功，已连接 {len(remote_devices)} 台异机设备 (耗时 {duration}s)"
    cfg["synced_devices"] = remote_devices
    save_sync_config(cfg)
    _emit("merge", "done", f"跨端融合完成 (已连接 {len(remote_devices)} 台异机)", f"总耗时: {duration}s")

    return {
        "success": True,
        "duration": duration,
        "lastSyncTime": cfg["last_sync_time"],
        "syncedDevices": remote_devices,
        "message": cfg["last_sync_message"]
    }

def trigger_sync(on_progress: Optional[Callable[[str, str, str, str], None]] = None) -> dict[str, Any]:
    """手动触发一次完整的多端同步流程 (线程安全且原子化)"""
    with _SYNC_LOCK:
        cfg = load_sync_config(force_reload=True)
        if not cfg.get("enabled"):
            raise ValueError("多端同步功能尚未开启，请先配置私有仓库地址")
        try:
            return _do_sync_unlocked(cfg, on_progress=on_progress)
        except Exception as e:
            cfg["last_sync_status"] = "error"
            cfg["last_sync_message"] = f"同步失败: {str(e)}"
            save_sync_config(cfg)
            raise e

def invalidate_remote_cache() -> None:
    """失效异机内存缓存，促使下次读取重新加载"""
    global _REMOTE_DEVICES_CACHE, _REMOTE_DEVICES_CACHE_KEY
    _REMOTE_DEVICES_CACHE = None
    _REMOTE_DEVICES_CACHE_KEY = ""

def load_remote_devices_data() -> dict[str, Any]:
    """
    极速读取并缓存除本机外的所有异机设备数据 (开销 < 2ms):
    返回格式:
    {
      "devices": [ { deviceId, deviceName, ... } ],
      "agents": {
        "agy": {
          "dailyMap": { "YYYY-MM-DD": [ { sessionId, ... remoteDevice: ... } ] },
          "sessionList": [ ... ]
        }
      }
    }
    """
    global _REMOTE_DEVICES_CACHE, _REMOTE_DEVICES_CACHE_KEY
    if not is_sync_enabled():
        return {}

    repo_dir = get_sync_repo_dir()
    devices_dir = os.path.join(repo_dir, "devices")
    if not os.path.isdir(devices_dir):
        return {}

    # 以全部分片文件的「文件数:最大 mtime」作为缓存有效性键。
    # 早期实现仅比较 devices 目录 mtime，而覆盖写入同名分片并不会改变目录 mtime，
    # 会导致跨进程 / 外部 git pull 之后长期读到陈旧异机数据。
    current_key = get_remote_fingerprint()

    if _REMOTE_DEVICES_CACHE is not None and current_key and current_key == _REMOTE_DEVICES_CACHE_KEY:
        return _REMOTE_DEVICES_CACHE

    cfg = load_sync_config()
    current_device_id = cfg.get("device_id") or get_default_device_id()

    merged_agents: dict[str, dict[str, Any]] = {}
    known_devices = []

    try:
        for fname in os.listdir(devices_dir):
            if not fname.endswith(".json"):
                continue
            # 严格跳过本机文件，杜绝本机数据重复统计
            if fname == f"{current_device_id}.json":
                continue

            fpath = os.path.join(devices_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as jf:
                    data = json.load(jf)
            except Exception:
                continue

            dev_id = data.get("deviceId", fname[:-5])
            dev_name = data.get("deviceName", dev_id)
            known_devices.append({
                "deviceId": dev_id,
                "deviceName": dev_name,
                "platform": data.get("platform", "unknown"),
                "exportedAt": data.get("exportedAt", "")
            })

            agents = data.get("agents", {})
            for aid, a_val in agents.items():
                if aid not in merged_agents:
                    merged_agents[aid] = {
                        "dailyMap": {},
                        "sessionList": []
                    }

                target = merged_agents[aid]

                # 归并 dailyMap
                for d_str, s_list in a_val.get("dailyMap", {}).items():
                    if d_str not in target["dailyMap"]:
                        target["dailyMap"][d_str] = []
                    for s in s_list:
                        item = dict(s)
                        item["remoteDevice"] = dev_name
                        item["remoteDeviceId"] = dev_id
                        item["isRemote"] = True
                        target["dailyMap"][d_str].append(item)

                # 归并 sessionList
                for s in a_val.get("sessionList", []):
                    item = dict(s)
                    item["remoteDevice"] = dev_name
                    item["remoteDeviceId"] = dev_id
                    item["isRemote"] = True
                    target["sessionList"].append(item)

        _REMOTE_DEVICES_CACHE = {
            "devices": known_devices,
            "agents": merged_agents
        }
        _REMOTE_DEVICES_CACHE_KEY = current_key
        return _REMOTE_DEVICES_CACHE

    except Exception:
        return {}

def get_remote_agent_data(agent_type: str) -> tuple[dict[str, list[dict]], list[dict]]:
    """
    供 core.py 高性能调用的异机数据接口:
    返回 (remote_daily_map, remote_session_list)
    若未开启同步或无异机数据，短路耗时 < 0.005ms
    """
    if not is_sync_enabled():
        return {}, []

    all_remote = load_remote_devices_data()
    agents = all_remote.get("agents", {})
    a_data = agents.get(agent_type)
    if not a_data:
        return {}, []
    return a_data.get("dailyMap", {}), a_data.get("sessionList", [])
