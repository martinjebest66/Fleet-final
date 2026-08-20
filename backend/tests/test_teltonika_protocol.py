"""Teltonika Codec 8 / Codec 8 Extended protocol tests.

Packets are assembled byte by byte from the wire format rather than reused from
the parser, so a change in the parser cannot make these tests agree with it by
accident. The TCP tests drive a real listening socket, because the point of
them is the framing — TCP is a byte stream and one read is not one packet.
"""

import asyncio
import struct
from datetime import datetime, timezone

import pytest

from teltonika import (
    CODEC_8,
    CODEC_8E,
    MAX_DATA_LENGTH,
    TeltonikaProtocolError,
    TeltonikaTCPServer,
    _crc16_ibm,
    build_avl_packet,
    build_imei_packet,
    build_test_avl_packet,
    normalize_imei,
    parse_avl_packet,
)

IMEI = "352093081452251"


# ── packet-level parsing ────────────────────────────────────────

def test_codec8_roundtrip_preserves_gps_data():
    ts_ms = 1_772_000_000_000
    packet = build_avl_packet([
        {"lat": 50.0755, "lng": 14.4378, "speed": 45, "ts_ms": ts_ms,
         "altitude": 205, "angle": 180, "satellites": 9},
    ])

    records = parse_avl_packet(packet)

    assert len(records) == 1
    gps = records[0]["gps"]
    assert gps["lat"] == pytest.approx(50.0755, abs=1e-6)
    assert gps["lng"] == pytest.approx(14.4378, abs=1e-6)
    assert gps["speed"] == 45
    assert gps["altitude"] == 205
    assert gps["angle"] == 180
    assert gps["satellites"] == 9
    assert records[0]["timestamp"] == datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)


def test_southern_and_western_hemisphere_coordinates_keep_their_sign():
    """Latitude and longitude are signed 32-bit integers on the wire."""
    packet = build_avl_packet([{"lat": -33.8688, "lng": -151.2093, "speed": 60}])

    gps = parse_avl_packet(packet)[0]["gps"]

    assert gps["lat"] == pytest.approx(-33.8688, abs=1e-6)
    assert gps["lng"] == pytest.approx(-151.2093, abs=1e-6)


def test_multiple_records_in_one_packet():
    records_in = [
        {"lat": 50.0 + i / 100, "lng": 14.0 + i / 100, "speed": 30 + i,
         "ts_ms": 1_772_000_000_000 + i * 10_000}
        for i in range(8)
    ]
    packet = build_avl_packet(records_in)

    records = parse_avl_packet(packet)

    assert len(records) == 8
    assert [r["gps"]["speed"] for r in records] == [30 + i for i in range(8)]


def test_codec8_extended_with_io_elements():
    packet = build_avl_packet(
        [{"lat": 50.1, "lng": 14.5, "speed": 12,
          "io": {239: (1, 1), 240: (1, 1), 66: (2, 12800), 16: (4, 1_234_567), 199: (4, 4321)}}],
        codec_id=CODEC_8E,
    )

    record = parse_avl_packet(packet)[0]

    assert record["io"]["io"][239] == 1
    assert record["obd"]["ignition"]["value"] == 1
    assert record["obd"]["ext_voltage"]["value"] == 12800
    assert record["obd"]["total_odometer"]["value"] == 1_234_567


def test_codec8_io_elements_of_every_width():
    packet = build_avl_packet(
        [{"lat": 50.1, "lng": 14.5, "io": {239: (1, 1), 36: (2, 2500), 16: (4, 999_999),
                                           68: (8, 12_345_678_901)}}],
        codec_id=CODEC_8,
    )

    io = parse_avl_packet(packet)[0]["io"]["io"]

    assert io[239] == 1
    assert io[36] == 2500
    assert io[16] == 999_999
    assert io[68] == 12_345_678_901


# ── rejecting packets that cannot be trusted ────────────────────

def test_corrupt_crc_is_rejected():
    packet = bytearray(build_test_avl_packet(50.0, 14.0, 50))
    packet[-1] ^= 0xFF

    with pytest.raises(TeltonikaProtocolError, match="CRC"):
        parse_avl_packet(bytes(packet))


def test_flipped_payload_byte_is_caught_by_the_crc():
    """A single corrupted coordinate byte must not become a stored position."""
    packet = bytearray(build_test_avl_packet(50.0755, 14.4378, 45))
    packet[20] ^= 0x01

    with pytest.raises(TeltonikaProtocolError):
        parse_avl_packet(bytes(packet))


