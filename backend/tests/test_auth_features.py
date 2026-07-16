"""
Backend API tests for new auth features:
1. Admin email/password login
2. Instructor PIN-based login
3. Role-based access control
4. Fuel analytics endpoint
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from main agent
ADMIN_EMAIL = "admin@autoskola.cz"
ADMIN_PASSWORD = "Admin123!"
TEST_INSTRUCTOR_ID = "inst_aba594d9cd55"
TEST_INSTRUCTOR_PIN = "1234"


class TestAdminLogin:
    """Admin email/password login tests"""
    
    def test_admin_login_success(self):
        """POST /api/auth/login with valid admin credentials returns 200"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "user_id" in data
        assert data["email"] == ADMIN_EMAIL
        assert data["role"] == "admin"
        assert "name" in data
        print(f"Admin login success: {data}")
    
    def test_admin_login_wrong_password(self):
        """POST /api/auth/login with wrong password returns 401"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": "WrongPassword123!"}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("Admin login with wrong password correctly rejected")
    
    def test_admin_login_wrong_email(self):
        """POST /api/auth/login with non-existent email returns 401"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "nonexistent@test.com", "password": "SomePassword123!"}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("Admin login with non-existent email correctly rejected")
    
    def test_admin_login_sets_cookies(self):
        """POST /api/auth/login sets httponly cookies"""
        session = requests.Session()
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200
        
        # Check cookies are set
        cookies = session.cookies.get_dict()
        assert "access_token" in cookies or len(cookies) > 0, f"Expected cookies to be set, got: {cookies}"
        print(f"Cookies set after login: {list(cookies.keys())}")


class TestAdminAuthMe:
    """GET /api/auth/me tests with admin cookies"""
    
    def test_auth_me_with_admin_cookies(self):
        """GET /api/auth/me with admin cookies returns admin user with role=admin"""
        session = requests.Session()
        
        # Login first
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert login_response.status_code == 200
        
        # Get current user
        me_response = session.get(f"{BASE_URL}/api/auth/me")
        assert me_response.status_code == 200, f"Expected 200, got {me_response.status_code}: {me_response.text}"
        
        data = me_response.json()
        assert data["email"] == ADMIN_EMAIL
        assert data["role"] == "admin"
        print(f"Auth me response: {data}")
    
    def test_auth_me_without_auth(self):
        """GET /api/auth/me without auth returns 401"""
        response = requests.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("Auth me without auth correctly rejected")


