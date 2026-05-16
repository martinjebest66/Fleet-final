"""
Fleet Management API Tests - Iteration 7
Tests for new features: Teltonika FMB003 GPS tracker TCP receiver with Codec 8/8E parser
Plus verification of existing protected endpoints

New endpoints tested:
- GET /api/gps/tcp-status - TCP server status
- GET /api/gps/devices - List GPS devices
- POST /api/gps/devices - Register GPS device
- DELETE /api/gps/devices/{device_id} - Delete GPS device
- POST /api/gps/test-teltonika - Test device simulation
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestHealthCheck:
    """Health check endpoint tests"""
    
    def test_api_root_returns_200(self):
        """GET /api/ should return 200 with welcome message"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "Fleet Management API" in data["message"]
        print("✓ Health check passed - API root returns 200")


class TestNewGPSDeviceEndpoints:
    """Tests for new GPS device management endpoints (Teltonika FMB003)"""
    
    def test_gps_tcp_status_returns_401_without_auth(self):
        """GET /api/gps/tcp-status should return 401 without auth"""
        response = requests.get(f"{BASE_URL}/api/gps/tcp-status")
        assert response.status_code == 401
        print("✓ TCP status endpoint exists and requires auth (401)")
    
    def test_gps_devices_returns_401_without_auth(self):
        """GET /api/gps/devices should return 401 without auth"""
        response = requests.get(f"{BASE_URL}/api/gps/devices")
        assert response.status_code == 401
        print("✓ GPS devices list endpoint exists and requires auth (401)")
    
    def test_gps_devices_post_returns_401_without_auth(self):
        """POST /api/gps/devices should return 401 without auth"""
        response = requests.post(f"{BASE_URL}/api/gps/devices", json={
            "imei": "352625090000001",
            "vehicle_id": "test_vehicle",
            "name": "Test Tracker"
        })
        assert response.status_code == 401
        print("✓ GPS device registration endpoint exists and requires auth (401)")
    
    def test_gps_devices_delete_returns_401_without_auth(self):
        """DELETE /api/gps/devices/{device_id} should return 401 without auth"""
        response = requests.delete(f"{BASE_URL}/api/gps/devices/test123")
        assert response.status_code == 401
        print("✓ GPS device delete endpoint exists and requires auth (401)")
    
    def test_gps_test_teltonika_returns_401_without_auth(self):
        """POST /api/gps/test-teltonika should return 401 without auth"""
        response = requests.post(f"{BASE_URL}/api/gps/test-teltonika?imei=352625090000001")
        assert response.status_code == 401
        print("✓ Test Teltonika endpoint exists and requires auth (401)")


class TestPDFExportEndpoint:
    """Tests for PDF export feature"""
    
    def test_logbook_export_pdf_returns_401_without_auth(self):
        """GET /api/logbook/export-pdf should return 401 without auth"""
        response = requests.get(f"{BASE_URL}/api/logbook/export-pdf")
        assert response.status_code == 401
        print("✓ PDF export endpoint exists and requires auth (401)")


class TestLiveGPSEndpoints:
    """Tests for Live GPS tracking endpoints"""
    
    def test_gps_live_positions_returns_401_without_auth(self):
        """GET /api/gps/live-positions should return 401 without auth"""
        response = requests.get(f"{BASE_URL}/api/gps/live-positions")
        assert response.status_code == 401
        print("✓ Live positions endpoint exists and requires auth (401)")
    
    def test_gps_simulate_live_returns_401_without_auth(self):
        """POST /api/gps/simulate-live should return 401 without auth"""
        response = requests.post(f"{BASE_URL}/api/gps/simulate-live")
        assert response.status_code == 401
        print("✓ Simulate live endpoint exists and requires auth (401)")
    
    def test_gps_vehicle_history_returns_401_without_auth(self):
        """GET /api/gps/vehicle-history/{vehicle_id} should return 401 without auth"""
        response = requests.get(f"{BASE_URL}/api/gps/vehicle-history/test123")
        assert response.status_code == 401
        print("✓ Vehicle history endpoint exists and requires auth (401)")


