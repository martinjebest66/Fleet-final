# NOTE: live-server integration test — needs a running Fleet Manager.
# Configure with FLEET_BASE_URL / FLEET_ADMIN_EMAIL / FLEET_ADMIN_PASSWORD.
# Excluded from the default pytest run; see tests/integration/conftest.py.
"""
Test suite for Iteration 10 - New Features:
1. Maintenance (Údržba Vozidel) - CRUD operations, status computation, summary KPIs
2. Ruhavik Import - CSV/GPX GPS data import
3. Damage Notifications - Email notification trigger (RESEND_API_KEY empty, just verify endpoint works)
"""
import pytest
import requests
import os
from datetime import datetime, timedelta

BASE_URL = (os.environ.get('FLEET_BASE_URL') or os.environ.get('REACT_APP_BACKEND_URL', '')).rstrip('/')

# ======================== FIXTURES ========================

@pytest.fixture(scope="module")
def session():
    """Shared requests session"""
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin_session(session):
    """Authenticated admin session using cookies"""
    login_response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": os.environ.get("FLEET_ADMIN_EMAIL", ""), "password": os.environ.get("FLEET_ADMIN_PASSWORD", "")}
    )
    assert login_response.status_code == 200, f"Admin login failed: {login_response.text}"
    return session


@pytest.fixture(scope="module")
def test_vehicle_id(admin_session):
    """Get or create a test vehicle for maintenance/import tests"""
    # First try to get existing vehicles
    vehicles_res = admin_session.get(f"{BASE_URL}/api/vehicles")
    assert vehicles_res.status_code == 200
    vehicles = vehicles_res.json()
    
    if vehicles:
        return vehicles[0]["vehicle_id"]
    
    # Create a test vehicle if none exist
    create_res = admin_session.post(f"{BASE_URL}/api/vehicles", json={
        "brand": "TEST_Škoda",
        "model": "Octavia",
        "registration_plate": "TEST1234",
        "year": 2023,
        "vin": "TEST123456789",
        "fuel_type": "benzín",
        "transmission": "manuální",
        "category": "B"
    })
    assert create_res.status_code == 201, f"Failed to create test vehicle: {create_res.text}"
    return create_res.json()["vehicle_id"]


# ======================== MAINTENANCE CRUD TESTS ========================

