"""idbcodec 解码内核单元测试（合成 fixture，不依赖活体豆包库）。

覆盖：Snappy raw block 已知向量、WAL 帧重组与撕裂尾、SSTable 往返、
结构化提取与自指回声拒绝。
"""

import struct

import pytest

from myccusage_lib import idbcodec as C


# ---------------------------------------------------------------------------
# Snappy raw block
# ---------------------------------------------------------------------------
def test_snappy_literal_only():
    # preamble=3, literal tag (3-1)<<2=0x08, "abc"
    assert C.snappy_decompress(b"\x03\x08abc") == b"abc"


def test_snappy_copy1_overlap():
    # "a" 然后 copy offset=1 length=5 → "aaaaaa"
    assert C.snappy_decompress(b"\x06\x00a\x05\x01") == b"aaaaaa"


def test_snappy_copy2():
    # "abc" 然后 copy2 offset=3 length=9 → "abcabcabcabc"
    assert C.snappy_decompress(b"\x0c\x08abc\x22\x03\x00") == b"abcabcabcabc"


def test_snappy_long_literal():
    payload = bytes(range(256)) * 3  # 768 字节，触发 >60 的多字节长度
    lit_len = len(payload)
    extra = lit_len - 1
    n_extra = 2 if extra > 255 else 1
    pre = bytearray()
    v = lit_len
    while True:
        b = v & 0x7F
        v >>= 7
        pre.append(b | (0x80 if v else 0))
        if not v:
            break
    tag = (60 + n_extra - 1) << 2  # 60→1 extra byte, 61→2 extra bytes
    block = bytes(pre) + bytes([tag]) + extra.to_bytes(n_extra, "little") + payload
    assert C.snappy_decompress(block) == payload


def test_snappy_length_mismatch_raises():
    with pytest.raises(ValueError):
        C.snappy_decompress(b"\x05\x08abc")  # 声明 5 实际 3


def test_snappy_bad_offset_raises():
    with pytest.raises(ValueError):
        C.snappy_decompress(b"\x06\x00a\x05\x05")  # offset 5 > 已有 1 字节


# ---------------------------------------------------------------------------
# WAL 帧
# ---------------------------------------------------------------------------
def _frame(typ: int, payload: bytes) -> bytes:
    return struct.pack("<IHB", 0, len(payload), typ) + payload


def test_wal_full_record():
    data = _frame(1, b"hello")
    recs = list(C.iter_wal_batches(data))
    assert recs == [(7 + 5, b"hello")]
    assert C.wal_complete_end(data) == 12


def test_wal_fragmented_record():
    data = _frame(2, b"aa") + _frame(3, b"bb") + _frame(4, b"cc")
    recs = list(C.iter_wal_batches(data))
    assert len(recs) == 1
    assert recs[0][1] == b"aabbcc"


def test_wal_torn_tail_stops():
    good = _frame(1, b"ok")
    torn = struct.pack("<IHB", 0, 99, 1) + b"short"  # 声明 99 实际不足
    data = good + torn
    assert C.wal_complete_end(data) == len(good)
    assert [p for _, p in C.iter_wal_batches(data)] == [b"ok"]


def test_wal_block_padding_skipped():
    # 在 32KB 块尾留 3 字节零填充，下一块放完整记录
    pad = b"\x00" * 3
    data = b"\x00" * (32768 - 3) + pad + _frame(1, b"next")
    recs = list(C.iter_wal_batches(data))
    assert [p for _, p in recs] == [b"next"]


# ---------------------------------------------------------------------------
# SSTable 往返
# ---------------------------------------------------------------------------
def _varint_enc(v: int) -> bytes:
    out = bytearray()
    while True:
        b = v & 0x7F
        v >>= 7
        out.append(b | (0x80 if v else 0))
        if not v:
            return bytes(out)


def _build_block(entries) -> bytes:
    body = bytearray()
    restarts = []
    key = b""
    for k, val in entries:
        restarts.append(len(body))
        shared = 0
        body += _varint_enc(shared) + _varint_enc(len(k)) + _varint_enc(len(val))
        body += k + val
        key = k
    body += struct.pack("<%dI" % len(restarts), *restarts)
    body += struct.pack("<I", len(restarts))
    return bytes(body)


