"""scan_files_fast 短 TTL 记忆化回归测试（性能修复方案 1）。

验证：TTL 内复用遍历、TTL 过期重扫、today_only 剪枝、缓存键隔离、返回副本不污染缓存。
"""
import os
import time

import pytest

import myccusage_lib.adapters.base as B


@pytest.fixture(autouse=True)
def _clear_scan_cache():
    B._SCAN_CACHE.clear()
    yield
    B._SCAN_CACHE.clear()


def _touch(path, mtime=None):
    path.write_text("x", encoding="utf-8")
    if mtime is not None:
        os.utime(path, (mtime, mtime))


def _count_scandir(monkeypatch):
    real = os.scandir
    calls = {"n": 0}

    def counting(path):
        calls["n"] += 1
        return real(path)

    monkeypatch.setattr(B.os, "scandir", counting)
    return calls


def test_memo_reuses_within_ttl(tmp_path, monkeypatch):
    _touch(tmp_path / "a.jsonl")
    calls = _count_scandir(monkeypatch)
    r1 = B.scan_files_fast([str(tmp_path)], extensions=(".jsonl",))
    r2 = B.scan_files_fast([str(tmp_path)], extensions=(".jsonl",))
    assert r1 == r2
    assert calls["n"] == 1  # 第二次命中缓存，未重新遍历


def test_refresh_after_ttl(tmp_path, monkeypatch):
    _touch(tmp_path / "a.jsonl")
    monkeypatch.setattr(B, "_SCAN_CACHE_TTL", 0.0)
    calls = _count_scandir(monkeypatch)
    B.scan_files_fast([str(tmp_path)], extensions=(".jsonl",))
    B.scan_files_fast([str(tmp_path)], extensions=(".jsonl",))
    assert calls["n"] == 2  # TTL=0 → 每次重扫


def test_today_only_prunes_cold_files(tmp_path):
    now = time.time()
    _touch(tmp_path / "cold.jsonl", now - 86400 * 2)
    _touch(tmp_path / "hot.jsonl", now)
    hot = B.scan_files_fast([str(tmp_path)], extensions=(".jsonl",), today_only=True)
    assert [os.path.basename(p) for p in hot] == ["hot.jsonl"]
    allf = B.scan_files_fast([str(tmp_path)], extensions=(".jsonl",), today_only=False)
    assert len(allf) == 2


def test_cache_key_isolation(tmp_path):
    _touch(tmp_path / "a.jsonl")
    _touch(tmp_path / "b.db")
    j = B.scan_files_fast([str(tmp_path)], extensions=(".jsonl",))
    d = B.scan_files_fast([str(tmp_path)], extensions=(".db",))
    assert [os.path.basename(p) for p in j] == ["a.jsonl"]
    assert [os.path.basename(p) for p in d] == ["b.db"]


def test_returns_copy_not_cached_ref(tmp_path):
    _touch(tmp_path / "a.jsonl")
    r1 = B.scan_files_fast([str(tmp_path)], extensions=(".jsonl",))
    r1.clear()  # 调用方 mutate 返回值不得污染缓存
    r2 = B.scan_files_fast([str(tmp_path)], extensions=(".jsonl",))
    assert len(r2) == 1