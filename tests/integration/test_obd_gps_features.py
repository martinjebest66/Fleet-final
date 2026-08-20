# NOTE: live-server integration test — needs a running Fleet Manager.
# Configure with FLEET_BASE_URL / FLEET_ADMIN_EMAIL / FLEET_ADMIN_PASSWORD.
# Excluded from the default pytest run; see tests/integration/conftest.py.
"""
Test suite for OBD-II diagnostics and GPS auto-trip detection features.
Tests new endpoints: /api/obd/*, /api/gps/detect-trips/*, and Teltonika parser.
"""
import pytest
import requests
import os
import sys

# Add backend to path for teltonika import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_URL = (os.environ.get('FLEET_BASE_URL') or os.environ.get('REACT_APP_BACKEND_URL', '')).rstrip('/')

# Test credentials
ADMIN_EMAIL = os.environ.get("FLEET_ADMIN_EMAIL", os.environ.get("ADMIN_EMAIL", ""))
ADMIN_PASSWORD = os.environ.get("FLEET_ADMIN_PASSWORD", os.environ.get("ADMIN_PASSWORD", ""))
INSTRUCTOR_ID = os.environ.get("TEST_INSTRUCTOR_ID", "inst_aba594d9cd55")
INSTRUCTOR_PIN = os.environ.get("TEST_INSTRUCTOR_PIN", "1234")


class TestTeltonikaParser:
    """Unit tests for Teltonika OBD-II data extraction."""
    
    def test_extract_obd_data_with_known_io_ids(self):
        """Test extract_obd_data function with known OBD IO IDs."""
        from teltonika import extract_obd_data
        
        # Test with engine RPM (36), coolant temp (32), fuel level (48)
        io_values = {36: 2500, 32: 85, 48: 60}
        result = extract_obd_data(io_values)
        
        assert "engine_rpm" in result
        assert result["engine_rpm"]["value"] == 2500
        assert result["engine_rpm"]["unit"] == "rpm"
        
        assert "coolant_temp" in result
        assert result["coolant_temp"]["value"] == 85
        assert result["coolant_temp"]["unit"] == "°C"
        
        assert "fuel_level" in result
        assert result["fuel_level"]["value"] == 60
        assert result["fuel_level"]["unit"] == "%"
        print("PASS: extract_obd_data correctly parses known IO IDs")
    
    def test_extract_obd_data_with_string_keys(self):
        """Test extract_obd_data handles string keys (from JSON)."""
        from teltonika import extract_obd_data
        
        io_values = {"36": 3000, "32": 90}
        result = extract_obd_data(io_values)
        
        assert "engine_rpm" in result
        assert result["engine_rpm"]["value"] == 3000
        print("PASS: extract_obd_data handles string keys")
    
    def test_extract_obd_data_with_unknown_io_ids(self):
        """Test extract_obd_data ignores unknown IO IDs."""
        from teltonika import extract_obd_data
        
        io_values = {999: 123, 36: 2000}  # 999 is unknown
        result = extract_obd_data(io_values)
        
        assert "engine_rpm" in result
        assert len(result) == 1  # Only known ID should be extracted
        print("PASS: extract_obd_data ignores unknown IO IDs")
    
    def test_extract_obd_data_empty_input(self):
        """Test extract_obd_data with empty input."""
        from teltonika import extract_obd_data
        
        result = extract_obd_data({})
        assert result == {}
        print("PASS: extract_obd_data handles empty input")
    
    def test_obd_io_map_contains_expected_parameters(self):
        """Verify OBD_IO_MAP contains all expected parameters."""
        from teltonika import OBD_IO_MAP
        
        expected_ids = [32, 36, 48, 30, 31, 33, 35, 37, 38, 39, 42, 47, 16, 199, 66, 67, 68, 239, 240, 390, 281]
        for io_id in expected_ids:
            assert io_id in OBD_IO_MAP, f"Missing IO ID {io_id} in OBD_IO_MAP"
        print(f"PASS: OBD_IO_MAP contains all {len(expected_ids)} expected parameters")


