#!/usr/bin/env python3
"""
多端同步分片来源清洗工具 (Shard Provenance Repair)
====================================================
背景：
  v1.6.0 之前 core.get_daily_data() 在合并异机数据时会就地改写适配器 _full_cache 的列表对象，
  导致本机导出的分片文件混入了异机会话；由于 export_local_snapshot 的字段白名单不含
  isRemote / remoteDevice，来源标记在导出时被抹除，污染条目与本机数据在结构上无法区分，
  并经 Merge-on-Export 与 Git 双向回传被永久固化。

用法：
  python3 scripts/repair_shard_provenance.py            # 试运行（只报告，不写入）
  python3 scripts/repair_shard_provenance.py --apply    # 备份后执行清洗

清洗判定（保守优先，宁可不删）：
  1. 对"本机真值可覆盖的日期"：分片条目必须命中本机适配器真值，否则删除。
  2. 对"本机真值无法覆盖的日期"（本地日志已轮转清理）：无法验证，保留；
     但若同一 sessionId 同时出现在其他设备分片中，则可判定其来源为异机，删除。
  3. 其他设备的分片：条目若命中"本机真值"，说明它其实是本机会话被复制过去的，删除。
"""
from __future__ import annotations

import os
import sys
import json
import shutil
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from myccusage_lib.adapters import ADAPTERS                    # noqa: E402
from myccusage_lib.sync import (                               # noqa: E402
    get_sync_repo_dir,
    get_sync_base_dir,
    load_sync_config,
    get_default_device_id,
)


def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def dump_json(path: str, data) -> None:
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def build_local_truth() -> tuple[dict[str, dict[str, set[str]]], dict[str, set[str]]]:
    """建立本机真值: ({agent: {date: {sid}}}, {agent: {sid}})"""
    by_date: dict[str, dict[str, set[str]]] = {}
    all_sids: dict[str, set[str]] = {}
    for aid, adapter in ADAPTERS.items():
        if not adapter.is_available():
            continue
        try:
            daily_map, session_list = adapter.fetch_data()
            by_date[aid] = {
                d: {s.get("sessionId") for s in lst if s.get("sessionId")}
                for d, lst in daily_map.items()
            }
            all_sids[aid] = {s.get("sessionId") for s in session_list if s.get("sessionId")}
        except Exception as e:
            print(f"  [警告] {aid} 本机真值读取失败，跳过: {e}")
    return by_date, all_sids


