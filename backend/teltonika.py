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

#: Largest AVL data field we will buffer. A Codec 8 packet carries at most 255
#: records; this leaves generous headroom while making a corrupt length header
#: a rejected packet rather than a multi-gigabyte allocation.
MAX_DATA_LENGTH = 1 << 20  # 1 MiB

#: How long a connected tracker may stay silent before the connection is
#: recycled. Without this a half-open TCP connection holds a task forever.
DEFAULT_IDLE_TIMEOUT_SEC = 900

#: Minimum acceptable IMEI length (GSM IMEI is 15 digits; some devices report
#: a 16-digit IMEISV).
IMEI_MIN_LEN = 14
IMEI_MAX_LEN = 17


class TeltonikaProtocolError(ValueError):
    """Raised for any packet that cannot be trusted (framing, codec, CRC)."""


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
        "obd": extract_obd_data(io.get("io", {})),
    }, offset


# ── OBD-II IO element mapper ───────────────────────────────────

# Known Teltonika FMB003 AVL IO IDs for OBD-II / vehicle data
OBD_IO_MAP = {
    # Standard OBD-II PIDs
    32: ("coolant_temp", "°C"),         # Engine Coolant Temperature
    36: ("engine_rpm", "rpm"),           # Engine RPM
    48: ("fuel_level", "%"),             # Fuel Level (standard PID 0x2F)
    30: ("dtc_count", ""),               # Number of DTC codes
    31: ("mil_status", ""),              # Malfunction Indicator Lamp
    33: ("fuel_rate", "l/h"),            # Fuel Rate
    35: ("intake_air_temp", "°C"),       # Intake Air Temperature
    37: ("throttle_position", "%"),      # Throttle Position
    38: ("engine_load", "%"),            # Calculated Engine Load
    39: ("fuel_pressure", "kPa"),        # Fuel Pressure
    42: ("vehicle_speed", "km/h"),       # OBD Vehicle Speed
    47: ("ambient_air_temp", "°C"),      # Ambient Air Temperature
    # Total distance
    16: ("total_odometer", "m"),         # Total Odometer
    199: ("trip_odometer", "m"),         # Trip Odometer
    # Battery / Power
    66: ("ext_voltage", "mV"),           # External Voltage
    67: ("battery_voltage", "mV"),       # Battery Voltage
    68: ("battery_current", "mA"),       # Battery Current
    # Movement & Ignition
    239: ("ignition", ""),               # Ignition (0/1)
    240: ("movement", ""),               # Movement (0/1)
    # OEM (Codec 8 Extended)
    390: ("oem_fuel_level", "%"),        # OEM Fuel Level
    281: ("dtc_list", ""),               # DTC List (string/hex)
}


def extract_obd_data(io_values: dict) -> dict:
    """Extract known OBD-II parameters from raw IO values."""
    obd = {}
    for io_id, value in io_values.items():
        io_id_int = int(io_id) if isinstance(io_id, str) else io_id
        if io_id_int in OBD_IO_MAP:
            param_name, unit = OBD_IO_MAP[io_id_int]
            obd[param_name] = {"value": value, "unit": unit}
    return obd


# ── Full packet parser ──────────────────────────────────────────

