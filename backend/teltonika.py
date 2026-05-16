"""
Teltonika FMB003 Codec 8 / Codec 8 Extended TCP receiver.

Protocol flow (TCP):
  1. Device connects
  2. Device sends IMEI login packet (2-byte length + ASCII IMEI)
  3. Server replies 0x01 (accepted)
  4. Device sends AVL data packets
  5. Server replies with 4-byte record count ACK
  6. Repeat 4-5 until disconnect

AVL Packet structure:
  [4B preamble 0x00000000] [4B data_length] [1B codec_id] [1-2B num_records]
  [AVL records...] [1-2B num_records] [4B CRC-16]

Each AVL record:
  [8B timestamp_ms] [1B priority] [GPS element] [IO element]

GPS element (15 bytes):
  [4B longitude] [4B latitude] [2B altitude] [2B angle] [1B satellites] [2B speed]

IO element (Codec 8):
  [1B event_io_id] [1B total_io] [groups of 1/2/4/8 byte values]

IO element (Codec 8 Extended):
  [2B event_io_id] [2B total_io] [groups with 2B ids + variable-size values]
"""

import asyncio
import struct
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("teltonika")

CODEC_8 = 0x08
CODEC_8E = 0x8E


def _crc16_ibm(data: bytes) -> int:
    """CRC-16/IBM (CRC-16/ARC) used by Teltonika."""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


# ── Codec 8 parser ──────────────────────────────────────────────

def _parse_io_codec8(data: bytes, offset: int):
    event_io_id = data[offset]
    total_io = data[offset + 1]
    offset += 2
    io = {}

    # 1-byte values
    cnt = data[offset]
    offset += 1
    for _ in range(cnt):
        io_id = data[offset]
        val = data[offset + 1]
        io[io_id] = val
        offset += 2

    # 2-byte values
    cnt = data[offset]
    offset += 1
    for _ in range(cnt):
        io_id = data[offset]
        val = struct.unpack(">H", data[offset + 1:offset + 3])[0]
        io[io_id] = val
        offset += 3

    # 4-byte values
    cnt = data[offset]
    offset += 1
    for _ in range(cnt):
        io_id = data[offset]
        val = struct.unpack(">I", data[offset + 1:offset + 5])[0]
        io[io_id] = val
        offset += 5

    # 8-byte values
    cnt = data[offset]
    offset += 1
    for _ in range(cnt):
        io_id = data[offset]
        val = struct.unpack(">Q", data[offset + 1:offset + 9])[0]
        io[io_id] = val
        offset += 9

    return {"event_io_id": event_io_id, "total_io": total_io, "io": io}, offset


# ── Codec 8 Extended parser ─────────────────────────────────────

def _parse_io_codec8e(data: bytes, offset: int):
    event_io_id = struct.unpack(">H", data[offset:offset + 2])[0]
    total_io = struct.unpack(">H", data[offset + 2:offset + 4])[0]
    offset += 4
    io = {}

    # 1-byte values
    cnt = struct.unpack(">H", data[offset:offset + 2])[0]
    offset += 2
    for _ in range(cnt):
        io_id = struct.unpack(">H", data[offset:offset + 2])[0]
        val = data[offset + 2]
        io[io_id] = val
        offset += 3

    # 2-byte values
    cnt = struct.unpack(">H", data[offset:offset + 2])[0]
    offset += 2
    for _ in range(cnt):
        io_id = struct.unpack(">H", data[offset:offset + 2])[0]
        val = struct.unpack(">H", data[offset + 2:offset + 4])[0]
        io[io_id] = val
        offset += 4

    # 4-byte values
    cnt = struct.unpack(">H", data[offset:offset + 2])[0]
    offset += 2
    for _ in range(cnt):
        io_id = struct.unpack(">H", data[offset:offset + 2])[0]
        val = struct.unpack(">I", data[offset + 2:offset + 6])[0]
        io[io_id] = val
        offset += 6

    # 8-byte values
    cnt = struct.unpack(">H", data[offset:offset + 2])[0]
    offset += 2
    for _ in range(cnt):
        io_id = struct.unpack(">H", data[offset:offset + 2])[0]
        val = struct.unpack(">Q", data[offset + 2:offset + 10])[0]
        io[io_id] = val
        offset += 10

    # Variable-length values (Codec 8 Extended)
    cnt = struct.unpack(">H", data[offset:offset + 2])[0]
    offset += 2
    for _ in range(cnt):
        io_id = struct.unpack(">H", data[offset:offset + 2])[0]
        vlen = struct.unpack(">H", data[offset + 2:offset + 4])[0]
        val = data[offset + 4:offset + 4 + vlen]
        io[io_id] = val.hex()
        offset += 4 + vlen

    return {"event_io_id": event_io_id, "total_io": total_io, "io": io}, offset


