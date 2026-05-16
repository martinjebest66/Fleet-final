"""
Teltonika FMB003 Codec 8/8E Parser Unit Tests
Tests the parser functions without network dependencies
"""
import pytest
import sys
import os

# Add backend to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from teltonika import (
    build_test_avl_packet,
    parse_avl_packet,
    build_imei_packet,
    _crc16_ibm,
    CODEC_8,
    CODEC_8E
)


class TestTeltonikaParser:
    """Unit tests for Teltonika Codec 8/8E parser"""
    
    def test_build_and_parse_avl_packet_roundtrip(self):
        """Build a test AVL packet and parse it back - verify data integrity"""
        lat = 50.0755
        lng = 14.4378
        speed = 45
        
        # Build packet
        packet = build_test_avl_packet(lat=lat, lng=lng, speed=speed)
        
        # Parse packet
        records = parse_avl_packet(packet)
        
        # Verify
        assert len(records) == 1, f"Expected 1 record, got {len(records)}"
        
        gps = records[0]["gps"]
        assert abs(gps["lat"] - lat) < 0.0001, f"Latitude mismatch: {gps['lat']} vs {lat}"
        assert abs(gps["lng"] - lng) < 0.0001, f"Longitude mismatch: {gps['lng']} vs {lng}"
        assert gps["speed"] == speed, f"Speed mismatch: {gps['speed']} vs {speed}"
        
        print(f"✓ AVL packet roundtrip test passed - lat={gps['lat']}, lng={gps['lng']}, speed={gps['speed']}")
    
    def test_build_avl_packet_with_different_coordinates(self):
        """Test packet building with various coordinate values"""
        test_cases = [
            (50.0, 14.0, 0),      # Prague area, stationary
            (48.8566, 2.3522, 60), # Paris
            (-33.8688, 151.2093, 30),  # Sydney (negative lat)
            (0.0, 0.0, 100),      # Equator/Prime meridian
        ]
        
        for lat, lng, speed in test_cases:
            packet = build_test_avl_packet(lat=lat, lng=lng, speed=speed)
            records = parse_avl_packet(packet)
            
            assert len(records) == 1
            gps = records[0]["gps"]
            assert abs(gps["lat"] - lat) < 0.0001
            assert abs(gps["lng"] - lng) < 0.0001
            assert gps["speed"] == speed
        
        print(f"✓ Multiple coordinate tests passed ({len(test_cases)} cases)")
    
    def test_imei_packet_format(self):
        """Test IMEI packet builder produces correct format"""
        imei = "352625090000001"
        
        packet = build_imei_packet(imei)
        
        # IMEI packet format: [2B length] [ASCII IMEI]
        assert len(packet) == 2 + len(imei), f"Packet length mismatch: {len(packet)} vs {2 + len(imei)}"
        
        # First 2 bytes should be length in big-endian
        import struct
        length = struct.unpack(">H", packet[:2])[0]
        assert length == len(imei), f"Length field mismatch: {length} vs {len(imei)}"
        
        # Rest should be ASCII IMEI
        decoded_imei = packet[2:].decode("ascii")
        assert decoded_imei == imei, f"IMEI mismatch: {decoded_imei} vs {imei}"
        
        print(f"✓ IMEI packet format test passed - IMEI={imei}")
    
    def test_imei_packet_various_lengths(self):
        """Test IMEI packet with various IMEI lengths"""
        test_imeis = [
            "352625090000001",  # Standard 15-digit IMEI
            "123456789012345",  # Another 15-digit
            "12345678901234567",  # 17-digit (some devices)
        ]
        
        for imei in test_imeis:
            packet = build_imei_packet(imei)
            import struct
            length = struct.unpack(">H", packet[:2])[0]
            assert length == len(imei)
            assert packet[2:].decode("ascii") == imei
        
        print(f"✓ Various IMEI length tests passed ({len(test_imeis)} cases)")
    
    def test_crc16_ibm_calculation(self):
        """Test CRC-16/IBM calculation"""
        # Known test vector
        test_data = b"\x08\x01"  # Codec 8, 1 record
        crc = _crc16_ibm(test_data)
        
        # CRC should be a 16-bit value
        assert 0 <= crc <= 0xFFFF, f"CRC out of range: {crc}"
        
        # Same data should produce same CRC
        crc2 = _crc16_ibm(test_data)
        assert crc == crc2, "CRC not deterministic"
        
        print(f"✓ CRC-16/IBM calculation test passed - CRC={crc:#06x}")
    
    def test_avl_packet_structure(self):
        """Test AVL packet has correct structure"""
        packet = build_test_avl_packet(lat=50.0, lng=14.0, speed=45)
        
        # Preamble should be 4 zero bytes
        assert packet[:4] == b"\x00\x00\x00\x00", "Invalid preamble"
        
        # Codec ID should be at offset 8
        codec_id = packet[8]
        assert codec_id == CODEC_8, f"Expected Codec 8 ({CODEC_8:#x}), got {codec_id:#x}"
        
        # Number of records at offset 9
        num_records = packet[9]
        assert num_records == 1, f"Expected 1 record, got {num_records}"
        
        print(f"✓ AVL packet structure test passed - codec={codec_id:#x}, records={num_records}")
    
    def test_parse_invalid_packet_too_short(self):
        """Test parser rejects packets that are too short"""
        with pytest.raises(ValueError, match="Packet too short"):
            parse_avl_packet(b"\x00\x00\x00\x00\x00")
        
        print("✓ Short packet rejection test passed")
    
    def test_parse_invalid_preamble(self):
        """Test parser rejects packets with invalid preamble"""
        # Create packet with wrong preamble
        bad_packet = b"\x01\x02\x03\x04" + b"\x00" * 20
        
        with pytest.raises(ValueError, match="Invalid preamble"):
            parse_avl_packet(bad_packet)
        
        print("✓ Invalid preamble rejection test passed")
    
    def test_parsed_record_has_required_fields(self):
        """Test parsed record contains all required fields"""
        packet = build_test_avl_packet(lat=50.0, lng=14.0, speed=45)
        records = parse_avl_packet(packet)
        
        record = records[0]
        
        # Check required top-level fields
        assert "timestamp" in record, "Missing timestamp field"
        assert "priority" in record, "Missing priority field"
        assert "gps" in record, "Missing gps field"
        assert "io" in record, "Missing io field"
        
        # Check GPS sub-fields
        gps = record["gps"]
        assert "lat" in gps, "Missing lat in GPS"
        assert "lng" in gps, "Missing lng in GPS"
        assert "altitude" in gps, "Missing altitude in GPS"
        assert "angle" in gps, "Missing angle in GPS"
        assert "satellites" in gps, "Missing satellites in GPS"
        assert "speed" in gps, "Missing speed in GPS"
        
        print("✓ Record structure test passed - all required fields present")
    
    def test_timestamp_is_datetime(self):
        """Test parsed timestamp is a datetime object"""
        from datetime import datetime
        
        packet = build_test_avl_packet(lat=50.0, lng=14.0, speed=45)
        records = parse_avl_packet(packet)
        
        ts = records[0]["timestamp"]
        assert isinstance(ts, datetime), f"Timestamp is not datetime: {type(ts)}"
        
        print(f"✓ Timestamp type test passed - {ts}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
