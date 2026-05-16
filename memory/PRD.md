# Fleet Manager - PRD (Product Requirements Document)

## Original Problem Statement
Create a fleet management app for a small driving school with vehicle management, instructor management, driving logbook (kniha jízd), fuel entries via QR code, damage reporting via QR code, handover protocols, GPS tracker data import, and map visualization.

## User Choices
- **Language**: Czech (kniha jízd)
- **Authentication**: Emergent-managed Google OAuth
- **Maps**: OpenStreetMap (Leaflet)
- **GPS Data**: Mock import + simulated real-time (Teltonika FMB003 architecture ready)

## Architecture
- **Frontend**: React + Tailwind CSS + Shadcn/UI
- **Backend**: FastAPI + Motor (async MongoDB)
- **Database**: MongoDB
- **Maps**: Leaflet with OpenStreetMap tiles
- **Icons**: Phosphor Icons
- **Charts**: Recharts
- **QR Codes**: qrcode.react
- **PDF**: reportlab

## User Personas
1. **Admin/Owner**: Full access to all features, vehicle/instructor management, reports
2. **Instructor**: Limited access, can use QR codes for fuel/damage reporting
3. **Public User**: Can submit fuel entries and damage reports via QR code links

## Core Requirements (Static)
- [x] Vehicle CRUD with instructor assignment
- [x] Instructor CRUD
- [x] Driving logbook with filtering and CSV export
- [x] Fuel entry management with QR code mobile forms
- [x] Damage reporting with photo upload and QR code access
- [x] Handover protocols for vehicle condition documentation
- [x] GPS trip import (mock) with map visualization
- [x] Dashboard with KPIs and charts
- [x] Reports with custom date ranges
- [x] PDF export for logbook (Kniha jízd)
- [x] Live GPS map with real-time vehicle positions

## What's Been Implemented
1. **Authentication**: Google OAuth via Emergent Auth
2. **Vehicle Management**: Full CRUD, QR code generation for fuel/damage/handover
3. **Instructor Management**: Full CRUD with vehicle assignment
4. **Logbook (Kniha jízd)**: Manual entry, GPS sync, CSV export, **PDF export**
5. **Fuel Entries**: Admin form + public QR code mobile form
6. **Damage Reports**: Admin form + public QR code mobile form with photo upload
7. **Handover Protocols**: Vehicle condition with fluid checks, 6-step photo capture
8. **GPS Tracking**: Mock data import, trip list, map visualization, **live map with simulated positions**
9. **Reports**: Kilometer statistics with charts, vehicle breakdown
10. **Dashboard**: KPIs, charts, vehicle status, recent trips

## Code Quality Fixes (2026-04-04)
- [x] React Hook dependencies properly configured
- [x] Array index keys replaced with unique string keys
- [x] Inline chart objects extracted to module-level constants
- [x] Backend random module replaced with secrets

## Component Refactoring (2026-05-16)
- [x] PublicHandoverForm.jsx split: 557 → ~170 lines + 4 sub-components
- [x] Vehicles.jsx split: 492 → ~140 lines + 3 sub-components
- [x] Backend server.py: 13 helper functions extracted

## New Features (2026-05-16)
- [x] PDF export knihy jízd (reportlab, Czech format, landscape A4)
- [x] Live GPS mapa s pozicemi vozidel (simulace + auto-refresh)
- [x] GPS historie tras (tab view)
- [x] Simulace pohybu vozidel (POST /api/gps/simulate-live)
- [x] Historie pozic vozidla (GET /api/gps/vehicle-history/{id})

## P0 Features (Critical - Done)
- [x] Authentication
- [x] Vehicle/Instructor CRUD
- [x] Logbook entries
- [x] Dashboard

## P1 Features (Important - Done)
- [x] QR code fuel/damage forms
- [x] GPS mock import
- [x] Map visualization
- [x] Reports with date ranges
- [x] PDF export for logbook
- [x] Live GPS tracking map

## P2 Features (Nice to have - Backlog)
- [ ] Real Teltonika FMB003 integration (TCP/MQTT receiver)
- [ ] Email notifications for damage reports
- [ ] Multi-language support
- [ ] Instructor login (separate from admin)
- [ ] Fuel consumption analytics
- [ ] Vehicle maintenance scheduling
- [ ] Sample data for demo