class TestAuthEndpoints:
    """Test existing auth endpoints still work."""
    
    def test_admin_login_success(self):
        """Test admin login with email/password returns 200."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "user_id" in data
        assert data["email"] == ADMIN_EMAIL
        assert data["role"] == "admin"
        print(f"PASS: Admin login returns 200 with role={data['role']}")
    
    def test_admin_login_sets_cookies(self):
        """Test admin login sets httpOnly cookies."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200
        
        cookies = response.cookies
        assert "access_token" in cookies or "access_token" in response.headers.get("Set-Cookie", "")
        print("PASS: Admin login sets auth cookies")
    
    def test_instructor_login_success(self):
        """Test instructor login with ID/PIN returns 200."""
        response = requests.post(
            f"{BASE_URL}/api/auth/instructor-login",
            json={"instructor_id": INSTRUCTOR_ID, "pin": INSTRUCTOR_PIN}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["role"] == "instructor"
        print(f"PASS: Instructor login returns 200 with role={data['role']}")
    
    def test_auth_me_with_admin_session(self):
        """Test GET /api/auth/me returns admin user data."""
        session = requests.Session()
        login_resp = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert login_resp.status_code == 200
        
        me_resp = session.get(f"{BASE_URL}/api/auth/me")
        assert me_resp.status_code == 200
        
        data = me_resp.json()
        assert data["email"] == ADMIN_EMAIL
        assert data["role"] == "admin"
        print("PASS: GET /api/auth/me returns admin user data")
    
    def test_auth_me_without_auth_returns_401(self):
        """Test GET /api/auth/me without auth returns 401."""
        response = requests.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 401
        print("PASS: GET /api/auth/me without auth returns 401")


class TestOBDEndpoints:
    """Test OBD-II diagnostic endpoints."""
    
    @pytest.fixture(autouse=True)
    def setup_session(self):
        """Setup authenticated session for each test."""
        self.session = requests.Session()
        login_resp = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    
    def test_get_all_obd_vehicles_returns_200(self):
        """Test GET /api/obd/vehicles returns 200 with array."""
        response = self.session.get(f"{BASE_URL}/api/obd/vehicles")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Expected array response"
        print(f"PASS: GET /api/obd/vehicles returns 200 with {len(data)} vehicles")
    
    def test_get_vehicle_obd_data_returns_200(self):
        """Test GET /api/obd/vehicle/{id} returns 200 with data or empty message."""
        response = self.session.get(f"{BASE_URL}/api/obd/vehicle/test123")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "vehicle_id" in data
        # Should have either data or message for empty
        assert "data" in data or "message" in data
        print(f"PASS: GET /api/obd/vehicle/test123 returns 200")
    
    def test_get_vehicle_obd_history_returns_200(self):
        """Test GET /api/obd/vehicle/{id}/history returns 200 with array."""
        response = self.session.get(f"{BASE_URL}/api/obd/vehicle/test123/history")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Expected array response"
        print(f"PASS: GET /api/obd/vehicle/test123/history returns 200 with {len(data)} records")
    
    def test_obd_endpoints_require_auth(self):
        """Test OBD endpoints require authentication."""
        unauthenticated = requests.Session()
        
        endpoints = [
            "/api/obd/vehicles",
            "/api/obd/vehicle/test123",
            "/api/obd/vehicle/test123/history"
        ]
        
        for endpoint in endpoints:
            response = unauthenticated.get(f"{BASE_URL}{endpoint}")
            assert response.status_code == 401, f"Expected 401 for {endpoint}, got {response.status_code}"
        
        print("PASS: All OBD endpoints require authentication")


class TestGPSEndpoints:
    """Test GPS tracking and trip detection endpoints."""
    
    @pytest.fixture(autouse=True)
    def setup_session(self):
        """Setup authenticated session for each test."""
        self.session = requests.Session()
        login_resp = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    
    def test_detect_trips_nonexistent_vehicle_returns_404(self):
        """Test POST /api/gps/detect-trips/nonexistent returns 404."""
        response = self.session.post(f"{BASE_URL}/api/gps/detect-trips/nonexistent")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        print("PASS: POST /api/gps/detect-trips/nonexistent returns 404")
    
    def test_get_live_positions_returns_200(self):
        """Test GET /api/gps/live-positions returns 200."""
        response = self.session.get(f"{BASE_URL}/api/gps/live-positions")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Expected array response"
        print(f"PASS: GET /api/gps/live-positions returns 200 with {len(data)} positions")
    
    def test_get_tcp_status_returns_200(self):
        """Test GET /api/gps/tcp-status returns 200."""
        response = self.session.get(f"{BASE_URL}/api/gps/tcp-status")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "running" in data
        assert "port" in data
        print(f"PASS: GET /api/gps/tcp-status returns 200 (running={data['running']}, port={data['port']})")
    
    def test_get_gps_devices_returns_200(self):
        """Test GET /api/gps/devices returns 200."""
        response = self.session.get(f"{BASE_URL}/api/gps/devices")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Expected array response"
        print(f"PASS: GET /api/gps/devices returns 200 with {len(data)} devices")
    
    def test_gps_endpoints_require_auth(self):
        """Test GPS endpoints require authentication."""
        unauthenticated = requests.Session()
        
        endpoints = [
            "/api/gps/live-positions",
            "/api/gps/tcp-status",
            "/api/gps/devices"
        ]
        
        for endpoint in endpoints:
            response = unauthenticated.get(f"{BASE_URL}{endpoint}")
            assert response.status_code == 401, f"Expected 401 for {endpoint}, got {response.status_code}"
        
        print("PASS: All GPS endpoints require authentication")


class TestExistingEndpoints:
    """Verify existing endpoints still work after new feature additions."""
    
    @pytest.fixture(autouse=True)
    def setup_session(self):
        """Setup authenticated session for each test."""
        self.session = requests.Session()
        login_resp = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    
    def test_get_vehicles_returns_200(self):
        """Test GET /api/vehicles still works."""
        response = self.session.get(f"{BASE_URL}/api/vehicles")
        assert response.status_code == 200
        print("PASS: GET /api/vehicles returns 200")
    
    def test_get_instructors_returns_200(self):
        """Test GET /api/instructors still works."""
        response = self.session.get(f"{BASE_URL}/api/instructors")
        assert response.status_code == 200
        print("PASS: GET /api/instructors returns 200")
    
    def test_get_logbook_returns_200(self):
        """Test GET /api/logbook still works."""
        response = self.session.get(f"{BASE_URL}/api/logbook")
        assert response.status_code == 200
        print("PASS: GET /api/logbook returns 200")
    
    def test_get_fuel_returns_200(self):
        """Test GET /api/fuel still works."""
        response = self.session.get(f"{BASE_URL}/api/fuel")
        assert response.status_code == 200
        print("PASS: GET /api/fuel returns 200")
    
    def test_get_fuel_analytics_returns_200(self):
        """Test GET /api/reports/fuel-analytics still works."""
        response = self.session.get(f"{BASE_URL}/api/reports/fuel-analytics")
        assert response.status_code == 200
        
        data = response.json()
        assert "summary" in data
        assert "vehicle_stats" in data
        print("PASS: GET /api/reports/fuel-analytics returns 200 with summary and vehicle_stats")
    
    def test_get_dashboard_returns_200(self):
        """Test GET /api/reports/dashboard still works."""
        response = self.session.get(f"{BASE_URL}/api/reports/dashboard")
        assert response.status_code == 200
        print("PASS: GET /api/reports/dashboard returns 200")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
