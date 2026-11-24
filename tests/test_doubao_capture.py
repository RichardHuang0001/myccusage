"""doubao_capture 采集引擎单元测试（临时目录 + 合成 WAL，不依赖活体豆包库）。

覆盖：关闭态零操作、增量固化、去重取最大、指纹幂等、重启续读不丢不重。
"""

import os
import json
import struct

import pytest

from myccusage_lib.adapters import doubao_capture as DC
from myccusage_lib import idbcodec as C


def _frame(typ: int, payload: bytes) -> bytes:
    return struct.pack("<IHB", 0, len(payload), typ) + payload


def _usage_blob(mid: str, msg: int = 200, conv: str = "38456109709267458",
                ts: int = 1763970000000) -> bytes:
    js = ('{"system_prompt":100,"messages":%d,"skills":10,"tools":300,"total_window_size":300000}'
          % msg)
    parts = [
        b'message_id"' + bytes([len(mid)]) + mid.encode(),
        b'context_window_usage"' + bytes([len(js)]) + js.encode(),
        b'conversation_id"' + bytes([len(conv)]) + conv.encode(),
        b'model_id"\x0238',
        b'create_time_msN' + struct.pack("<d", float(ts)),
    ]
    return b" ".join(parts)


MID_A = "8b19a730-e7e4-11f1-a4cc-35d422d7b591"
MID_B = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