class TestMaintenanceCRUD:
    """Test maintenance CRUD operations"""
    
    created_maintenance_ids = []
    
    def test_get_maintenance_items_empty_or_list(self, admin_session):
        """GET /api/maintenance returns 200 with list"""
        response = admin_session.get(f"{BASE_URL}/api/maintenance")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        print(f"✓ GET /api/maintenance returns {len(response.json())} items")
    
    def test_create_maintenance_stk(self, admin_session, test_vehicle_id):
        """POST /api/maintenance creates STK maintenance item"""
        future_date = (datetime.now() + timedelta(days=60)).strftime("%Y-%m-%d")
        payload = {
            "vehicle_id": test_vehicle_id,
            "type": "STK",
            "next_due_date": future_date,
            "notes": "TEST_STK kontrola"
        }
        response = admin_session.post(f"{BASE_URL}/api/maintenance", json=payload)
        assert response.status_code == 200, f"Create maintenance failed: {response.text}"
        
        data = response.json()
        assert data["type"] == "STK"
        assert data["vehicle_id"] == test_vehicle_id
        assert data["status"] == "ok"  # Future date = ok status
        assert "maintenance_id" in data
        
        self.__class__.created_maintenance_ids.append(data["maintenance_id"])
        print(f"✓ Created STK maintenance: {data['maintenance_id']} with status 'ok'")
    
    def test_create_maintenance_blizi_se_status(self, admin_session, test_vehicle_id):
        """Create maintenance with next_due_date within 30 days shows 'blíží se' status"""
        near_date = (datetime.now() + timedelta(days=15)).strftime("%Y-%m-%d")
        payload = {
            "vehicle_id": test_vehicle_id,
            "type": "olej",
            "next_due_date": near_date,
            "notes": "TEST_Oil change approaching"
        }
        response = admin_session.post(f"{BASE_URL}/api/maintenance", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "blíží se", f"Expected 'blíží se' but got '{data['status']}'"
        
        self.__class__.created_maintenance_ids.append(data["maintenance_id"])
        print(f"✓ Created maintenance with 'blíží se' status (due in 15 days)")
    
    def test_create_maintenance_po_terminu_status(self, admin_session, test_vehicle_id):
        """Create maintenance with next_due_date in past shows 'po termínu' status"""
        past_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
        payload = {
            "vehicle_id": test_vehicle_id,
            "type": "pneumatiky",
            "next_due_date": past_date,
            "notes": "TEST_Overdue tires"
        }
        response = admin_session.post(f"{BASE_URL}/api/maintenance", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "po termínu", f"Expected 'po termínu' but got '{data['status']}'"
        
        self.__class__.created_maintenance_ids.append(data["maintenance_id"])
        print(f"✓ Created maintenance with 'po termínu' status (overdue)")
    
    def test_create_maintenance_custom_type(self, admin_session, test_vehicle_id):
        """Create maintenance with custom type (vlastní)"""
        payload = {
            "vehicle_id": test_vehicle_id,
            "type": "vlastní",
            "custom_label": "TEST_Výměna filtru",
            "next_due_date": (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d"),
            "interval_months": 12,
            "interval_km": 15000,
            "notes": "TEST_Custom maintenance item"
        }
        response = admin_session.post(f"{BASE_URL}/api/maintenance", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        assert data["type"] == "vlastní"
        assert data["custom_label"] == "TEST_Výměna filtru"
        
        self.__class__.created_maintenance_ids.append(data["maintenance_id"])
        print(f"✓ Created custom maintenance item: {data['custom_label']}")
    
    def test_get_maintenance_summary(self, admin_session):
        """GET /api/maintenance/summary returns correct KPI counts"""
        response = admin_session.get(f"{BASE_URL}/api/maintenance/summary")
        assert response.status_code == 200
        
        data = response.json()
        assert "total" in data
        assert "overdue" in data
        assert "upcoming" in data
        assert "ok" in data
        
        # Verify counts are non-negative integers
        assert isinstance(data["total"], int) and data["total"] >= 0
        assert isinstance(data["overdue"], int) and data["overdue"] >= 0
        assert isinstance(data["upcoming"], int) and data["upcoming"] >= 0
        assert isinstance(data["ok"], int) and data["ok"] >= 0
        
        # Total should equal sum of statuses
        assert data["total"] == data["overdue"] + data["upcoming"] + data["ok"]
        
        print(f"✓ Maintenance summary: total={data['total']}, ok={data['ok']}, upcoming={data['upcoming']}, overdue={data['overdue']}")
    
    def test_update_maintenance_item(self, admin_session, test_vehicle_id):
        """PUT /api/maintenance/{id} updates maintenance item"""
        if not self.__class__.created_maintenance_ids:
            pytest.skip("No maintenance items to update")
        
        maintenance_id = self.__class__.created_maintenance_ids[0]
        new_date = (datetime.now() + timedelta(days=120)).strftime("%Y-%m-%d")
        payload = {
            "vehicle_id": test_vehicle_id,
            "type": "STK",
            "next_due_date": new_date,
            "notes": "TEST_Updated STK notes"
        }
        response = admin_session.put(f"{BASE_URL}/api/maintenance/{maintenance_id}", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        assert data["notes"] == "TEST_Updated STK notes"
        assert data["next_due_date"] == new_date
        print(f"✓ Updated maintenance item: {maintenance_id}")
    
    def test_delete_maintenance_item(self, admin_session):
        """DELETE /api/maintenance/{id} deletes maintenance item"""
        if not self.__class__.created_maintenance_ids:
            pytest.skip("No maintenance items to delete")
        
        maintenance_id = self.__class__.created_maintenance_ids.pop()
        response = admin_session.delete(f"{BASE_URL}/api/maintenance/{maintenance_id}")
        assert response.status_code == 200
        
        data = response.json()
        assert "message" in data
        
        # Verify deletion
        get_response = admin_session.get(f"{BASE_URL}/api/maintenance")
        items = get_response.json()
        assert not any(item["maintenance_id"] == maintenance_id for item in items)
        
        print(f"✓ Deleted maintenance item: {maintenance_id}")
    
    def test_filter_maintenance_by_vehicle(self, admin_session, test_vehicle_id):
        """GET /api/maintenance?vehicle_id=X filters by vehicle"""
        response = admin_session.get(f"{BASE_URL}/api/maintenance?vehicle_id={test_vehicle_id}")
        assert response.status_code == 200
        
        items = response.json()
        for item in items:
            assert item["vehicle_id"] == test_vehicle_id
        
        print(f"✓ Filtered maintenance by vehicle: {len(items)} items")
    
    def test_filter_maintenance_by_status(self, admin_session):
        """GET /api/maintenance?status=X filters by status"""
        for status in ["ok", "blíží se", "po termínu"]:
            response = admin_session.get(f"{BASE_URL}/api/maintenance?status={status}")
            assert response.status_code == 200
            
            items = response.json()
            for item in items:
                assert item["status"] == status
            
            print(f"✓ Filtered by status '{status}': {len(items)} items")
    
    @pytest.fixture(autouse=True, scope="class")
    def cleanup(self, admin_session):
        """Cleanup test maintenance items after all tests"""
        yield
        for mid in self.__class__.created_maintenance_ids:
            try:
                admin_session.delete(f"{BASE_URL}/api/maintenance/{mid}")
            except:
                pass


# ======================== RUHAVIK IMPORT TESTS ========================

class TestRuhavikImport:
    """Test Ruhavik GPS data import (CSV/GPX)"""
    
    def test_import_gpx_file(self, admin_session, test_vehicle_id):
        """POST /api/gps/import-ruhavik with GPX file imports trips"""
        # Create a simple GPX file content
        gpx_content = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
  <trk>
    <name>Test Track</name>
    <trkseg>
      <trkpt lat="50.0755" lon="14.4378">
        <time>2024-01-15T10:00:00Z</time>
        <speed>10</speed>
      </trkpt>
      <trkpt lat="50.0760" lon="14.4385">
        <time>2024-01-15T10:05:00Z</time>
        <speed>15</speed>
      </trkpt>
      <trkpt lat="50.0770" lon="14.4400">
        <time>2024-01-15T10:10:00Z</time>
        <speed>20</speed>
      </trkpt>
      <trkpt lat="50.0780" lon="14.4420">
        <time>2024-01-15T10:15:00Z</time>
        <speed>25</speed>
      </trkpt>
    </trkseg>
  </trk>
</gpx>"""
        
        files = {"file": ("test_track.gpx", gpx_content, "application/gpx+xml")}
        form_data = {"vehicle_id": test_vehicle_id}
        
        # Remove Content-Type header for multipart form data
        headers = {k: v for k, v in admin_session.headers.items() if k.lower() != 'content-type'}
        
        response = requests.post(
            f"{BASE_URL}/api/gps/import-ruhavik",
            files=files,
            data=form_data,
            cookies=admin_session.cookies,
            headers=headers
        )
        assert response.status_code == 200, f"GPX import failed: {response.text}"
        
        result = response.json()
        assert "message" in result
        assert "trips_count" in result
        assert "points_count" in result
        assert result["points_count"] >= 4
        
        print(f"✓ GPX import: {result['points_count']} points, {result['trips_count']} trips")
    
    def test_import_csv_file(self, admin_session, test_vehicle_id):
        """POST /api/gps/import-ruhavik with CSV file imports trips"""
        # Create a simple CSV file content
        csv_content = """latitude,longitude,timestamp,speed
50.0755,14.4378,2024-01-16T10:00:00Z,10
50.0760,14.4385,2024-01-16T10:05:00Z,15
50.0770,14.4400,2024-01-16T10:10:00Z,20
50.0780,14.4420,2024-01-16T10:15:00Z,25
50.0790,14.4440,2024-01-16T10:20:00Z,30"""
        
        files = {"file": ("test_track.csv", csv_content, "text/csv")}
        form_data = {"vehicle_id": test_vehicle_id}
        
        # Remove Content-Type header for multipart form data
        headers = {k: v for k, v in admin_session.headers.items() if k.lower() != 'content-type'}
        
        response = requests.post(
            f"{BASE_URL}/api/gps/import-ruhavik",
            files=files,
            data=form_data,
            cookies=admin_session.cookies,
            headers=headers
        )
        assert response.status_code == 200, f"CSV import failed: {response.text}"
        
        result = response.json()
        assert "message" in result
        assert "trips_count" in result
        assert "points_count" in result
        assert result["points_count"] >= 5
        
        print(f"✓ CSV import: {result['points_count']} points, {result['trips_count']} trips")
    
    def test_import_unsupported_format_returns_400(self, admin_session, test_vehicle_id):
        """POST /api/gps/import-ruhavik with unsupported format returns 400"""
        txt_content = "This is not a valid GPS file"
        
        files = {"file": ("test.txt", txt_content, "text/plain")}
        form_data = {"vehicle_id": test_vehicle_id}
        
        # Remove Content-Type header for multipart form data
        headers = {k: v for k, v in admin_session.headers.items() if k.lower() != 'content-type'}
        
        response = requests.post(
            f"{BASE_URL}/api/gps/import-ruhavik",
            files=files,
            data=form_data,
            cookies=admin_session.cookies,
            headers=headers
        )
        assert response.status_code == 400
        
        result = response.json()
        assert "detail" in result
        assert "Nepodporovaný formát" in result["detail"]
        
        print(f"✓ Unsupported format correctly returns 400: {result['detail']}")
    
    def test_import_invalid_vehicle_returns_404(self, admin_session):
        """POST /api/gps/import-ruhavik with invalid vehicle_id returns 404"""
        gpx_content = """<?xml version="1.0"?><gpx><trk><trkseg><trkpt lat="50" lon="14"/></trkseg></trk></gpx>"""
        
        files = {"file": ("test.gpx", gpx_content, "application/gpx+xml")}
        form_data = {"vehicle_id": "nonexistent_vehicle_id"}
        
        # Remove Content-Type header for multipart form data
        headers = {k: v for k, v in admin_session.headers.items() if k.lower() != 'content-type'}
        
        response = requests.post(
            f"{BASE_URL}/api/gps/import-ruhavik",
            files=files,
            data=form_data,
            cookies=admin_session.cookies,
            headers=headers
        )
        assert response.status_code == 404
        
        print("✓ Invalid vehicle_id correctly returns 404")
    
    def test_import_requires_auth(self, session, test_vehicle_id):
        """POST /api/gps/import-ruhavik without auth returns 401"""
        # Use a fresh session without auth
        gpx_content = """<?xml version="1.0"?><gpx><trk><trkseg><trkpt lat="50" lon="14"/></trkseg></trk></gpx>"""
        
        files = {"file": ("test.gpx", gpx_content, "application/gpx+xml")}
        form_data = {"vehicle_id": test_vehicle_id}
        
        response = requests.post(
            f"{BASE_URL}/api/gps/import-ruhavik",
            files=files,
            data=form_data
        )
        assert response.status_code == 401
        
        print("✓ Import endpoint requires authentication (401 without auth)")


# ======================== DAMAGE NOTIFICATION TESTS ========================

class TestDamageNotifications:
    """Test damage report creation with email notification trigger"""
    
    created_damage_ids = []
    
    def test_create_damage_report_authenticated(self, admin_session, test_vehicle_id):
        """POST /api/damages creates damage report (email notification triggered but won't send)"""
        payload = {
            "vehicle_id": test_vehicle_id,
            "description": "TEST_Škrábanec na dveřích",
            "severity": "nízká",
            "location_on_vehicle": "levé přední dveře",
            "reported_by": "Test User"
        }
        response = admin_session.post(f"{BASE_URL}/api/damages", json=payload)
        assert response.status_code == 200, f"Create damage failed: {response.text}"
        
        data = response.json()
        assert data["description"] == "TEST_Škrábanec na dveřích"
        assert data["severity"] == "nízká"
        assert data["status"] == "otevřeno"
        assert "damage_id" in data
        
        self.__class__.created_damage_ids.append(data["damage_id"])
        print(f"✓ Created damage report: {data['damage_id']} (email notification triggered, RESEND_API_KEY empty)")
    
    def test_create_public_damage_report(self, admin_session, test_vehicle_id):
        """POST /api/public/damages creates damage report via public endpoint"""
        # Use fresh session for public endpoint
        fresh_session = requests.Session()
        payload = {
            "vehicle_id": test_vehicle_id,
            "description": "TEST_Public damage report",
            "severity": "střední",
            "location_on_vehicle": "zadní nárazník",
            "reported_by": "Anonymous"
        }
        response = fresh_session.post(f"{BASE_URL}/api/public/damages", json=payload)
        assert response.status_code == 200, f"Create public damage failed: {response.text}"
        
        data = response.json()
        assert "message" in data
        assert "damage_id" in data
        
        self.__class__.created_damage_ids.append(data["damage_id"])
        print(f"✓ Created public damage report: {data['damage_id']}")
    
    def test_public_damage_invalid_vehicle_returns_404(self):
        """POST /api/public/damages with invalid vehicle returns 404"""
        fresh_session = requests.Session()
        payload = {
            "vehicle_id": "nonexistent_vehicle",
            "description": "Test",
            "severity": "nízká",
            "location_on_vehicle": "test",
            "reported_by": "Test"
        }
        response = fresh_session.post(f"{BASE_URL}/api/public/damages", json=payload)
        assert response.status_code == 404
        
        print("✓ Public damage with invalid vehicle returns 404")


# ======================== NAVIGATION TESTS ========================

class TestNavigation:
    """Test that new pages are accessible"""
    
    def test_maintenance_endpoint_accessible(self, admin_session):
        """GET /api/maintenance is accessible"""
        response = admin_session.get(f"{BASE_URL}/api/maintenance")
        assert response.status_code == 200
        print("✓ /api/maintenance endpoint accessible")
    
    def test_maintenance_summary_endpoint_accessible(self, admin_session):
        """GET /api/maintenance/summary is accessible"""
        response = admin_session.get(f"{BASE_URL}/api/maintenance/summary")
        assert response.status_code == 200
        print("✓ /api/maintenance/summary endpoint accessible")
    
    def test_api_root_accessible(self, admin_session):
        """GET /api/ returns API info"""
        response = admin_session.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        print("✓ API root accessible")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