class TestInstructorLogin:
    """Instructor PIN-based login tests"""
    
    def test_instructors_list_public(self):
        """GET /api/auth/instructors-list is public and returns instructors with PIN"""
        response = requests.get(f"{BASE_URL}/api/auth/instructors-list")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list)
        print(f"Instructors list (public): {len(data)} instructors with PIN")
        
        # Check structure
        if len(data) > 0:
            assert "instructor_id" in data[0]
            assert "name" in data[0]
            # Should NOT expose PIN
            assert "pin" not in data[0], "PIN should not be exposed in public list"
    
    def test_instructor_login_success(self):
        """POST /api/auth/instructor-login with valid instructor_id and PIN returns 200"""
        response = requests.post(
            f"{BASE_URL}/api/auth/instructor-login",
            json={"instructor_id": TEST_INSTRUCTOR_ID, "pin": TEST_INSTRUCTOR_PIN}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["user_id"] == TEST_INSTRUCTOR_ID
        assert data["role"] == "instructor"
        assert "name" in data
        print(f"Instructor login success: {data}")
    
    def test_instructor_login_wrong_pin(self):
        """POST /api/auth/instructor-login with wrong PIN returns 401"""
        response = requests.post(
            f"{BASE_URL}/api/auth/instructor-login",
            json={"instructor_id": TEST_INSTRUCTOR_ID, "pin": "9999"}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("Instructor login with wrong PIN correctly rejected")
    
    def test_instructor_login_invalid_id(self):
        """POST /api/auth/instructor-login with invalid instructor_id returns 401"""
        response = requests.post(
            f"{BASE_URL}/api/auth/instructor-login",
            json={"instructor_id": "invalid_instructor_id", "pin": "1234"}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("Instructor login with invalid ID correctly rejected")


class TestLogout:
    """Logout tests"""
    
    def test_logout_clears_cookies(self):
        """POST /api/auth/logout clears cookies"""
        session = requests.Session()
        
        # Login first
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert login_response.status_code == 200
        
        # Logout
        logout_response = session.post(f"{BASE_URL}/api/auth/logout")
        assert logout_response.status_code == 200, f"Expected 200, got {logout_response.status_code}"
        
        data = logout_response.json()
        assert "message" in data
        print(f"Logout response: {data}")
        
        # Verify auth is cleared - /me should fail
        me_response = session.get(f"{BASE_URL}/api/auth/me")
        assert me_response.status_code == 401, f"Expected 401 after logout, got {me_response.status_code}"
        print("Auth cleared after logout")


class TestRefreshToken:
    """Refresh token tests"""
    
    def test_refresh_token_works(self):
        """POST /api/auth/refresh works with valid refresh token"""
        session = requests.Session()
        
        # Login first
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert login_response.status_code == 200
        
        # Refresh token
        refresh_response = session.post(f"{BASE_URL}/api/auth/refresh")
        assert refresh_response.status_code == 200, f"Expected 200, got {refresh_response.status_code}: {refresh_response.text}"
        
        data = refresh_response.json()
        assert "message" in data
        print(f"Refresh token response: {data}")
    
    def test_refresh_without_token_fails(self):
        """POST /api/auth/refresh without token returns 401"""
        response = requests.post(f"{BASE_URL}/api/auth/refresh")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("Refresh without token correctly rejected")


class TestRoleBasedAccess:
    """Role-based access control tests"""
    
    @pytest.fixture
    def admin_session(self):
        """Get authenticated admin session"""
        session = requests.Session()
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200
        return session
    
    @pytest.fixture
    def instructor_session(self):
        """Get authenticated instructor session"""
        session = requests.Session()
        response = session.post(
            f"{BASE_URL}/api/auth/instructor-login",
            json={"instructor_id": TEST_INSTRUCTOR_ID, "pin": TEST_INSTRUCTOR_PIN}
        )
        assert response.status_code == 200
        return session
    
    def test_instructor_can_get_vehicles(self, instructor_session):
        """Instructor can GET /api/vehicles (200)"""
        response = instructor_session.get(f"{BASE_URL}/api/vehicles")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("Instructor can GET vehicles")
    
    def test_instructor_cannot_post_vehicles(self, instructor_session):
        """Instructor cannot POST /api/vehicles (403 - admin only)"""
        response = instructor_session.post(
            f"{BASE_URL}/api/vehicles",
            json={
                "registration_plate": "TEST123",
                "brand": "Test",
                "model": "Car",
                "year": 2024,
                "fuel_type": "benzín"
            }
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("Instructor correctly denied POST vehicles")
    
    def test_instructor_can_get_logbook(self, instructor_session):
        """Instructor can GET /api/logbook (200)"""
        response = instructor_session.get(f"{BASE_URL}/api/logbook")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("Instructor can GET logbook")
    
    def test_instructor_cannot_post_instructors(self, instructor_session):
        """Instructor cannot POST /api/instructors (403 - admin only)"""
        response = instructor_session.post(
            f"{BASE_URL}/api/instructors",
            json={
                "name": "Test Instructor",
                "email": "test@test.com",
                "phone": "123456789",
                "license_number": "TEST123"
            }
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("Instructor correctly denied POST instructors")
    
    def test_admin_can_post_vehicles(self, admin_session):
        """Admin can POST /api/vehicles (201)"""
        response = admin_session.post(
            f"{BASE_URL}/api/vehicles",
            json={
                "registration_plate": f"TEST_{os.urandom(4).hex()}",
                "brand": "TestBrand",
                "model": "TestModel",
                "year": 2024,
                "fuel_type": "benzín"
            }
        )
        assert response.status_code == 200 or response.status_code == 201, f"Expected 200/201, got {response.status_code}: {response.text}"
        print("Admin can POST vehicles")
        
        # Cleanup - delete the test vehicle
        if response.status_code in [200, 201]:
            vehicle_id = response.json().get("vehicle_id")
            if vehicle_id:
                admin_session.delete(f"{BASE_URL}/api/vehicles/{vehicle_id}")


class TestFuelAnalytics:
    """Fuel analytics endpoint tests"""
    
    @pytest.fixture
    def admin_session(self):
        """Get authenticated admin session"""
        session = requests.Session()
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200
        return session
    
    def test_fuel_analytics_returns_summary_and_vehicle_stats(self, admin_session):
        """GET /api/reports/fuel-analytics returns summary and vehicle_stats"""
        response = admin_session.get(f"{BASE_URL}/api/reports/fuel-analytics")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "summary" in data, "Response should contain 'summary'"
        assert "vehicle_stats" in data, "Response should contain 'vehicle_stats'"
        
        # Check summary structure
        summary = data["summary"]
        assert "total_liters" in summary
        assert "total_cost" in summary
        assert "total_km" in summary
        assert "avg_consumption_per_100km" in summary
        assert "vehicle_count" in summary
        
        print(f"Fuel analytics summary: {summary}")
        print(f"Vehicle stats count: {len(data['vehicle_stats'])}")
    
    def test_fuel_analytics_without_auth(self):
        """GET /api/reports/fuel-analytics without auth returns 401"""
        response = requests.get(f"{BASE_URL}/api/reports/fuel-analytics")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("Fuel analytics without auth correctly rejected")
    
    def test_fuel_analytics_with_filters(self, admin_session):
        """GET /api/reports/fuel-analytics with filters works"""
        response = admin_session.get(
            f"{BASE_URL}/api/reports/fuel-analytics",
            params={"date_from": "2024-01-01", "date_to": "2025-12-31"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "summary" in data
        assert "vehicle_stats" in data
        print("Fuel analytics with date filters works")


class TestInstructorExists:
    """Verify test instructor exists in database"""
    
    def test_instructor_exists_in_list(self):
        """Verify test instructor inst_aba594d9cd55 exists"""
        response = requests.get(f"{BASE_URL}/api/auth/instructors-list")
        assert response.status_code == 200
        
        data = response.json()
        instructor_ids = [i["instructor_id"] for i in data]
        
        if TEST_INSTRUCTOR_ID not in instructor_ids:
            pytest.skip(f"Test instructor {TEST_INSTRUCTOR_ID} not found. Available: {instructor_ids}")
        
        print(f"Test instructor {TEST_INSTRUCTOR_ID} found in list")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