def test_bad_preamble_is_rejected():
    packet = b"\xDE\xAD\xBE\xEF" + build_test_avl_packet(50.0, 14.0)[4:]

    with pytest.raises(TeltonikaProtocolError, match="preamble"):
        parse_avl_packet(packet)


def test_unsupported_codec_is_rejected():
    body = struct.pack("B", 0x07) + struct.pack("B", 1) + b"\x00" * 20 + struct.pack("B", 1)
    packet = b"\x00\x00\x00\x00" + struct.pack(">I", len(body)) + body + struct.pack(">I", _crc16_ibm(body))

    with pytest.raises(TeltonikaProtocolError, match="codec"):
        parse_avl_packet(packet)


def test_truncated_packet_is_rejected():
    packet = build_test_avl_packet(50.0, 14.0)

    with pytest.raises(TeltonikaProtocolError):
        parse_avl_packet(packet[:-6])


def test_absurd_declared_length_is_rejected_without_allocating():
    packet = b"\x00\x00\x00\x00" + struct.pack(">I", MAX_DATA_LENGTH + 1) + b"\x08\x01" + b"\x00" * 8

    with pytest.raises(TeltonikaProtocolError, match="length"):
        parse_avl_packet(packet)


def test_record_count_mismatch_is_rejected():
    packet = bytearray(build_test_avl_packet(50.0, 14.0))
    data_len = struct.unpack(">I", bytes(packet[4:8]))[0]
    packet[8 + data_len - 1] = 5              # trailing record count
    data = bytes(packet[8:8 + data_len])
    packet[8 + data_len:12 + data_len] = struct.pack(">I", _crc16_ibm(data))

    with pytest.raises(TeltonikaProtocolError, match="count"):
        parse_avl_packet(bytes(packet))


def test_random_garbage_never_crashes_the_parser():
    for payload in (b"", b"\x00", b"\x00" * 11, b"\xff" * 64, bytes(range(256))):
        with pytest.raises(TeltonikaProtocolError):
            parse_avl_packet(payload)


# ── IMEI handling ───────────────────────────────────────────────

def test_valid_imei_is_accepted():
    assert normalize_imei(IMEI.encode()) == IMEI


@pytest.mark.parametrize("raw", [b"12345", b"not-an-imei-x", b"\xff\xfe\x00\x01", b"3520930814522XY"])
def test_implausible_imei_is_rejected(raw):
    with pytest.raises(TeltonikaProtocolError):
        normalize_imei(raw)


# ── TCP framing (the part TCP makes hard) ───────────────────────

class Collector:
    def __init__(self):
        self.records = []
        self.imeis = []

    async def __call__(self, imei, records):
        self.imeis.append(imei)
        self.records.extend(records)


async def _serve(collector, **kwargs):
    server = TeltonikaTCPServer(host="127.0.0.1", port=0, on_records=collector, **kwargs)
    server._server = await asyncio.start_server(server._handle_client, "127.0.0.1", 0)
    port = server._server.sockets[0].getsockname()[1]
    return server, port


async def test_login_then_data_over_tcp():
    collector = Collector()
    server, port = await _serve(collector)
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(build_imei_packet(IMEI))
        await writer.drain()
        assert await reader.readexactly(1) == b"\x01"

        writer.write(build_avl_packet([{"lat": 50.0, "lng": 14.0, "speed": 30}]))
        await writer.drain()
        assert struct.unpack(">I", await reader.readexactly(4))[0] == 1

        writer.close()
        await writer.wait_closed()
    finally:
        await server.stop()

    assert collector.imeis == [IMEI]
    assert len(collector.records) == 1


async def test_several_packets_arriving_in_one_tcp_segment():
    """One read must not be treated as one packet."""
    collector = Collector()
    server, port = await _serve(collector)
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)

        # Login and three data packets pushed out as a single write.
        blob = build_imei_packet(IMEI)
        for i in range(3):
            blob += build_avl_packet([
                {"lat": 50.0 + i / 100, "lng": 14.0, "speed": 20 + i,
                 "ts_ms": 1_772_000_000_000 + i * 1000},
            ])
        writer.write(blob)
        await writer.drain()

        assert await reader.readexactly(1) == b"\x01"
        for _ in range(3):
            assert struct.unpack(">I", await reader.readexactly(4))[0] == 1

        writer.close()
        await writer.wait_closed()
    finally:
        await server.stop()

    assert len(collector.records) == 3
    assert [r["gps"]["speed"] for r in collector.records] == [20, 21, 22]