def _build_table(data_blocks) -> bytes:
    """data_blocks: list of (raw_bytes, compression_type)。返回完整 .ldb 字节。"""
    out = bytearray()
    handles = []
    for raw, btype in data_blocks:
        off = len(out)
        out += raw + bytes([btype]) + b"\x00\x00\x00\x00"  # trailer: type + crc(未校验)
        handles.append((off, len(raw)))
    idx_entries = [(b"z%02d" % i, _varint_enc(o) + _varint_enc(s)) for i, (o, s) in enumerate(handles)]
    index = _build_block(idx_entries)
    idx_off = len(out)
    out += index + b"\x00" + b"\x00\x00\x00\x00"
    footer = bytearray()
    footer += _varint_enc(0) + _varint_enc(0)  # metaindex handle (空)
    footer += _varint_enc(idx_off) + _varint_enc(len(index))
    footer += b"\x00" * (40 - len(footer))
    footer += C._TABLE_MAGIC
    out += footer
    return bytes(out)


def test_sstable_raw_and_snappy_blocks(tmp_path):
    snappy_hello = b"\x05\x10hello"  # literal "hello"
    table = _build_table([(b"rawblock", 0), (snappy_hello, 1)])
    p = tmp_path / "t.ldb"
    p.write_bytes(table)
    blocks = list(C.iter_table_blocks(str(p)))
    assert blocks == [b"rawblock", b"hello"]


def test_sstable_bad_magic_yields_nothing(tmp_path):
    p = tmp_path / "bad.ldb"
    p.write_bytes(b"\x00" * 48)
    assert list(C.iter_table_blocks(str(p))) == []


# ---------------------------------------------------------------------------
# 结构化提取与回声拒绝
# ---------------------------------------------------------------------------
def _usage_blob(sp=100, msg=200, sk=10, tool=300, tw=300000,
                mid="8b19a730-e7e4-11f1-a4cc-35d422d7b591",
                conv="38456109709267458", model="38", ts=1763970000000):
    js = ('{"system_prompt":%d,"messages":%d,"skills":%d,"tools":%d,"total_window_size":%d}'
          % (sp, msg, sk, tool, tw))
    sec = conv + "_2026112416"
    parts = [
        b'message_id"' + bytes([len(mid)]) + mid.encode(),
        b'context_window_usage"' + bytes([len(js)]) + js.encode(),
        b'conversation_id"' + bytes([len(conv)]) + conv.encode(),
        b'model_id"' + bytes([len(model)]) + model.encode(),
        b'create_time_msN' + struct.pack("<d", float(ts)),
        b'section_tag_1h"' + bytes([len(sec)]) + sec.encode(),
    ]
    return b" ".join(parts)


def test_extract_full_identity():
    recs = C.extract_usage_records(_usage_blob())
    assert len(recs) == 1
    r = recs[0]
    assert r["message_id"] == "8b19a730-e7e4-11f1-a4cc-35d422d7b591"
    assert r["context_total"] == 610
    assert r["conversation_id"] == "38456109709267458"
    assert r["model_id"] == "38"
    assert r["create_time_ms"] == 1763970000000
    assert r["section_tag"] == "38456109709267458_2026112416"


def test_echo_without_message_id_rejected():
    # 只有 usage JSON、无轮次身份 → 视为回声/噪声，必须丢弃
    js = b'{"system_prompt":1,"messages":2,"skills":3,"tools":4,"total_window_size":5}'
    blob = b'context_window_usage"' + bytes([len(js)]) + js
    assert C.extract_usage_records(blob) == []


def test_multiple_versions_same_round():
    blob = _usage_blob(msg=200) + b" || " + _usage_blob(msg=900)
    recs = C.extract_usage_records(blob)
    assert len(recs) == 2
    assert all(r["message_id"] == recs[0]["message_id"] for r in recs)
    # 去重取最大由调用方负责，这里验证两版都在
    assert max(r["context_total"] for r in recs) == 1310


def test_conversation_meta():
    name_utf16 = "测试会话".encode("utf-16-le")  # 中文走 V8 双字节串 tag 'c'
    blob = (b'conversation_id"\x11' + b"38456109709267458"
            + b'namec' + bytes([len(name_utf16)]) + name_utf16
            + b'create_timeN' + struct.pack("<d", 1763970000000.0))
    meta = C.extract_conversation_meta(blob)
    assert len(meta) == 1
    assert meta[0]["conversation_id"] == "38456109709267458"
    assert meta[0]["name"] == "测试会话"
    assert meta[0]["create_time"] == 1763970000000


def test_conversation_meta_latin1():
    blob = (b'conversation_id"\x11' + b"38456109709267458"
            + b'name"\x05' + b"hello")
    meta = C.extract_conversation_meta(blob)
    assert meta[0]["name"] == "hello"