def main() -> int:
    apply_mode = "--apply" in sys.argv

    cfg = load_sync_config(force_reload=True)
    local_id = cfg.get("device_id") or get_default_device_id()
    devices_dir = os.path.join(get_sync_repo_dir(), "devices")

    if not os.path.isdir(devices_dir):
        print(f"❌ 未找到分片目录: {devices_dir}")
        return 1

    shard_files = sorted(f for f in os.listdir(devices_dir) if f.endswith(".json"))
    print("=" * 78)
    print(f"  分片来源清洗 {'【试运行】' if not apply_mode else '【正式执行】'}")
    print(f"  本机设备 ID : {local_id}")
    print(f"  分片目录    : {devices_dir}")
    print(f"  分片文件    : {shard_files}")
    print("=" * 78)

    print("\n[1/4] 读取本机适配器真值...")
    truth_by_date, truth_all = build_local_truth()
    for aid in sorted(truth_by_date):
        print(f"    {aid:10} {len(truth_by_date[aid]):>3} 天 / {sum(len(v) for v in truth_by_date[aid].values()):>4} 条当日切片")

    # 预读全部分片，用于跨设备重复判定
    shards: dict[str, dict] = {}
    for fn in shard_files:
        try:
            shards[fn] = load_json(os.path.join(devices_dir, fn))
        except Exception as e:
            print(f"  [警告] 无法解析 {fn}: {e}")

    # 其他设备分片持有的 (agent, date, sid) 集合
    foreign_keys: set[tuple[str, str, str]] = set()
    for fn, snap in shards.items():
        if fn == f"{local_id}.json":
            continue
        for aid, av in (snap.get("agents") or {}).items():
            for d, lst in (av.get("dailyMap") or {}).items():
                for s in lst:
                    sid = s.get("sessionId")
                    if sid:
                        foreign_keys.add((aid, d, sid))
    foreign_sids: set[tuple[str, str]] = {(k[0], k[2]) for k in foreign_keys}  # (agent, sid)

    print("\n[2/4] 逐分片比对与判定...")
    report: dict[str, list[str]] = {}
    total_drop = 0

    for fn, snap in shards.items():
        is_local = fn == f"{local_id}.json"
        drops: list[str] = []
        agents = snap.get("agents") or {}

        for aid, av in agents.items():
            truth_dates = truth_by_date.get(aid, {})
            truth_sids = truth_all.get(aid, set())

            # --- dailyMap ---
            for d, lst in (av.get("dailyMap") or {}).items():
                keep = []
                for s in lst:
                    sid = s.get("sessionId", "")
                    tok = s.get("totalTokens", 0)
                    ok = True
                    reason = ""
                    if is_local:
                        if d in truth_dates:
                            # 本机日志仍在，该日切片以本机真值为准
                            if sid not in truth_dates[d]:
                                ok = False
                                reason = "本机真值的该日切片中不存在"
                        elif (aid, sid) in foreign_sids:
                            # 本机日志已轮转无法验证，但异机持有同名会话 → 判定为异机来源
                            ok = False
                            reason = "本机无可验证日志，且异机分片持有同名会话"
                    else:
                        if sid and sid in truth_sids:
                            ok = False
                            reason = "该会话经本机真值确认为本机所有"
                    if ok:
                        keep.append(s)
                    else:
                        total_drop += 1
                        drops.append(f"    - [{aid}] {d} {sid[:8]} {tok:>12,}  {str(s.get('title'))[:32]}  ← {reason}")
                av["dailyMap"][d] = keep

            # --- sessionList ---
            sl = av.get("sessionList")
            if isinstance(sl, list):
                keep = []
                for s in sl:
                    sid = s.get("sessionId", "")
                    ok = True
                    reason = ""
                    if is_local:
                        if sid and sid not in truth_sids and (aid, sid) in foreign_sids:
                            ok = False
                            reason = "本机真值不含该会话，且异机分片持有同名会话"
                    else:
                        if sid and sid in truth_sids:
                            ok = False
                            reason = "该会话经本机真值确认为本机所有"
                    if ok:
                        keep.append(s)
                    else:
                        total_drop += 1
                        drops.append(f"    - [{aid}] sessionList {sid[:8]} {s.get('totalTokens',0):>12,}  ← {reason}")
                av["sessionList"] = keep

        report[fn] = drops

    print("\n[3/4] 判定结果:")
    for fn in shard_files:
        print(f"  {fn}: 计划移除 {len(report.get(fn, []))} 条")
        for line in report.get(fn, [])[:40]:
            print(line)
        if len(report.get(fn, [])) > 40:
            print(f"    ... 其余 {len(report.get(fn, [])) - 40} 条略")

    if total_drop == 0:
        print("\n✅ 所有分片均已干净，无需清洗。")
        return 0

    if not apply_mode:
        print(f"\n【试运行结束】共待移除 {total_drop} 条。加 --apply 正式执行（会先自动备份）。")
        return 0

    # --- 备份 ---
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = os.path.join(get_sync_base_dir(), "backups", ts)
    os.makedirs(backup_dir, exist_ok=True)
    for fn in shard_files:
        shutil.copy2(os.path.join(devices_dir, fn), os.path.join(backup_dir, fn))
    print(f"\n[4/4] 已备份 {len(shard_files)} 个分片到:\n      {backup_dir}")

    for fn, snap in shards.items():
        dump_json(os.path.join(devices_dir, fn), snap)
        print(f"      已写回 {fn}")

    print(f"\n✅ 清洗完成：共移除 {total_drop} 条跨设备污染条目。")
    print("   下一步：cd ~/.config/myccusage/sync_repo && git add devices && git commit -m 'repair: 清洗分片跨设备污染' && git push")
    return 0


if __name__ == "__main__":
    sys.exit(main())
