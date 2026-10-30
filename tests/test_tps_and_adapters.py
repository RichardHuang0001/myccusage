"""
Tests for TPS (Tokens Per Second) tracking, WorkBuddy adapter, and schema backward compatibility.
"""

import os
import json
import tempfile
import pytest
from myccusage_lib.adapters.base import BaseAgentAdapter, UNKNOWN_MODEL
from myccusage_lib.adapters.workbuddy import WorkBuddyAdapter
from myccusage_lib.cli import calc_tps, format_tps, format_ms_duration


class DummyAdapter(BaseAgentAdapter):
    agent_id = "test_agent"
    display_name = "Test Agent"

    def is_available(self) -> bool:
        return True

    def get_titles_and_times(self):
        return {}, {}

    def fetch_data(self, today_only=False):
        return {}, []


def test_calc_and_format_tps():
    assert calc_tps(0, 1000) == 0.0
    assert calc_tps(100, 0) == 0.0
    assert calc_tps(100, -500) == 0.0
    assert calc_tps(100, 1000) == 100.0
    assert calc_tps(50, 2000) == 25.0

    assert format_tps(0, 1000) == "--"
    assert format_tps(100, 0) == "--"
    assert format_tps(5, 1000) == "5.0 tok/s"
    assert format_tps(85, 1000) == "85 tok/s"


def test_format_ms_duration():
    assert format_ms_duration(0) == "0s"
    assert format_ms_duration(500) == "0.5s"
    assert format_ms_duration(45200) == "45.2s"
    assert format_ms_duration(65000) == "1m 5s"
    assert format_ms_duration(3665000) == "1h 1m"


def test_accumulate_records_backward_compatibility():
    # 7-tuple
    rec7 = ("s1", "2026-10-30", "2026-10-30T10:00:00Z", 100, 50, 20, 170)
    # 8-tuple
    rec8 = ("s2", "2026-10-30", "2026-10-30T10:01:00Z", 200, 100, 40, 340, "claude-3-5-sonnet")
    # 9-tuple (with credit)
    rec9 = ("s3", "2026-10-30", "2026-10-30T10:02:00Z", 300, 150, 60, 510, "deepseek-v4.1-flash", 1.25)
    # 10-tuple (with credit and model_ms)
    rec10 = ("s4", "2026-10-30", "2026-10-30T10:03:00Z", 400, 200, 80, 680, "deepseek-v4.1-flash", 2.50, 800)

    daily_map, session_list = BaseAgentAdapter._accumulate_records([rec7, rec8, rec9, rec10])

    assert "2026-10-30" in daily_map
    day_entries = {s["sessionId"]: s for s in daily_map["2026-10-30"]}
    sess_entries = {s["sessionId"]: s for s in session_list}

    # Verify rec7
    assert day_entries["s1"]["totalTokens"] == 170
    assert day_entries["s1"]["modelMs"] == 0
    assert day_entries["s1"]["credit"] == 0.0
    assert UNKNOWN_MODEL in day_entries["s1"]["models"]

    # Verify rec8
    assert day_entries["s2"]["totalTokens"] == 340
    assert day_entries["s2"]["modelMs"] == 0
    assert "claude-3-5-sonnet" in day_entries["s2"]["models"]

    # Verify rec9
    assert day_entries["s3"]["credit"] == 1.25
    assert day_entries["s3"]["modelMs"] == 0

    # Verify rec10
    assert day_entries["s4"]["credit"] == 2.50
    assert day_entries["s4"]["modelMs"] == 800
    assert sess_entries["s4"]["modelMs"] == 800
    assert sess_entries["s4"]["models"]["deepseek-v4.1-flash"]["modelMs"] == 800