@pytest.fixture
def env(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    cfg = tmp_path / "config"
    cfg.mkdir()
    src = tmp_path / "src"
    src.mkdir()
    monkeypatch.setattr(DC, "CACHE_DIR", str(cache))
    monkeypatch.setattr(DC, "CONFIG_DIR", str(cfg))
    monkeypatch.setattr(DC, "JOURNAL", str(cache / "doubao_journal.jsonl"))
    monkeypatch.setattr(DC, "STATE", str(cache / "doubao_state.json"))
    monkeypatch.setattr(DC, "CONFIG", str(cfg / "doubao_config.json"))
    monkeypatch.setattr(DC, "_source_dirs", lambda: [str(src)])
    DC._reset()
    monkeypatch.setattr(DC, "_enabled", True)
    return src


def _append_wal(src, blob: bytes, name: str = "000001.log"):
    p = src / name
    old = p.read_bytes() if p.exists() else b""
    p.write_bytes(old + _frame(1, blob))


def _lines():
    if not os.path.exists(DC.JOURNAL):
        return []
    with open(DC.JOURNAL, encoding="utf-8") as f:
        return [json.loads(x) for x in f]


def test_disabled_zero_op(env, monkeypatch):
    monkeypatch.setattr(DC, "_enabled", False)
    _append_wal(env, _usage_blob(MID_A))
    DC.tick()  # 非 force，关闭态
    assert not os.path.exists(DC.JOURNAL)


def test_capture_and_dedup_max(env):
    _append_wal(env, _usage_blob(MID_A, msg=200))
    DC.tick(force=True)
    usage = [x for x in _lines() if x["type"] == "usage"]
    assert len(usage) == 1
    assert usage[0]["context_total"] == 610
    # 同轮更大快照 → 更新为最大版
    _append_wal(env, _usage_blob(MID_A, msg=900))
    DC.tick(force=True)
    assert DC._usage[MID_A]["context_total"] == 1310


def test_smaller_snapshot_ignored(env):
    _append_wal(env, _usage_blob(MID_A, msg=900))
    DC.tick(force=True)
    n_before = len(_lines())
    _append_wal(env, _usage_blob(MID_A, msg=200))  # 更小版本
    DC.tick(force=True)
    assert DC._usage[MID_A]["context_total"] == 1310
    assert len(_lines()) == n_before  # 不追加


def test_fingerprint_idempotent(env):
    _append_wal(env, _usage_blob(MID_A))
    DC.tick(force=True)
    n_before = len(_lines())
    DC._last_tick = 0.0  # 解除节流
    DC.tick()  # 非 force，指纹未变 → 短路
    assert len(_lines()) == n_before


def test_restart_resume_no_dup(env):
    _append_wal(env, _usage_blob(MID_A))
    _append_wal(env, _usage_blob(MID_B))
    DC.tick(force=True)
    n_before = len(_lines())
    usage_before = [x for x in _lines() if x["type"] == "usage"]
    assert len(usage_before) == 2  # 另有 1 行会话元数据
    # 模拟 daemon 重启：清空内存态，从 journal/state 懒加载
    DC._reset()
    DC._last_tick = 0.0
    DC.tick()  # 指纹已持久化 → 短路，不重复固化
    assert len(_lines()) == n_before
    assert len(DC._usage) == 2


def test_two_rounds(env):
    _append_wal(env, _usage_blob(MID_A))
    _append_wal(env, _usage_blob(MID_B))
    DC.tick(force=True)
    assert len(DC._usage) == 2
    st = DC.get_status()
    assert st["capturedRounds"] == 2
    assert st["enabled"] is True


# ---------------------------------------------------------------------------
# P4 边界加固
# ---------------------------------------------------------------------------
MID_C = "cccccccc-bbbb-cccc-dddd-eeeeeeeeeeee"


def _venc(v: int) -> bytes:
    out = bytearray()
    while True:
        b = v & 0x7F
        v >>= 7
        out.append(b | (0x80 if v else 0))
        if not v:
            return bytes(out)


def _make_ldb(blob: bytes) -> bytes:
    """构造含单个 raw 数据块（内容=blob）的最小合法 .ldb。"""
    out = bytearray()
    out += blob + b"\x00" + b"\x00\x00\x00\x00"  # data block + trailer(type0)
    handle = _venc(0) + _venc(len(blob))
    body = bytearray()
    body += _venc(0) + _venc(1) + _venc(len(handle)) + b"z" + handle
    body += struct.pack("<I", 0) + struct.pack("<I", 1)  # restart array
    index = bytes(body)
    idx_off = len(out)
    out += index + b"\x00" + b"\x00\x00\x00\x00"
    footer = bytearray()
    footer += _venc(0) + _venc(0)
    footer += _venc(idx_off) + _venc(len(index))
    footer += b"\x00" * (40 - len(footer))
    footer += C._TABLE_MAGIC
    out += footer
    return bytes(out)


def test_rotation_catchup(env):
    _append_wal(env, _usage_blob(MID_A), "000001.log")
    DC.tick(force=True)
    assert MID_A in DC._usage
    # 轮换：旧 WAL 消失，数据压入新 .ldb
    (env / "000001.log").unlink()
    (env / "000002.ldb").write_bytes(_make_ldb(_usage_blob(MID_B)))
    DC.tick(force=True)
    assert MID_B in DC._usage  # 冷路径追平捕获
    assert not any("000001.log" in k for k in DC._state["files"])  # 已清理


def test_multi_profile(env, monkeypatch):
    src2 = env.parent / "src2"
    src2.mkdir()
    monkeypatch.setattr(DC, "_source_dirs", lambda: [str(env), str(src2)])
    _append_wal(env, _usage_blob(MID_A))
    _append_wal(src2, _usage_blob(MID_B))
    DC.tick(force=True)
    assert MID_A in DC._usage and MID_B in DC._usage


def test_journal_compaction(env, monkeypatch):
    monkeypatch.setattr(DC, "_COMPACT_SLACK", 2)
    _append_wal(env, _usage_blob(MID_A))
    _append_wal(env, _usage_blob(MID_B))
    DC.tick(force=True)
    # 制造重复行冗余（模拟重叠/轮换导致的重复追加）
    dup = [x for x in _lines() if x["type"] == "usage"][0]
    with open(DC.JOURNAL, "a", encoding="utf-8") as f:
        for _ in range(5):
            f.write(json.dumps(dup, ensure_ascii=False) + "\n")
    DC._journal_lines += 5
    _append_wal(env, _usage_blob(MID_C))
    DC.tick(force=True)  # 冗余超阈值 → 压实
    assert len(_lines()) == len(DC._usage) + len(DC._meta)
    assert {x["message_id"] for x in _lines() if x["type"] == "usage"} == {MID_A, MID_B, MID_C}


def test_config_hot_switch(env):
    DC.set_enabled(True)
    assert DC._enabled is True
    assert json.load(open(DC.CONFIG))["enabled"] is True
    DC.set_enabled(False)
    assert DC._enabled is False
    assert json.load(open(DC.CONFIG))["enabled"] is False


def test_corrupted_ldb_tolerated(env):
    _append_wal(env, _usage_blob(MID_A))
    # 损坏的 .ldb：合法 magic 但内容截断，不得让整个 tick 崩溃
    (env / "000009.ldb").write_bytes(b"\x00" * 40 + C._TABLE_MAGIC)
    DC.tick(force=True)
    assert MID_A in DC._usage  # 正常数据仍捕获