class TestExistingProtectedEndpoints:
    """Verify all existing protected endpoints still return 401 without auth"""
    
    def test_vehicles_returns_401(self):
        """GET /api/vehicles should return 401 without auth"""
        response = requests.get(f"{BASE_URL}/api/vehicles")
        assert response.status_code == 401
        print("✓ /api/vehicles requires auth (401)")
    
    def test_instructors_returns_401(self):
        """GET /api/instructors should return 401 without auth"""
        response = requests.get(f"{BASE_URL}/api/instructors")
        assert response.status_code == 401
        print("✓ /api/instructors requires auth (401)")
    
    def test_logbook_returns_401(self):
        """GET /api/logbook should return 401 without auth"""
        response = requests.get(f"{BASE_URL}/api/logbook")
        assert response.status_code == 401
        print("✓ /api/logbook requires auth (401)")
    
    def test_fuel_returns_401(self):
        """GET /api/fuel should return 401 without auth"""
        response = requests.get(f"{BASE_URL}/api/fuel")
        assert response.status_code == 401
        print("✓ /api/fuel requires auth (401)")
    
    def test_damages_returns_401(self):
        """GET /api/damages should return 401 without auth"""
        response = requests.get(f"{BASE_URL}/api/damages")
        assert response.status_code == 401
        print("✓ /api/damages requires auth (401)")
    
    def test_handovers_returns_401(self):
        """GET /api/handovers should return 401 without auth"""
        response = requests.get(f"{BASE_URL}/api/handovers")
        assert response.status_code == 401
        print("✓ /api/handovers requires auth (401)")
    
    def test_qr_handovers_returns_401(self):
        """GET /api/qr-handovers should return 401 without auth"""
        response = requests.get(f"{BASE_URL}/api/qr-handovers")
        assert response.status_code == 401
        print("✓ /api/qr-handovers requires auth (401)")
    
    def test_reports_dashboard_returns_401(self):
        """GET /api/reports/dashboard should return 401 without auth"""
        response = requests.get(f"{BASE_URL}/api/reports/dashboard")
        assert response.status_code == 401
        print("✓ /api/reports/dashboard requires auth (401)")
    
    def test_reports_km_stats_returns_401(self):
        """GET /api/reports/km-stats should return 401 without auth"""
        response = requests.get(f"{BASE_URL}/api/reports/km-stats?date_from=2024-01-01&date_to=2024-12-31")
        assert response.status_code == 401
        print("✓ /api/reports/km-stats requires auth (401)")
    
    def test_gps_trips_returns_401(self):
        """GET /api/gps/trips should return 401 without auth"""
        response = requests.get(f"{BASE_URL}/api/gps/trips")
        assert response.status_code == 401
        print("✓ /api/gps/trips requires auth (401)")
    
    def test_gps_import_mock_returns_401(self):
        """POST /api/gps/import-mock should return 401 without auth"""
        response = requests.post(f"{BASE_URL}/api/gps/import-mock?vehicle_id=test123")
        assert response.status_code == 401
        print("✓ /api/gps/import-mock requires auth (401)")


class TestPublicEndpoints:
    """Verify public endpoints work without auth"""
    
    def test_public_vehicle_fuel_returns_404_for_nonexistent(self):
        """GET /api/public/vehicle/fuel_test123 should return 404 for non-existent vehicle"""
        response = requests.get(f"{BASE_URL}/api/public/vehicle/fuel_test123")
        assert response.status_code == 404
        print("✓ Public vehicle endpoint returns 404 for non-existent vehicle")
    
    def test_public_vehicle_damage_returns_404_for_nonexistent(self):
        """GET /api/public/vehicle/damage_test123 should return 404 for non-existent vehicle"""
        response = requests.get(f"{BASE_URL}/api/public/vehicle/damage_test123")
        assert response.status_code == 404
        print("✓ Public damage endpoint returns 404 for non-existent vehicle")
    
    def test_public_vehicle_handover_returns_404_for_nonexistent(self):
        """GET /api/public/vehicle/handover_test123 should return 404 for non-existent vehicle"""
        response = requests.get(f"{BASE_URL}/api/public/vehicle/handover_test123")
        assert response.status_code == 404
        print("✓ Public handover endpoint returns 404 for non-existent vehicle")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