def parse_avl_packet(packet: bytes):
    """Parse one full Teltonika AVL TCP packet into a list of records.

    Raises :class:`TeltonikaProtocolError` for anything that is not a
    verifiably intact packet. A record is only returned once framing, the
    record-count echo *and* the CRC agree, so a corrupted packet can never be
    written to the database as if it were real positions.
    """
    if len(packet) < 12:
        raise TeltonikaProtocolError("Packet too short")
    if packet[:4] != b"\x00\x00\x00\x00":
        raise TeltonikaProtocolError("Invalid preamble")

    data_len = struct.unpack(">I", packet[4:8])[0]
    if data_len < 3 or data_len > MAX_DATA_LENGTH:
        raise TeltonikaProtocolError(f"Implausible data length: {data_len}")
    if len(packet) < 8 + data_len + 4:
        raise TeltonikaProtocolError(
            f"Truncated packet: need {8 + data_len + 4} bytes, got {len(packet)}"
        )

    codec_id = packet[8]
    if codec_id not in (CODEC_8, CODEC_8E):
        raise TeltonikaProtocolError(f"Unsupported codec: {codec_id:#x}")

    # Verify the CRC before interpreting any field. Codec 8 and 8 Extended both
    # cover [codec id .. number of data 2] with a CRC-16/IBM in the low 16 bits
    # of the trailing 4 bytes.
    crc_data = packet[8:8 + data_len]
    expected_crc = struct.unpack(">I", packet[8 + data_len:12 + data_len])[0]
    actual_crc = _crc16_ibm(crc_data)
    if expected_crc != actual_crc:
        raise TeltonikaProtocolError(
            f"CRC mismatch: expected {expected_crc:#06x}, computed {actual_crc:#06x}"
        )

    # Number of Data 1 is a single byte for both Codec 8 and Codec 8 Extended.
    num_records = packet[9]
    offset = 10

    records = []
    try:
        for _ in range(num_records):
            rec, offset = _parse_avl_record(packet, offset, codec_id)
            records.append(rec)
        num_records_2 = packet[offset]
    except (struct.error, IndexError, ValueError, OverflowError, OSError) as exc:
        raise TeltonikaProtocolError(f"Malformed AVL record: {exc}") from exc

    if num_records != num_records_2:
        raise TeltonikaProtocolError(f"Record count mismatch: {num_records} vs {num_records_2}")
    if offset + 1 != 8 + data_len:
        raise TeltonikaProtocolError(
            f"Record data does not fill the declared length ({offset + 1 - 8} of {data_len} bytes)"
        )

    return records


# ── Helper: read exactly n bytes from asyncio stream ────────────

async def _read_n(reader: asyncio.StreamReader, n: int, timeout: Optional[float] = None) -> bytes:
    """Read exactly `n` bytes, however the stream happens to be chunked.

    TCP is a byte stream: one `read()` may return part of a packet, or several
    packets at once. Every protocol field is therefore read through this
    helper, which loops until the requested number of bytes has arrived. The
    optional timeout bounds the *total* wait so a silent peer cannot pin a task
    forever.
    """
    data = bytearray()
    deadline = None if timeout is None else asyncio.get_running_loop().time() + timeout
    while len(data) < n:
        if deadline is not None:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise asyncio.TimeoutError("Timed out waiting for data")
            chunk = await asyncio.wait_for(reader.read(n - len(data)), timeout=remaining)
        else:
            chunk = await reader.read(n - len(data))
        if not chunk:
            raise ConnectionError("Connection closed while reading")
        data += chunk
    return bytes(data)


def normalize_imei(raw: bytes) -> str:
    """Validate and normalise the IMEI from a login packet.

    Raises :class:`TeltonikaProtocolError` when the value is not a plausible
    IMEI, so a garbage login is rejected explicitly instead of being stored as
    a device identifier.
    """
    try:
        imei = raw.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise TeltonikaProtocolError("IMEI is not ASCII") from exc
    if not imei.isdigit():
        raise TeltonikaProtocolError("IMEI contains non-digit characters")
    if not (IMEI_MIN_LEN <= len(imei) <= IMEI_MAX_LEN):
        raise TeltonikaProtocolError(f"Implausible IMEI length: {len(imei)}")
    return imei


# ── TCP Server ──────────────────────────────────────────────────

