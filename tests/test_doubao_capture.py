"""doubao_capture 采集引擎单元测试（临时目录 + 合成 WAL，不依赖活体豆包库）。

覆盖：关闭态零操作、增量固化、去重取最大、指纹幂等、重启续读不丢不重。
"""

import os
import json
import struct

import pytest

from myccusage_lib.adapters import doubao_capture as DC


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