# ── GPS element parser ──────────────────────────────────────────

def _parse_gps(data: bytes, offset: int):
    lon = struct.unpack(">i", data[offset:offset + 4])[0] / 10_000_000
    lat = struct.unpack(">i", data[offset + 4:offset + 8])[0] / 10_000_000
    alt = struct.unpack(">h", data[offset + 8:offset + 10])[0]
    angle = struct.unpack(">H", data[offset + 10:offset + 12])[0]
    sats = data[offset + 12]
    speed = struct.unpack(">H", data[offset + 13:offset + 15])[0]
    return {
        "lng": lon,
        "lat": lat,
        "altitude": alt,
        "angle": angle,
        "satellites": sats,
        "speed": speed,
    }, offset + 15


# ── AVL record parser ──────────────────────────────────────────

def _parse_avl_record(data: bytes, offset: int, codec_id: int):
    ts_ms = struct.unpack(">Q", data[offset:offset + 8])[0]
    priority = data[offset + 8]
    offset += 9

    gps, offset = _parse_gps(data, offset)

    if codec_id == CODEC_8E:
        io, offset = _parse_io_codec8e(data, offset)
    else:
        io, offset = _parse_io_codec8(data, offset)

    return {
        "timestamp": datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc),
        "priority": priority,
        "gps": gps,
        "io": io,
    }, offset


# ── Full packet parser ──────────────────────────────────────────

def parse_avl_packet(packet: bytes):
    """Parse a full Teltonika AVL TCP packet. Returns list of records."""
    if len(packet) < 12:
        raise ValueError("Packet too short")
    if packet[:4] != b"\x00\x00\x00\x00":
        raise ValueError("Invalid preamble")

    data_len = struct.unpack(">I", packet[4:8])[0]
    codec_id = packet[8]

    if codec_id not in (CODEC_8, CODEC_8E):
        raise ValueError(f"Unsupported codec: {codec_id:#x}")

    if codec_id == CODEC_8E:
        num_records = packet[9]
        offset = 10
    else:
        num_records = packet[9]
        offset = 10

    records = []
    for _ in range(num_records):
        rec, offset = _parse_avl_record(packet, offset, codec_id)
        records.append(rec)

    num_records_2 = packet[offset]
    if num_records != num_records_2:
        raise ValueError(f"Record count mismatch: {num_records} vs {num_records_2}")

    # CRC check
    crc_data = packet[8:8 + data_len]
    expected_crc = struct.unpack(">I", packet[8 + data_len:12 + data_len])[0]
    actual_crc = _crc16_ibm(crc_data)
    if expected_crc != actual_crc:
        logger.warning("CRC mismatch: expected %04X, got %04X", expected_crc, actual_crc)

    return records


# ── Helper: read exactly n bytes from asyncio stream ────────────

async def _read_n(reader: asyncio.StreamReader, n: int) -> bytes:
    data = b""
    while len(data) < n:
        chunk = await reader.read(n - len(data))
        if not chunk:
            raise ConnectionError("Connection closed while reading")
        data += chunk
    return data


# ── TCP Server ──────────────────────────────────────────────────