async def test_one_packet_split_across_several_tcp_writes():
    """A packet dribbled in byte by byte must still be reassembled."""
    collector = Collector()
    server, port = await _serve(collector)
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(build_imei_packet(IMEI))
        await writer.drain()
        assert await reader.readexactly(1) == b"\x01"

        packet = build_avl_packet([
            {"lat": 50.0 + i / 1000, "lng": 14.0, "speed": 40 + i} for i in range(4)
        ])
        for offset in range(0, len(packet), 7):
            writer.write(packet[offset:offset + 7])
            await writer.drain()
            await asyncio.sleep(0)

        assert struct.unpack(">I", await reader.readexactly(4))[0] == 4

        writer.close()
        await writer.wait_closed()
    finally:
        await server.stop()

    assert len(collector.records) == 4


async def test_corrupt_packet_does_not_kill_the_server():
    collector = Collector()
    server, port = await _serve(collector)
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(build_imei_packet(IMEI))
        await writer.drain()
        await reader.readexactly(1)

        bad = bytearray(build_test_avl_packet(50.0, 14.0))
        bad[-1] ^= 0xFF
        writer.write(bytes(bad))
        await writer.drain()

        # Zero records acknowledged -> the device keeps them and resends.
        assert struct.unpack(">I", await reader.readexactly(4))[0] == 0
        writer.close()
        await writer.wait_closed()

        # The listener is still healthy and serves the next tracker.
        reader2, writer2 = await asyncio.open_connection("127.0.0.1", port)
        writer2.write(build_imei_packet(IMEI))
        await writer2.drain()
        assert await reader2.readexactly(1) == b"\x01"
        writer2.write(build_avl_packet([{"lat": 50.0, "lng": 14.0, "speed": 10}]))
        await writer2.drain()
        assert struct.unpack(">I", await reader2.readexactly(4))[0] == 1
        writer2.close()
        await writer2.wait_closed()
    finally:
        await server.stop()

    assert len(collector.records) == 1
    assert server.stats["rejected_packets"] == 1


async def test_bad_imei_login_is_refused():
    collector = Collector()
    server, port = await _serve(collector)
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(struct.pack(">H", 15) + b"NOT-A-REAL-IMEI")
        await writer.drain()
        assert await reader.readexactly(1) == b"\x00"
        writer.close()
        await writer.wait_closed()
    finally:
        await server.stop()

    assert collector.records == []


async def test_records_are_not_acknowledged_when_storage_fails():
    """An unacknowledged packet is resent by the tracker; data is not lost."""
    class Failing:
        calls = 0

        async def __call__(self, imei, records):
            Failing.calls += 1
            raise RuntimeError("database down")

    handler = Failing()
    server, port = await _serve(handler)
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(build_imei_packet(IMEI))
        await writer.drain()
        await reader.readexactly(1)

        writer.write(build_avl_packet([{"lat": 50.0, "lng": 14.0, "speed": 30}]))
        await writer.drain()

        # The connection is closed without an ACK rather than lying to the device.
        with pytest.raises(asyncio.IncompleteReadError):
            await reader.readexactly(4)
        writer.close()
        await writer.wait_closed()
    finally:
        await server.stop()

    assert Failing.calls == 1


async def test_two_trackers_are_served_concurrently():
    collector = Collector()
    server, port = await _serve(collector)
    imeis = ["352093081452251", "352093081452252"]

    async def one_device(imei, speed):
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(build_imei_packet(imei))
        await writer.drain()
        assert await reader.readexactly(1) == b"\x01"
        for _ in range(3):
            writer.write(build_avl_packet([{"lat": 50.0, "lng": 14.0, "speed": speed}]))
            await writer.drain()
            assert struct.unpack(">I", await reader.readexactly(4))[0] == 1
        writer.close()
        await writer.wait_closed()

    try:
        await asyncio.gather(one_device(imeis[0], 30), one_device(imeis[1], 60))
    finally:
        await server.stop()

    assert sorted(set(collector.imeis)) == imeis
    assert len(collector.records) == 6
    assert server.stats["active_connections"] == 0


async def test_idle_connection_is_recycled():
    collector = Collector()
    server, port = await _serve(collector, idle_timeout=0.2)
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        # Connect and say nothing at all.
        assert await reader.read(1) == b""
        writer.close()
        await writer.wait_closed()
    finally:
        await server.stop()
