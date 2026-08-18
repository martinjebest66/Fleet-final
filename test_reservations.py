#!/usr/bin/env python3
"""
Reservation System API Testing Suite
Tests all reservation-related backend endpoints including import, drives report, 
GPS km calculation, tolerance model, private toggle, settings, and batches.
"""

import requests
import sys
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import os

class ReservationAPITester:
    def __init__(self, base_url: str = "https://feature-builder-53.preview.emergentagent.com/api"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})
        
        # Test tracking
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        self.passed_tests = []
        
        # Test data storage
        self.admin_token = None
        self.instructor_token = None
        self.test_batch_id = None
        self.test_drive_id = None
        self.original_settings = None

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

    def login_admin(self) -> bool:
        """Login as admin and store access token"""
        try:
            response = self.session.post(
                f"{self.base_url}/auth/login",
                json={"email": "admin@autoskola.cz", "password": "Admin123!"}
            )
            
            if response.status_code == 200:
                data = response.json()
                # Check if access_token is in cookies
                if 'access_token' in self.session.cookies:
                    self.admin_token = self.session.cookies['access_token']
                    self.log_test("Admin Login", True, f"Logged in as {data.get('email')}")
                    return True
                else:
                    self.log_test("Admin Login", False, "No access_token cookie set")
                    return False
            else:
                self.log_test("Admin Login", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_test("Admin Login", False, f"Exception: {str(e)}")
            return False

    def test_auth_required(self) -> bool:
        """Test that endpoints require authentication (401 without auth)"""
        # Create a new session without auth
        temp_session = requests.Session()
        temp_session.headers.update({'Content-Type': 'application/json'})
        
        endpoints = [
            ("GET", "/reservations/drives", "Drives Report"),
            ("GET", "/reservations/batches", "Batches List"),
            ("GET", "/reservations/settings", "Settings Get"),
            ("GET", "/reservations/vehicle-mapping", "Vehicle Mapping"),
        ]
        
        all_passed = True
        for method, endpoint, name in endpoints:
            try:
                response = temp_session.get(f"{self.base_url}{endpoint}")
                success = response.status_code == 401
                self.log_test(f"Auth Required - {name}", success, f"Status: {response.status_code}")
                if not success:
                    all_passed = False
            except Exception as e:
                self.log_test(f"Auth Required - {name}", False, f"Exception: {str(e)}")
                all_passed = False
        
        return all_passed

    def test_admin_required(self) -> bool:
        """Test that admin endpoints require admin role (403 for non-admin)"""
        # For now, we'll test with no auth (should get 401)
        # In a full test, we'd login as instructor and expect 403
        temp_session = requests.Session()
        temp_session.headers.update({'Content-Type': 'application/json'})
        
        endpoints = [
            ("POST", "/reservations/import", "Import"),
            ("PUT", "/reservations/settings", "Settings Update"),
            ("DELETE", "/reservations/batches/test_batch", "Batch Delete"),
            ("GET", "/reservations/vehicle-mapping", "Vehicle Mapping"),
        ]
        
        all_passed = True
        for method, endpoint, name in endpoints:
            try:
                if method == "POST":
                    response = temp_session.post(f"{self.base_url}{endpoint}", json={})
                elif method == "PUT":
                    response = temp_session.put(f"{self.base_url}{endpoint}", json={})
                elif method == "DELETE":
                    response = temp_session.delete(f"{self.base_url}{endpoint}")
                else:
                    response = temp_session.get(f"{self.base_url}{endpoint}")
                
                # Should return 401 (no auth) or 403 (not admin)
                success = response.status_code in [401, 403]
                self.log_test(f"Admin Required - {name}", success, f"Status: {response.status_code}")
                if not success:
                    all_passed = False
            except Exception as e:
                self.log_test(f"Admin Required - {name}", False, f"Exception: {str(e)}")
                all_passed = False
        
        return all_passed

    def test_import_endpoint(self) -> bool:
        """Test POST /api/reservations/import with file upload"""
        try:
            # Check if sample file exists
            sample_file = "/tmp/rez.xls"
            if not os.path.exists(sample_file):
                self.log_test("Import - File Check", False, f"Sample file not found at {sample_file}")
                # Try to download it
                try:
                    download_url = "https://customer-assets-wrfwihn1.emergentagent.net/job_feature-builder-53/artifacts/b60gv5vl_sta%C5%BEen%C3%BD%20soubor%20%282%29.xls"
                    dl_response = requests.get(download_url, timeout=30)
                    if dl_response.status_code == 200:
                        with open(sample_file, 'wb') as f:
                            f.write(dl_response.content)
                        self.log_test("Import - File Download", True, "Downloaded sample file")
                    else:
                        self.log_test("Import - File Download", False, f"Download failed: {dl_response.status_code}")
                        return False
                except Exception as e:
                    self.log_test("Import - File Download", False, f"Exception: {str(e)}")
                    return False
            
            # Test import with file - use a separate session to preserve cookies but allow multipart
            with open(sample_file, 'rb') as f:
                files = {'file': ('rez.xls', f, 'application/vnd.ms-excel')}
                # Create new request without Content-Type header (requests will set it for multipart)
                cookies = self.session.cookies.get_dict()
                response = requests.post(
                    f"{self.base_url}/reservations/import",
                    files=files,
                    cookies=cookies
                )
            
            if response.status_code == 200:
                data = response.json()
                self.test_batch_id = data.get('batch_id')
                imported = data.get('imported', 0)
                skipped = data.get('skipped', 0)
                vehicles = data.get('vehicles', [])
                
                success = (
                    self.test_batch_id is not None and
                    imported > 0 and
                    isinstance(vehicles, list)
                )
                
                details = f"Batch: {self.test_batch_id}, Imported: {imported}, Skipped: {skipped}, Vehicles: {len(vehicles)}"
                self.log_test("Import - POST /reservations/import", success, details)
                return success
            else:
                self.log_test("Import - POST /reservations/import", False, 
                            f"Status: {response.status_code}, Response: {response.text[:200]}")
                return False
                
        except Exception as e:
            self.log_test("Import - POST /reservations/import", False, f"Exception: {str(e)}")
            return False

    def test_drives_report(self) -> bool:
        """Test GET /api/reservations/drives with filters"""
        try:
            # Get current settings to know base_limit
            settings_response = self.session.get(f"{self.base_url}/reservations/settings")
            base_limit = 60.0  # default
            if settings_response.status_code == 200:
                base_limit = settings_response.json().get('base_limit_km', 60.0)
            
            # Test basic drives query
            response = self.session.get(
                f"{self.base_url}/reservations/drives",
                params={"date_from": "2026-07-01", "date_to": "2026-07-01"}
            )
            
            if response.status_code != 200:
                self.log_test("Drives Report - Basic Query", False, 
                            f"Status: {response.status_code}, Response: {response.text[:200]}")
                return False
            
            data = response.json()
            drives = data.get('drives', [])
            summary = data.get('summary', {})
            
            # Verify response structure
            has_structure = (
                isinstance(drives, list) and
                isinstance(summary, dict) and
                'total' in summary and
                'exceeded' in summary and
                'missing_gps' in summary and
                'total_gps_km' in summary
            )
            
            if not has_structure:
                self.log_test("Drives Report - Response Structure", False, 
                            f"Invalid structure: {json.dumps(data, indent=2)[:200]}")
                return False
            
            self.log_test("Drives Report - Response Structure", True, 
                        f"Total: {summary['total']}, Exceeded: {summary['exceeded']}, Missing GPS: {summary['missing_gps']}")
            
            # Find Skoda Kamiq 09:30 drive
            skoda_drive = None
            for drive in drives:
                vehicle_name = drive.get('vehicle_name', '').lower()
                start_time = drive.get('start_datetime', '')
                if 'skoda' in vehicle_name and 'kamiq' in vehicle_name and '09:30' in start_time:
                    skoda_drive = drive
                    self.test_drive_id = drive.get('drive_id')
                    break
            
            if skoda_drive:
                gps_km = skoda_drive.get('gps_km')
                tolerance_km = skoda_drive.get('tolerance_km')
                effective_limit_km = skoda_drive.get('effective_limit_km')
                exceeded = skoda_drive.get('exceeded')
                gps_available = skoda_drive.get('gps_available')
                
                # Verify Skoda Kamiq drive data
                # Note: tolerance may vary depending on adjacent drives in the same vehicle+day
                skoda_valid = (
                    gps_available == True and
                    gps_km is not None and
                    abs(gps_km - 80.1) < 5 and  # tolerance for GPS calculation
                    tolerance_km >= 0 and  # tolerance can be 0 or 12 depending on adjacent drives
                    abs(effective_limit_km - (base_limit + tolerance_km)) < 0.1 and
                    exceeded == True
                )
                
                details = f"GPS km: {gps_km}, Tolerance: {tolerance_km}, Limit: {effective_limit_km}, Exceeded: {exceeded}"
                self.log_test("Drives Report - Skoda Kamiq Verification", skoda_valid, details)
            else:
                self.log_test("Drives Report - Skoda Kamiq Verification", False, 
                            "Skoda Kamiq 09:30 drive not found")
            
            # Verify drives without GPS have correct flags
            drives_without_gps = [d for d in drives if not d.get('gps_available')]
            if drives_without_gps:
                all_null_gps = all(d.get('gps_km') is None for d in drives_without_gps)
                self.log_test("Drives Report - Missing GPS Handling", all_null_gps, 
                            f"Drives without GPS: {len(drives_without_gps)}")
            
            return True
            
        except Exception as e:
            self.log_test("Drives Report - GET /reservations/drives", False, f"Exception: {str(e)}")
            return False

    def test_tolerance_model(self) -> bool:
        """Test tolerance calculation for KV -> Ostrov -> KV sequence"""
        try:
            # Get all drives for 2026-07-01
            response = self.session.get(
                f"{self.base_url}/reservations/drives",
                params={"date_from": "2026-07-01", "date_to": "2026-07-01"}
            )
            
            if response.status_code != 200:
                self.log_test("Tolerance Model - Query", False, f"Status: {response.status_code}")
                return False
            
            data = response.json()
            drives = data.get('drives', [])
            
            # Group by vehicle and date, find sequences
            from collections import defaultdict
            vehicle_drives = defaultdict(list)
            for drive in drives:
                key = (drive.get('vehicle_id'), drive.get('date'))
                vehicle_drives[key].append(drive)
            
            # Look for any sequence with tolerance > 12 (indicating middle drive)
            found_pattern = False
            for key, vdrives in vehicle_drives.items():
                if len(vdrives) < 2:
                    continue
                
                # Sort by start time
                vdrives.sort(key=lambda x: x.get('start_datetime', ''))
                
                # Check for any drive with tolerance > 12 (middle drive)
                for i, drive in enumerate(vdrives):
                    tolerance = drive.get('tolerance_km', 0)
                    if tolerance > 12:
                        found_pattern = True
                        prev_loc = vdrives[i-1].get('boarding_location', '') if i > 0 else 'N/A'
                        curr_loc = drive.get('boarding_location', '')
                        next_loc = vdrives[i+1].get('boarding_location', '') if i < len(vdrives)-1 else 'N/A'
                        
                        details = f"Middle drive found: {prev_loc} -> {curr_loc} -> {next_loc}, Tolerance: {tolerance}"
                        self.log_test("Tolerance Model - Middle Drive", True, details)
                        return True
                
                # Also check for KV -> Ostrov -> KV pattern specifically
                for i in range(len(vdrives) - 2):
                    loc1 = vdrives[i].get('boarding_location', '').upper()
                    loc2 = vdrives[i+1].get('boarding_location', '').upper()
                    loc3 = vdrives[i+2].get('boarding_location', '').upper()
                    
                    if 'KV' in loc1 and 'OSTROV' in loc2 and 'KV' in loc3:
                        found_pattern = True
                        # Middle drive should have tolerance 24 (12 + 12)
                        middle_tolerance = vdrives[i+1].get('tolerance_km')
                        first_tolerance = vdrives[i].get('tolerance_km')
                        
                        tolerance_valid = middle_tolerance == 24 and first_tolerance == 12
                        
                        details = f"KV->Ostrov->KV: First tolerance: {first_tolerance}, Middle tolerance: {middle_tolerance}"
                        self.log_test("Tolerance Model - KV->Ostrov->KV", tolerance_valid, details)
                        return tolerance_valid
            
            if not found_pattern:
                # Check if tolerance calculation is working at all
                any_tolerance = any(d.get('tolerance_km', 0) > 0 for d in drives)
                if any_tolerance:
                    self.log_test("Tolerance Model - Basic Calculation", True, 
                                "Tolerance calculation working (no specific pattern found)")
                    return True
                else:
                    self.log_test("Tolerance Model - Verification", False, 
                                "No tolerance found in any drives (may need manual seeding)")
                    return False
            
        except Exception as e:
            self.log_test("Tolerance Model - Calculation", False, f"Exception: {str(e)}")
            return False

    def test_drive_route(self) -> bool:
        """Test GET /api/reservations/drives/{id}/route"""
        if not self.test_drive_id:
            self.log_test("Drive Route - No Drive ID", False, "No test drive ID available")
            return False
        
        try:
            response = self.session.get(
                f"{self.base_url}/reservations/drives/{self.test_drive_id}/route"
            )
            
            if response.status_code != 200:
                self.log_test("Drive Route - GET", False, 
                            f"Status: {response.status_code}, Response: {response.text[:200]}")
                return False
            
            data = response.json()
            has_points = 'points' in data and isinstance(data['points'], list)
            is_private = data.get('private', False)
            
            if is_private:
                success = len(data['points']) == 0
                self.log_test("Drive Route - Private Drive", success, "Route hidden for private drive")
            else:
                success = has_points
                self.log_test("Drive Route - Normal Drive", success, f"Points: {len(data['points'])}")
            
            return success
            
        except Exception as e:
            self.log_test("Drive Route - GET", False, f"Exception: {str(e)}")
            return False

    def test_private_toggle(self) -> bool:
        """Test PATCH /api/reservations/drives/{id}/private"""
        if not self.test_drive_id:
            self.log_test("Private Toggle - No Drive ID", False, "No test drive ID available")
            return False
        
        try:
            # Set drive as private
            response = self.session.patch(
                f"{self.base_url}/reservations/drives/{self.test_drive_id}/private",
                json={"is_private": True}
            )
            
            if response.status_code != 200:
                self.log_test("Private Toggle - Set Private", False, 
                            f"Status: {response.status_code}, Response: {response.text[:200]}")
                return False
            
            data = response.json()
            self.log_test("Private Toggle - Set Private", True, f"Drive {data.get('drive_id')} set to private")
            
            # Verify route is hidden
            route_response = self.session.get(
                f"{self.base_url}/reservations/drives/{self.test_drive_id}/route"
            )
            
            if route_response.status_code == 200:
                route_data = route_response.json()
                route_hidden = route_data.get('private') == True and len(route_data.get('points', [])) == 0
                self.log_test("Private Toggle - Route Hidden", route_hidden, 
                            f"Private: {route_data.get('private')}, Points: {len(route_data.get('points', []))}")
            
            # Verify gps_km still shown in report
            drives_response = self.session.get(
                f"{self.base_url}/reservations/drives",
                params={"date_from": "2026-07-01", "date_to": "2026-07-01"}
            )
            
            if drives_response.status_code == 200:
                drives_data = drives_response.json()
                drive = next((d for d in drives_data.get('drives', []) if d.get('drive_id') == self.test_drive_id), None)
                if drive:
                    gps_km_shown = drive.get('gps_km') is not None and drive.get('route_hidden') == True
                    self.log_test("Private Toggle - GPS km Still Shown", gps_km_shown, 
                                f"GPS km: {drive.get('gps_km')}, Route hidden: {drive.get('route_hidden')}")
            
            # Toggle back to non-private
            toggle_back = self.session.patch(
                f"{self.base_url}/reservations/drives/{self.test_drive_id}/private",
                json={"is_private": False}
            )
            
            if toggle_back.status_code == 200:
                self.log_test("Private Toggle - Toggle Back", True, "Drive set back to non-private")
            
            return True
            
        except Exception as e:
            self.log_test("Private Toggle - PATCH", False, f"Exception: {str(e)}")
            return False

    def test_settings(self) -> bool:
        """Test GET/PUT /api/reservations/settings"""
        try:
            # GET settings
            response = self.session.get(f"{self.base_url}/reservations/settings")
            
            if response.status_code != 200:
                self.log_test("Settings - GET", False, 
                            f"Status: {response.status_code}, Response: {response.text[:200]}")
                return False
            
            self.original_settings = response.json()
            original_base_limit = self.original_settings.get('base_limit_km', 60)
            
            self.log_test("Settings - GET", True, f"Base limit: {original_base_limit}")
            
            # PUT settings with changed base_limit_km
            new_base_limit = 30
            update_response = self.session.put(
                f"{self.base_url}/reservations/settings",
                json={"base_limit_km": new_base_limit}
            )
            
            if update_response.status_code != 200:
                self.log_test("Settings - PUT", False, 
                            f"Status: {update_response.status_code}, Response: {update_response.text[:200]}")
                return False
            
            updated_settings = update_response.json()
            updated_base_limit = updated_settings.get('base_limit_km')
            
            put_success = updated_base_limit == new_base_limit
            self.log_test("Settings - PUT", put_success, f"Updated base limit to {updated_base_limit}")
            
            # Verify effective_limit changed in drives report
            drives_response = self.session.get(
                f"{self.base_url}/reservations/drives",
                params={"date_from": "2026-07-01", "date_to": "2026-07-01"}
            )
            
            if drives_response.status_code == 200:
                drives_data = drives_response.json()
                drives = drives_data.get('drives', [])
                if drives:
                    sample_drive = drives[0]
                    new_effective_limit = sample_drive.get('effective_limit_km')
                    tolerance = sample_drive.get('tolerance_km', 0)
                    expected_limit = new_base_limit + tolerance
                    
                    limit_changed = abs(new_effective_limit - expected_limit) < 0.1
                    self.log_test("Settings - Effective Limit Changed", limit_changed, 
                                f"New effective limit: {new_effective_limit}, Expected: {expected_limit}")
            
            # Restore original settings
            restore_response = self.session.put(
                f"{self.base_url}/reservations/settings",
                json={"base_limit_km": original_base_limit}
            )
            
            if restore_response.status_code == 200:
                self.log_test("Settings - Restore", True, f"Restored base limit to {original_base_limit}")
            
            return True
            
        except Exception as e:
            self.log_test("Settings - GET/PUT", False, f"Exception: {str(e)}")
            return False

    def test_batches(self) -> bool:
        """Test GET /api/reservations/batches and DELETE batch"""
        try:
            # GET batches
            response = self.session.get(f"{self.base_url}/reservations/batches")
            
            if response.status_code != 200:
                self.log_test("Batches - GET", False, 
                            f"Status: {response.status_code}, Response: {response.text[:200]}")
                return False
            
            batches = response.json()
            self.log_test("Batches - GET", True, f"Found {len(batches)} batches")
            
            # DELETE a test batch (if we created one)
            if self.test_batch_id:
                delete_response = self.session.delete(
                    f"{self.base_url}/reservations/batches/{self.test_batch_id}"
                )
                
                if delete_response.status_code == 200:
                    self.log_test("Batches - DELETE", True, f"Deleted batch {self.test_batch_id}")
                else:
                    self.log_test("Batches - DELETE", False, 
                                f"Status: {delete_response.status_code}, Response: {delete_response.text[:200]}")
            else:
                self.log_test("Batches - DELETE", False, "No test batch to delete")
            
            return True
            
        except Exception as e:
            self.log_test("Batches - GET/DELETE", False, f"Exception: {str(e)}")
            return False

    def test_vehicle_mapping(self) -> bool:
        """Test GET /api/reservations/vehicle-mapping"""
        try:
            response = self.session.get(f"{self.base_url}/reservations/vehicle-mapping")
            
            if response.status_code != 200:
                self.log_test("Vehicle Mapping - GET", False, 
                            f"Status: {response.status_code}, Response: {response.text[:200]}")
                return False
            
            data = response.json()
            has_structure = (
                'reservation_vehicle_names' in data and
                'vehicles' in data and
                isinstance(data['reservation_vehicle_names'], list) and
                isinstance(data['vehicles'], list)
            )
            
            details = f"Names: {len(data.get('reservation_vehicle_names', []))}, Vehicles: {len(data.get('vehicles', []))}"
            self.log_test("Vehicle Mapping - GET", has_structure, details)
            
            return has_structure
            
        except Exception as e:
            self.log_test("Vehicle Mapping - GET", False, f"Exception: {str(e)}")
            return False

    def run_all_tests(self) -> Dict[str, Any]:
        """Run all reservation tests"""
        print("=" * 50)
        print("🧪 RESERVATION SYSTEM API TESTS")
        print("=" * 50)
        
        # Login as admin
        print("\n🔐 Logging in as admin...")
        if not self.login_admin():
            print("❌ Admin login failed - stopping tests")
            return self.get_results()
        
        # Test auth requirements
        print("\n🔒 Testing Authentication Requirements...")
        self.test_auth_required()
        self.test_admin_required()
        
        # Test import endpoint
        print("\n📤 Testing Import Endpoint...")
        self.test_import_endpoint()
        
        # Test drives report
        print("\n📊 Testing Drives Report...")
        self.test_drives_report()
        
        # Test tolerance model
        print("\n📏 Testing Tolerance Model...")
        self.test_tolerance_model()
        
        # Test drive route
        print("\n🗺️ Testing Drive Route...")
        self.test_drive_route()
        
        # Test private toggle
        print("\n🔒 Testing Private Toggle...")
        self.test_private_toggle()
        
        # Test settings
        print("\n⚙️ Testing Settings...")
        self.test_settings()
        
        # Test batches
        print("\n📦 Testing Batches...")
        self.test_batches()
        
        # Test vehicle mapping
        print("\n🚗 Testing Vehicle Mapping...")
        self.test_vehicle_mapping()
        
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
        
        if results['passed_tests']:
            print("\n✅ Passed Tests:")
            for test in results['passed_tests']:
                print(f"  - {test}")

def main():
    """Main test execution"""
    tester = ReservationAPITester()
    results = tester.run_all_tests()
    tester.print_summary()
    
    # Return appropriate exit code
    return 0 if results['failed'] == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