class TeltonikaTCPServer:
    """Asyncio TCP server that receives Teltonika AVL data and stores it via a callback."""

    def __init__(self, host: str = "0.0.0.0", port: int = 5027, on_records=None):
        self.host = host
        self.port = port
        self.on_records = on_records  # async callback(imei, records)
        self._server: Optional[asyncio.AbstractServer] = None
        self._connections = 0
        self._total_records = 0

    @property
    def is_running(self) -> bool:
        return self._server is not None and self._server.is_serving()

    @property
    def stats(self) -> dict:
        return {
            "running": self.is_running,
            "host": self.host,
            "port": self.port,
            "active_connections": self._connections,
            "total_records_received": self._total_records,
        }

    async def start(self):
        self._server = await asyncio.start_server(self._handle_client, self.host, self.port)
        logger.info("Teltonika TCP server listening on %s:%d", self.host, self.port)

    async def stop(self):
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            logger.info("Teltonika TCP server stopped")

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        addr = writer.get_extra_info("peername")
        logger.info("Teltonika device connected: %s", addr)
        self._connections += 1
        imei = None

        try:
            # Step 1: IMEI login
            imei_len_bytes = await _read_n(reader, 2)
            imei_len = struct.unpack(">H", imei_len_bytes)[0]
            imei_bytes = await _read_n(reader, imei_len)
            imei = imei_bytes.decode("ascii")
            logger.info("Device IMEI: %s from %s", imei, addr)

            # Accept IMEI
            writer.write(b"\x01")
            await writer.drain()

            # Step 2: AVL data loop
            while True:
                header = await _read_n(reader, 8)
                data_len = struct.unpack(">I", header[4:8])[0]
                body = await _read_n(reader, data_len + 4)  # data + CRC
                packet = header + body

                try:
                    records = parse_avl_packet(packet)
                    self._total_records += len(records)
                    logger.info("Parsed %d records from IMEI %s", len(records), imei)

                    if self.on_records:
                        await self.on_records(imei, records)

                    # ACK
                    writer.write(struct.pack(">I", len(records)))
                    await writer.drain()

                except ValueError as e:
                    logger.error("Parse error from %s: %s", addr, e)
                    break

        except (ConnectionError, asyncio.IncompleteReadError):
            logger.info("Device disconnected: %s (IMEI: %s)", addr, imei)
        except Exception as e:
            logger.error("Unexpected error from %s: %s", addr, e)
        finally:
            self._connections -= 1
            writer.close()


def build_test_avl_packet(lat: float, lng: float, speed: int = 45, ts_ms: Optional[int] = None) -> bytes:
    """Build a minimal Codec 8 AVL packet for testing without real hardware."""
    if ts_ms is None:
        ts_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    # AVL record
    record = struct.pack(">Q", ts_ms)          # timestamp
    record += struct.pack("B", 0)              # priority
    record += struct.pack(">i", int(lng * 10_000_000))  # longitude
    record += struct.pack(">i", int(lat * 10_000_000))  # latitude
    record += struct.pack(">h", 200)           # altitude
    record += struct.pack(">H", 0)             # angle
    record += struct.pack("B", 10)             # satellites
    record += struct.pack(">H", speed)         # speed
    # IO element (Codec 8 - minimal)
    record += struct.pack("B", 0)              # event IO id
    record += struct.pack("B", 0)              # total IO count
    record += struct.pack("B", 0)              # 1-byte count
    record += struct.pack("B", 0)              # 2-byte count
    record += struct.pack("B", 0)              # 4-byte count
    record += struct.pack("B", 0)              # 8-byte count

    # Build packet
    codec_id = CODEC_8
    num_records = 1
    data = struct.pack("B", codec_id) + struct.pack("B", num_records) + record + struct.pack("B", num_records)

    crc = _crc16_ibm(data)
    packet = b"\x00\x00\x00\x00" + struct.pack(">I", len(data)) + data + struct.pack(">I", crc)
    return packet


def build_imei_packet(imei: str) -> bytes:
    """Build IMEI login packet."""
    imei_bytes = imei.encode("ascii")
    return struct.pack(">H", len(imei_bytes)) + imei_bytes