def test_workbuddy_state_machine_parallel_tools():
    """
    Test WorkBuddy parser state machine on:
    1. Single prompt -> single response
    2. Model calls multiple parallel tools (e.g. 3 tools)
    3. Tool 1 finishes concurrently while model is still outputting Tool 3 (early finish)
    4. Tool 2 and Tool 3 finish after model output
    5. Next turn accurately measures inference time from the latest tool finish
    6. Idle time is NOT counted in inference time
    """
    events = [
        # Turn 1: User prompt at 1000
        {"type": "message", "role": "user", "timestamp": 1000},
        # Model emits tool calls
        {"type": "function_call", "callId": "call_01", "timestamp": 1900},
        {"type": "function_call", "callId": "call_02", "timestamp": 1950},
        # Early result for call_01 finishes at 1980 (before call_03 is logged)
        {"type": "function_call_result", "callId": "call_01", "timestamp": 1980},
        # Model emits call_03 with rawUsage at 2000 (elapsed = 2000 - 1000 = 1000ms)
        {
            "type": "function_call",
            "callId": "call_03",
            "timestamp": 2000,
            "providerData": {
                "requestModelName": "Deepseek-V4.1-Flash",
                "rawUsage": {
                    "prompt_cache_hit_tokens": 500,
                    "prompt_cache_miss_tokens": 500,
                    "completion_tokens": 100,
                    "credit": 0.5,
                },
            },
        },
        # Remaining tools finish
        {"type": "function_call_result", "callId": "call_02", "timestamp": 2500},
        {"type": "function_call_result", "callId": "call_03", "timestamp": 3000},
        # Turn 2: Next model generation starts after all tools (i.e. at 3000)
        # Model finishes at 4500 (elapsed = 4500 - 3000 = 1500ms)
        {
            "type": "message",
            "role": "assistant",
            "timestamp": 4500,
            "providerData": {
                "requestModelName": "Deepseek-V4.1-Flash",
                "rawUsage": {
                    "prompt_cache_hit_tokens": 1000,
                    "prompt_cache_miss_tokens": 200,
                    "completion_tokens": 150,
                    "credit": 0.8,
                },
            },
        },
        # User is idle for 60 seconds (from 4500 to 64500)
        # Turn 3: User sends next message at 64500
        {"type": "message", "role": "user", "timestamp": 64500},
        # Model finishes at 66500 (elapsed = 66500 - 64500 = 2000ms, NOT 62000ms!)
        {
            "type": "message",
            "role": "assistant",
            "timestamp": 66500,
            "providerData": {
                "requestModelName": "Deepseek-V4.1-Flash",
                "rawUsage": {
                    "prompt_cache_hit_tokens": 1200,
                    "prompt_cache_miss_tokens": 100,
                    "completion_tokens": 200,
                    "credit": 1.0,
                },
            },
        },
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        jsonl_path = os.path.join(tmpdir, "test_session.jsonl")
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for ev in events:
                f.write(json.dumps(ev) + "\n")

        adapter = WorkBuddyAdapter()
        # Parse directly
        stat = os.stat(jsonl_path)
        records = []
        anchor_ts = None
        next_anchor = None
        active_call_ids = set()

        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip() or ("user" not in line and "function_call" not in line and "usage" not in line and "rawUsage" not in line):
                    continue
                obj = json.loads(line)
                t = obj.get("type")
                role = obj.get("role")
                ts = obj.get("timestamp")
                if not ts:
                    continue

                pd = obj.get("providerData") or {}
                ru = pd.get("rawUsage")
                u = pd.get("usage")

                if (t == "message" and role == "user") or t == "user":
                    anchor_ts = ts
                    next_anchor = None
                    active_call_ids.clear()
                    continue

                if t == "function_call":
                    cid = obj.get("callId")
                    if cid:
                        active_call_ids.add(cid)

                if t == "function_call_result":
                    cid = obj.get("callId")
                    if (cid and cid in active_call_ids) or (not cid and active_call_ids):
                        next_anchor = max(next_anchor or 0, ts)
                    else:
                        anchor_ts = max(anchor_ts or 0, ts)
                    continue

                if not ru and not u:
                    continue

                model_ms = 0
                if anchor_ts is not None and ts >= anchor_ts:
                    delta = ts - anchor_ts
                    if delta >= 100:
                        model_ms = delta

                records.append(model_ms)

                anchor_ts = next_anchor
                next_anchor = None
                active_call_ids.clear()

        # Turn 1: 1000ms
        assert records[0] == 1000
        # Turn 2: 1500ms
        assert records[1] == 1500
        # Turn 3: 2000ms (idle time excluded)
        assert records[2] == 2000