class TeltonikaTCPServer:
    """Asyncio TCP server that receives Teltonika AVL data and stores it via a callback."""

    def __init__(self, host: str = "0.0.0.0", port: int = 5027, on_records=None,
                 idle_timeout: float = DEFAULT_IDLE_TIMEOUT_SEC):
        self.host = host
        self.port = port
        self.on_records = on_records  # async callback(imei, records)
        self.idle_timeout = idle_timeout
        self._server: Optional[asyncio.AbstractServer] = None
        self._connections = 0
        self._total_records = 0
        self._total_packets = 0
        self._rejected_packets = 0
        self._connected_imeis: set = set()
        # Tracked so shutdown can close in-flight tracker sessions instead of
        # leaving their tasks running after the listener is gone.
        self._sessions: set = set()
        self._writers: set = set()

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
            "total_packets_received": self._total_packets,
            "rejected_packets": self._rejected_packets,
            "connected_imeis": sorted(self._connected_imeis),
        }

    async def start(self):
        self._server = await asyncio.start_server(self._handle_client, self.host, self.port)
        logger.info("Teltonika TCP server listening on %s:%d", self.host, self.port)

    async def stop(self, drain_timeout: float = 10.0):
        """Stop accepting connections and let open sessions finish.

        Waits for the in-flight tracker sessions so a redeploy does not cut a
        device off between receiving its records and acknowledging them.
        """
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        for writer in list(self._writers):
            try:
                writer.close()
            except (ConnectionError, OSError):
                pass
        if self._sessions:
            await asyncio.wait(set(self._sessions), timeout=drain_timeout)
            for task in list(self._sessions):
                if not task.done():
                    task.cancel()
        logger.info("Teltonika TCP server stopped")

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Serve one tracker connection for its whole lifetime.

        Framing is driven entirely by the declared data length, so any mix of
        partial reads and several packets arriving in one TCP segment is
        handled. A packet that fails validation is answered with a zero ACK and
        the connection is closed, which makes the device reconnect and resend
        rather than silently losing records.
        """
        addr = writer.get_extra_info("peername")
        self._connections += 1
        session = asyncio.current_task()
        if session is not None:
            self._sessions.add(session)
        self._writers.add(writer)
        imei = None
        packets = 0
        records_total = 0

        try:
            # Step 1: IMEI login
            imei_len_bytes = await _read_n(reader, 2, timeout=self.idle_timeout)
            imei_len = struct.unpack(">H", imei_len_bytes)[0]
            if not (IMEI_MIN_LEN <= imei_len <= IMEI_MAX_LEN):
                logger.warning("Rejected login from %s: implausible IMEI length %d", addr, imei_len)
                writer.write(b"\x00")
                await writer.drain()
                return
            imei_bytes = await _read_n(reader, imei_len, timeout=self.idle_timeout)
            try:
                imei = normalize_imei(imei_bytes)
            except TeltonikaProtocolError as exc:
                logger.warning("Rejected login from %s: %s", addr, exc)
                writer.write(b"\x00")
                await writer.drain()
                return

            logger.info("Tracker connected: IMEI %s from %s", imei, addr)
            self._connected_imeis.add(imei)
            writer.write(b"\x01")
            await writer.drain()

            # Step 2: AVL data loop
            while True:
                header = await _read_n(reader, 8, timeout=self.idle_timeout)
                data_len = struct.unpack(">I", header[4:8])[0]
                if data_len < 3 or data_len > MAX_DATA_LENGTH:
                    self._rejected_packets += 1
                    logger.error(
                        "IMEI %s sent an implausible data length (%d) - dropping connection",
                        imei, data_len,
                    )
                    break
                body = await _read_n(reader, data_len + 4, timeout=self.idle_timeout)  # data + CRC
                packet = header + body

                try:
                    records = parse_avl_packet(packet)
                except TeltonikaProtocolError as exc:
                    self._rejected_packets += 1
                    logger.error("Invalid packet from IMEI %s (%s): %s", imei, addr, exc)
                    # Acknowledge zero records so the device resends them.
                    writer.write(struct.pack(">I", 0))
                    await writer.drain()
                    break

                packets += 1
                self._total_packets += 1
                self._total_records += len(records)
                records_total += len(records)
                logger.info("IMEI %s: received %d AVL record(s)", imei, len(records))

                if self.on_records:
                    try:
                        await self.on_records(imei, records)
                    except Exception:
                        # Do not ACK records we failed to persist - the tracker
                        # keeps them and resends on the next connection.
                        self._rejected_packets += 1
                        logger.exception(
                            "Storing %d record(s) from IMEI %s failed - not acknowledging",
                            len(records), imei,
                        )
                        break

                writer.write(struct.pack(">I", len(records)))
                await writer.drain()

        except asyncio.TimeoutError:
            logger.info("Tracker idle timeout: %s (IMEI: %s)", addr, imei)
        except (ConnectionError, asyncio.IncompleteReadError):
            logger.info("Tracker disconnected: %s (IMEI: %s)", addr, imei)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Unexpected error on tracker connection %s (IMEI: %s)", addr, imei)
        finally:
            self._connections -= 1
            self._writers.discard(writer)
            if session is not None:
                self._sessions.discard(session)
            if imei:
                self._connected_imeis.discard(imei)
            logger.info(
                "Tracker session ended: IMEI %s, %d packet(s), %d record(s)",
                imei, packets, records_total,
            )
            try:
                writer.close()
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass


def build_test_avl_packet(lat: float, lng: float, speed: int = 45, ts_ms: Optional[int] = None) -> bytes:
    """Build a minimal Codec 8 AVL packet for testing without real hardware."""
    return build_avl_packet(
        [{"lat": lat, "lng": lng, "speed": speed, "ts_ms": ts_ms, "altitude": 200}],
        codec_id=CODEC_8,
    )


def build_avl_packet(records: list, codec_id: int = CODEC_8) -> bytes:
    """Build a Codec 8 / Codec 8 Extended packet from record descriptions.

    Used by the test-device endpoint and by the protocol tests, so the parser
    is exercised against packets built strictly to the wire format rather than
    against a fixture that mirrors the parser's own assumptions.

    Each record is a dict with ``lat``, ``lng`` and optionally ``speed``,
    ``ts_ms``, ``altitude``, ``angle``, ``satellites``, ``priority`` and
    ``io`` (a ``{io_id: (size_in_bytes, value)}`` mapping).
    """
    if codec_id not in (CODEC_8, CODEC_8E):
        raise ValueError(f"Unsupported codec: {codec_id:#x}")

    body = b""
    for rec in records:
        ts_ms = rec.get("ts_ms") or int(datetime.now(timezone.utc).timestamp() * 1000)
        body += struct.pack(">Q", ts_ms)
        body += struct.pack("B", rec.get("priority", 0))
        body += struct.pack(">i", int(round(rec["lng"] * 10_000_000)))
        body += struct.pack(">i", int(round(rec["lat"] * 10_000_000)))
        body += struct.pack(">h", int(rec.get("altitude", 0)))
        body += struct.pack(">H", int(rec.get("angle", 0)))
        body += struct.pack("B", int(rec.get("satellites", 10)))
        body += struct.pack(">H", int(rec.get("speed", 0)))
        body += _build_io_element(rec.get("io") or {}, codec_id, rec.get("event_io_id", 0))

    num_records = len(records)
    data = struct.pack("B", codec_id) + struct.pack("B", num_records) + body + struct.pack("B", num_records)
    crc = _crc16_ibm(data)
    return b"\x00\x00\x00\x00" + struct.pack(">I", len(data)) + data + struct.pack(">I", crc)


def _build_io_element(io_values: dict, codec_id: int, event_io_id: int = 0) -> bytes:
    """Serialise ``{io_id: (size, value)}`` into a Codec 8 / 8E IO element."""
    buckets = {1: [], 2: [], 4: [], 8: []}
    for io_id, (size, value) in io_values.items():
        if size not in buckets:
            raise ValueError(f"Unsupported IO value size: {size}")
        buckets[size].append((io_id, value))

    total = sum(len(v) for v in buckets.values())
    fmt = {1: "B", 2: ">H", 4: ">I", 8: ">Q"}

    if codec_id == CODEC_8E:
        out = struct.pack(">H", event_io_id) + struct.pack(">H", total)
        for size in (1, 2, 4, 8):
            out += struct.pack(">H", len(buckets[size]))
            for io_id, value in buckets[size]:
                out += struct.pack(">H", io_id) + struct.pack(fmt[size], value)
        out += struct.pack(">H", 0)  # no variable-length values
        return out

    out = struct.pack("B", event_io_id) + struct.pack("B", total)
    for size in (1, 2, 4, 8):
        out += struct.pack("B", len(buckets[size]))
        for io_id, value in buckets[size]:
            out += struct.pack("B", io_id) + struct.pack(fmt[size], value)
    return out


def build_imei_packet(imei: str) -> bytes:
    """Build IMEI login packet."""
    imei_bytes = imei.encode("ascii")
    return struct.pack(">H", len(imei_bytes)) + imei_bytes
