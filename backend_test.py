#!/usr/bin/env python3
"""
Fleet Management API Testing Suite
Tests all backend endpoints for the driving school fleet management system.
"""

import requests
import sys
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

class FleetAPITester:
    def __init__(self, base_url: str = "https://logbook-optimize.preview.emergentagent.com/api"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})
        
        # Test tracking
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        self.passed_tests = []
        
        # Test data storage
        self.test_vehicle_id = None
        self.test_instructor_id = None
        self.test_logbook_id = None
        self.test_fuel_id = None
        self.test_damage_id = None
        self.test_handover_id = None

    def log_test(self, name: str, success: bool, details: str = ""):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            self.passed_tests.append(name)
            print(f"✅ {name}: PASSED {details}")
        else:
            self.failed_tests.append({"test": name, "details": details})
            print(f"❌ {name}: FAILED {details}")

    def test_health_check(self) -> bool:
        """Test API health check endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/")
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            if success:
                data = response.json()
                details += f", Message: {data.get('message', 'N/A')}"
            self.log_test("API Health Check", success, details)
            return success
        except Exception as e:
            self.log_test("API Health Check", False, f"Exception: {str(e)}")
            return False

    def test_public_endpoints(self) -> bool:
        """Test public QR endpoints that don't require auth"""
        all_passed = True
        
        # Test public vehicle QR endpoint with invalid code
        try:
            response = self.session.get(f"{self.base_url}/public/vehicle/invalid_code")
            success = response.status_code == 400  # Should return bad request for invalid code
            self.log_test("Public Vehicle QR (Invalid)", success, f"Status: {response.status_code}")
            if not success:
                all_passed = False
        except Exception as e:
            self.log_test("Public Vehicle QR (Invalid)", False, f"Exception: {str(e)}")
            all_passed = False

        return all_passed

    def test_auth_required_endpoints(self) -> bool:
        """Test endpoints that require authentication (should return 401)"""
        auth_endpoints = [
            ("GET", "/vehicles", "Get Vehicles"),
            ("GET", "/instructors", "Get Instructors"), 
            ("GET", "/logbook", "Get Logbook"),
            ("GET", "/fuel", "Get Fuel Entries"),
            ("GET", "/damages", "Get Damage Reports"),
            ("GET", "/handovers", "Get Handovers"),
            ("GET", "/qr-handovers", "Get QR Handovers"),
            ("GET", "/reports/dashboard", "Dashboard Stats"),
            ("GET", "/gps/trips", "GPS Trips")
        ]
        
        all_passed = True
        for method, endpoint, name in auth_endpoints:
            try:
                if method == "GET":
                    response = self.session.get(f"{self.base_url}{endpoint}")
                else:
                    response = self.session.post(f"{self.base_url}{endpoint}", json={})
                
                # Should return 401 Unauthorized without auth
                success = response.status_code == 401
                self.log_test(f"Auth Required - {name}", success, f"Status: {response.status_code}")
                if not success:
                    all_passed = False
            except Exception as e:
                self.log_test(f"Auth Required - {name}", False, f"Exception: {str(e)}")
                all_passed = False
        
        return all_passed

    def test_vehicle_crud_structure(self) -> bool:
        """Test vehicle CRUD endpoint structure (without auth)"""
        all_passed = True
        
        # Test POST /vehicles structure
        try:
            test_vehicle = {
                "registration_plate": "TEST123",
                "brand": "Test Brand",
                "model": "Test Model", 
                "year": 2023,
                "fuel_type": "benzín"
            }
            response = self.session.post(f"{self.base_url}/vehicles", json=test_vehicle)
            # Should return 401 (auth required) not 422 (validation error)
            success = response.status_code == 401
            self.log_test("Vehicle POST Structure", success, f"Status: {response.status_code}")
            if not success:
                all_passed = False
        except Exception as e:
            self.log_test("Vehicle POST Structure", False, f"Exception: {str(e)}")
            all_passed = False

        return all_passed

    def test_instructor_crud_structure(self) -> bool:
        """Test instructor CRUD endpoint structure (without auth)"""
        all_passed = True
        
        # Test POST /instructors structure
        try:
            test_instructor = {
                "name": "Test Instructor",
                "email": "test@example.com",
                "phone": "+420123456789",
                "license_number": "TEST123"
            }
            response = self.session.post(f"{self.base_url}/instructors", json=test_instructor)
            # Should return 401 (auth required) not 422 (validation error)
            success = response.status_code == 401
            self.log_test("Instructor POST Structure", success, f"Status: {response.status_code}")
            if not success:
                all_passed = False
        except Exception as e:
            self.log_test("Instructor POST Structure", False, f"Exception: {str(e)}")
            all_passed = False

        return all_passed

    def test_logbook_structure(self) -> bool:
        """Test logbook endpoint structure"""
        try:
            test_entry = {
                "vehicle_id": "test_vehicle",
                "date": "2024-01-15",
                "start_time": "09:00",
                "end_time": "10:30",
                "start_location": "Praha",
                "end_location": "Brno",
                "route_description": "Test route",
                "start_odometer": 1000,
                "end_odometer": 1150,
                "purpose": "výcvik"
            }
            response = self.session.post(f"{self.base_url}/logbook", json=test_entry)
            success = response.status_code == 401
            self.log_test("Logbook POST Structure", success, f"Status: {response.status_code}")
            return success
        except Exception as e:
            self.log_test("Logbook POST Structure", False, f"Exception: {str(e)}")
            return False

    def test_fuel_structure(self) -> bool:
        """Test fuel entry endpoint structure"""
        try:
            test_fuel = {
                "vehicle_id": "test_vehicle",
                "date": "2024-01-15",
                "odometer": 1000,
                "liters": 45.5,
                "price_per_liter": 35.50,
                "total_price": 1615.25,
                "fuel_station": "Test Station"
            }
            response = self.session.post(f"{self.base_url}/fuel", json=test_fuel)
            success = response.status_code == 401
            self.log_test("Fuel POST Structure", success, f"Status: {response.status_code}")
            return success
        except Exception as e:
            self.log_test("Fuel POST Structure", False, f"Exception: {str(e)}")
            return False

    def test_damage_structure(self) -> bool:
        """Test damage report endpoint structure"""
        try:
            test_damage = {
                "vehicle_id": "test_vehicle",
                "description": "Test damage description",
                "severity": "nízká",
                "location_on_vehicle": "Front bumper",
                "reported_by": "Test User"
            }
            response = self.session.post(f"{self.base_url}/damages", json=test_damage)
            success = response.status_code == 401
            self.log_test("Damage POST Structure", success, f"Status: {response.status_code}")
            return success
        except Exception as e:
            self.log_test("Damage POST Structure", False, f"Exception: {str(e)}")
            return False

    def test_handover_structure(self) -> bool:
        """Test handover protocol endpoint structure"""
        try:
            test_handover = {
                "vehicle_id": "test_vehicle",
                "instructor_id": "test_instructor",
                "type": "převzetí",
                "odometer": 1000,
                "fuel_level": 75,
                "exterior_condition": "dobrý",
                "interior_condition": "dobrý"
            }
            response = self.session.post(f"{self.base_url}/handovers", json=test_handover)
            success = response.status_code == 401
            self.log_test("Handover POST Structure", success, f"Status: {response.status_code}")
            return success
        except Exception as e:
            self.log_test("Handover POST Structure", False, f"Exception: {str(e)}")
            return False

    def test_gps_mock_import_structure(self) -> bool:
        """Test GPS mock import endpoint structure"""
        try:
            response = self.session.post(f"{self.base_url}/gps/import-mock", 
                                       params={"vehicle_id": "test_vehicle"})
            success = response.status_code == 401
            self.log_test("GPS Mock Import Structure", success, f"Status: {response.status_code}")
            return success
        except Exception as e:
            self.log_test("GPS Mock Import Structure", False, f"Exception: {str(e)}")
            return False

    def test_public_fuel_entry_structure(self) -> bool:
        """Test public fuel entry endpoint (should work without auth)"""
        try:
            test_fuel = {
                "vehicle_id": "nonexistent_vehicle",
                "date": "2024-01-15",
                "odometer": 1000,
                "liters": 45.5,
                "price_per_liter": 35.50,
                "total_price": 1615.25
            }
            response = self.session.post(f"{self.base_url}/public/fuel", json=test_fuel)
            # Should return 404 (vehicle not found) not 401 (auth required)
            success = response.status_code == 404
            self.log_test("Public Fuel Entry Structure", success, f"Status: {response.status_code}")
            return success
        except Exception as e:
            self.log_test("Public Fuel Entry Structure", False, f"Exception: {str(e)}")
            return False

    def test_public_damage_report_structure(self) -> bool:
        """Test public damage report endpoint (should work without auth)"""
        try:
            test_damage = {
                "vehicle_id": "nonexistent_vehicle",
                "description": "Test damage",
                "severity": "nízká",
                "location_on_vehicle": "Front"
            }
            response = self.session.post(f"{self.base_url}/public/damages", json=test_damage)
            # Should return 404 (vehicle not found) not 401 (auth required)
            success = response.status_code == 404
            self.log_test("Public Damage Report Structure", success, f"Status: {response.status_code}")
            return success
        except Exception as e:
            self.log_test("Public Damage Report Structure", False, f"Exception: {str(e)}")
            return False

    def test_qr_handover_endpoints(self) -> bool:
        """Test QR handover specific endpoints"""
        all_passed = True
        
        # Test public vehicle endpoint with handover QR code
        try:
            response = self.session.get(f"{self.base_url}/public/vehicle/handover_veh_test123")
            # Should return 404 for non-existent vehicle, but endpoint should exist
            success = response.status_code in [404, 200]
            details = f"Status: {response.status_code}"
            if response.status_code == 200:
                data = response.json()
                if data.get('qr_type') == 'handover':
                    details += ", QR type: handover ✓"
                else:
                    success = False
                    details += f", QR type: {data.get('qr_type')} (expected: handover)"
            self.log_test("Public Vehicle Handover QR", success, details)
            if not success:
                all_passed = False
        except Exception as e:
            self.log_test("Public Vehicle Handover QR", False, f"Exception: {str(e)}")
            all_passed = False

        # Test public QR handover submission endpoint structure
        try:
            test_handover = {
                "vehicle_id": "nonexistent_vehicle",
                "handler_name": "Test Handler",
                "handler_type": "převzetí",
                "odometer": 1000,
                "fuel_level": 50,
                "fluid_checks": {
                    "engine_oil": True,
                    "coolant": True,
                    "brake_fluid": True,
                    "windshield_washer": True,
                    "other_fluids": True
                },
                "photos": [
                    {"photo_type": "front", "photo_url": "data:image/jpeg;base64,test", "timestamp": "2024-01-01T10:00:00Z"},
                    {"photo_type": "rear", "photo_url": "data:image/jpeg;base64,test", "timestamp": "2024-01-01T10:01:00Z"},
                    {"photo_type": "left", "photo_url": "data:image/jpeg;base64,test", "timestamp": "2024-01-01T10:02:00Z"},
                    {"photo_type": "right", "photo_url": "data:image/jpeg;base64,test", "timestamp": "2024-01-01T10:03:00Z"},
                    {"photo_type": "interior", "photo_url": "data:image/jpeg;base64,test", "timestamp": "2024-01-01T10:04:00Z"},
                    {"photo_type": "dashboard", "photo_url": "data:image/jpeg;base64,test", "timestamp": "2024-01-01T10:05:00Z"}
                ]
            }
            response = self.session.post(f"{self.base_url}/public/qr-handover", json=test_handover)
            # Should return 404 (vehicle not found) not 401 (auth required) or 422 (validation error)
            success = response.status_code == 404
            self.log_test("Public QR Handover Structure", success, f"Status: {response.status_code}")
            if not success:
                all_passed = False
        except Exception as e:
            self.log_test("Public QR Handover Structure", False, f"Exception: {str(e)}")
            all_passed = False

        # Test QR handover validation - missing photos
        try:
            test_handover_incomplete = {
                "vehicle_id": "nonexistent_vehicle",
                "handler_name": "Test Handler",
                "handler_type": "převzetí",
                "odometer": 1000,
                "fuel_level": 50,
                "fluid_checks": {
                    "engine_oil": True,
                    "coolant": True,
                    "brake_fluid": True,
                    "windshield_washer": True,
                    "other_fluids": True
                },
                "photos": [
                    {"photo_type": "front", "photo_url": "data:image/jpeg;base64,test", "timestamp": "2024-01-01T10:00:00Z"}
                ]  # Missing 5 required photos
            }
            response = self.session.post(f"{self.base_url}/public/qr-handover", json=test_handover_incomplete)
            # Should return 400 for missing photos (validation error)
            success = response.status_code == 400
            details = f"Status: {response.status_code}"
            if success and response.status_code == 400:
                try:
                    error_data = response.json()
                    if "Chybí požadované fotografie" in error_data.get('detail', ''):
                        details += ", Validation: Missing photos detected ✓"
                    else:
                        details += f", Error: {error_data.get('detail', 'Unknown')}"
                except:
                    pass
            self.log_test("QR Handover Photo Validation", success, details)
            if not success:
                all_passed = False
        except Exception as e:
            self.log_test("QR Handover Photo Validation", False, f"Exception: {str(e)}")
            all_passed = False

        # Test QR handover validation - incomplete fluid checks
        try:
            test_handover_incomplete_fluids = {
                "vehicle_id": "nonexistent_vehicle",
                "handler_name": "Test Handler",
                "handler_type": "převzetí",
                "odometer": 1000,
                "fuel_level": 50,
                "fluid_checks": {
                    "engine_oil": True,
                    "coolant": False,  # Not checked
                    "brake_fluid": True,
                    "windshield_washer": True,
                    "other_fluids": True
                },
                "photos": [
                    {"photo_type": "front", "photo_url": "data:image/jpeg;base64,test", "timestamp": "2024-01-01T10:00:00Z"},
                    {"photo_type": "rear", "photo_url": "data:image/jpeg;base64,test", "timestamp": "2024-01-01T10:01:00Z"},
                    {"photo_type": "left", "photo_url": "data:image/jpeg;base64,test", "timestamp": "2024-01-01T10:02:00Z"},
                    {"photo_type": "right", "photo_url": "data:image/jpeg;base64,test", "timestamp": "2024-01-01T10:03:00Z"},
                    {"photo_type": "interior", "photo_url": "data:image/jpeg;base64,test", "timestamp": "2024-01-01T10:04:00Z"},
                    {"photo_type": "dashboard", "photo_url": "data:image/jpeg;base64,test", "timestamp": "2024-01-01T10:05:00Z"}
                ]
            }
            response = self.session.post(f"{self.base_url}/public/qr-handover", json=test_handover_incomplete_fluids)
            # Should return 400 for incomplete fluid checks
            success = response.status_code == 400
            details = f"Status: {response.status_code}"
            if success and response.status_code == 400:
                try:
                    error_data = response.json()
                    if "provozní kapaliny musí být zkontrolovány" in error_data.get('detail', ''):
                        details += ", Validation: Fluid checks validation ✓"
                    else:
                        details += f", Error: {error_data.get('detail', 'Unknown')}"
                except:
                    pass
            self.log_test("QR Handover Fluid Validation", success, details)
            if not success:
                all_passed = False
        except Exception as e:
            self.log_test("QR Handover Fluid Validation", False, f"Exception: {str(e)}")
            all_passed = False

        # Test auth-required QR handover list endpoint
        try:
            response = self.session.get(f"{self.base_url}/qr-handovers")
            success = response.status_code == 401  # Should require auth
            self.log_test("QR Handovers List Auth", success, f"Status: {response.status_code}")
            if not success:
                all_passed = False
        except Exception as e:
            self.log_test("QR Handovers List Auth", False, f"Exception: {str(e)}")
            all_passed = False

        return all_passed

    def run_all_tests(self) -> Dict[str, Any]:
        """Run all backend API tests"""
        print("🚀 Starting Fleet Management API Tests")
        print("=" * 50)
        
        # Test basic connectivity
        if not self.test_health_check():
            print("❌ Health check failed - stopping tests")
            return self.get_results()
        
        # Test public endpoints
        print("\n📋 Testing Public Endpoints...")
        self.test_public_endpoints()
        self.test_public_fuel_entry_structure()
        self.test_public_damage_report_structure()
        
        # Test QR handover endpoints
        print("\n🤝 Testing QR Handover Endpoints...")
        self.test_qr_handover_endpoints()
        
        # Test auth-required endpoints
        print("\n🔒 Testing Auth-Required Endpoints...")
        self.test_auth_required_endpoints()
        
        # Test CRUD endpoint structures
        print("\n🏗️ Testing CRUD Endpoint Structures...")
        self.test_vehicle_crud_structure()
        self.test_instructor_crud_structure()
        self.test_logbook_structure()
        self.test_fuel_structure()
        self.test_damage_structure()
        self.test_handover_structure()
        self.test_gps_mock_import_structure()
        
        return self.get_results()

    def get_results(self) -> Dict[str, Any]:
        """Get test results summary"""
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        
        return {
            "total_tests": self.tests_run,
            "passed": self.tests_passed,
            "failed": len(self.failed_tests),
            "success_rate": round(success_rate, 1),
            "passed_tests": self.passed_tests,
            "failed_tests": self.failed_tests
        }

    def print_summary(self):
        """Print test summary"""
        results = self.get_results()
        print("\n" + "=" * 50)
        print("📊 TEST SUMMARY")
        print("=" * 50)
        print(f"Total Tests: {results['total_tests']}")
        print(f"Passed: {results['passed']}")
        print(f"Failed: {results['failed']}")
        print(f"Success Rate: {results['success_rate']}%")
        
        if results['failed_tests']:
            print("\n❌ Failed Tests:")
            for test in results['failed_tests']:
                print(f"  - {test['test']}: {test['details']}")
        
        print("\n✅ Passed Tests:")
        for test in results['passed_tests']:
            print(f"  - {test}")

def main():
    """Main test execution"""
    tester = FleetAPITester()
    results = tester.run_all_tests()
    tester.print_summary()
    
    # Return appropriate exit code
    return 0 if results['failed'] == 0 else 1

if __name__ == "__main__":
    sys.exit(main())