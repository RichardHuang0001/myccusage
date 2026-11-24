"""doubao 适配器单元测试（合成固化账本，不依赖活体豆包库）。

覆盖：8 元组聚合、模型维度守恒不变式、unknown 模型归属、标题映射、
insights 口径与 gaps、today_only 剪枝。
"""

import os
import json
import time
from datetime import datetime

import pytest

from myccusage_lib.adapters import doubao_capture as DC
from myccusage_lib.adapters.doubao import DoubaoAdapter
from myccusage_lib.adapters.base import UNKNOWN_MODEL


def _usage(mid, cid, ts, sp=100, msg=200, sk=10, tool=300, tw=300000, model="38"):
    return {
        "type": "usage", "message_id": mid, "conversation_id": cid,
        "create_time_ms": ts, "system_prompt": sp, "messages": msg,
        "skills": sk, "tools": tool, "total_window_size": tw,
        "context_total": sp + msg + sk + tool, "model_id": model,
        "captured_at": ts,
    }


def _meta(cid, name):
    return {"type": "meta", "conversation_id": cid, "name": name, "captured_at": int(time.time() * 1000)}


@pytest.fixture
def adapter(tmp_path, monkeypatch):
    journal = tmp_path / "doubao_journal.jsonl"
    monkeypatch.setattr(DC, "JOURNAL", str(journal))
    monkeypatch.setattr(DC, "STATE", str(tmp_path / "doubao_state.json"))
    return DoubaoAdapter(), journal


def _write(journal, objs):
    with open(journal, "w", encoding="utf-8") as f:
        for o in objs:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")


def _today_ms():
    now = datetime.now()
    return int(now.replace(hour=12, minute=0, second=0, microsecond=0).timestamp() * 1000)


def test_aggregate_and_model_invariant(adapter):
    ad, j = adapter
    ts = _today_ms()
    cid = "38456109709267458"
    _write(j, [
        _usage("mid-1", cid, ts, msg=200),
        _usage("mid-2", cid, ts + 1000, msg=900),
        _meta(cid, "测试会话"),
    ])
    daily, sessions = ad.fetch_data()
    day = datetime.now().strftime("%Y-%m-%d")
    assert day in daily
    assert len(daily[day]) == 1  # 同会话同日合并
    s = daily[day][0]
    assert s["totalTokens"] == 610 + 1310
    assert s["inputTokens"] == 610 + 1310
    assert s["outputTokens"] == 0 and s["cacheReadTokens"] == 0
    assert len(sessions) == 1
    # 模型维度守恒不变式
    assert sum(m["totalTokens"] for m in s["models"].values()) == s["totalTokens"]
    assert UNKNOWN_MODEL in s["models"]
    assert s["models"][UNKNOWN_MODEL]["calls"] == 2


def test_dedup_max_snapshot(adapter):
    ad, j = adapter
    ts = _today_ms()
    cid = "c1"
    _write(j, [
        _usage("mid-1", cid, ts, msg=200),
        _usage("mid-1", cid, ts, msg=900),  # 同轮更大快照
    ])
    daily, sessions = ad.fetch_data()
    assert sessions[0]["totalTokens"] == 1310  # 取最大，不重复累加


def test_titles_from_meta(adapter):
    ad, j = adapter
    ts = _today_ms()
    _write(j, [_usage("m", "c1", ts), _meta("c1", "我的豆包会话")])
    titles, times = ad.get_titles_and_times()
    assert titles["c1"] == "我的豆包会话"
    assert "c1" in times


def test_today_only_pruning(adapter):
    ad, j = adapter
    today = _today_ms()
    old = today - 86400000 * 3  # 三天前
    _write(j, [_usage("m1", "c1", today), _usage("m2", "c2", old)])
    daily_today, _ = ad.fetch_data(today_only=True)
    daily_all, _ = ad.fetch_data(today_only=False)
    assert sum(len(v) for v in daily_today.values()) == 1
    assert sum(len(v) for v in daily_all.values()) == 2


def test_insights_gaps_and_composition(adapter):
    ad, j = adapter
    ts = _today_ms()
    _write(j, [_usage("m1", "c1", ts, sp=100, msg=200, sk=10, tool=300), _meta("c1", "会话")])
    ins = ad.get_insights()
    assert ins["available"] is True
    assert ins["kind"] == "capture"
    assert ins["totals"]["rounds"] == 1
    assert ins["contextComposition"] == {"system_prompt": 100, "messages": 200, "skills": 10, "tools": 300}
    assert ins["totals"]["totalTokens"] == 610
    assert len(ins["gaps"]) >= 4
    assert ins["modelIds"][0]["id"] == "38"


def test_empty_journal(adapter):
    ad, j = adapter
    _write(j, [])
    daily, sessions = ad.fetch_data()
    assert daily == {} and sessions == []
    ins = ad.get_insights()
    assert ins["available"] is True  # 数据根存在即可用
    assert ins["totals"]["rounds"] == 0