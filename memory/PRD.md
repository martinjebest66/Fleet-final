# Fleet Manager - PRD (Product Requirements Document)

## Original Problem Statement
Create a fleet management app for a small driving school with vehicle management, instructor management, driving logbook (kniha jízd), fuel entries via QR code, damage reporting via QR code, handover protocols, GPS tracker data import, and map visualization.

## User Choices
- **Language**: Czech (kniha jízd)
- **Authentication**: Emergent-managed Google OAuth
- **Maps**: OpenStreetMap (Leaflet)
- **GPS Hardware**: Teltonika FMB003 (Codec 8 / 8 Extended over TCP)

## Architecture
- **Frontend**: React + Tailwind CSS + Shadcn/UI
- **Backend**: FastAPI + Motor (async MongoDB)
- **Database**: MongoDB
- **Maps**: Leaflet with OpenStreetMap tiles
- **Icons**: Phosphor Icons
- **Charts**: Recharts
- **QR Codes**: qrcode.react
- **PDF**: reportlab
- **GPS Protocol**: Teltonika Codec 8/8E TCP (asyncio server on port 5027)

## Core Requirements (Static)
- [x] Vehicle CRUD with instructor assignment
- [x] Instructor CRUD
- [x] Driving logbook with filtering, CSV export, PDF export
- [x] Fuel entry management with QR code mobile forms
- [x] Damage reporting with photo upload and QR code access
- [x] Handover protocols for vehicle condition documentation
- [x] GPS trip import (mock) with map visualization
- [x] Dashboard with KPIs and charts
- [x] Reports with custom date ranges
- [x] PDF export for logbook (Kniha jízd)
- [x] Live GPS map with real-time vehicle positions
- [x] Teltonika FMB003 TCP receiver (real protocol implementation)
- [x] GPS device management (IMEI → vehicle registration)

## What's Been Implemented

### Authentication
- Google OAuth via Emergent Auth

### Vehicle Management
- Full CRUD, QR code generation for fuel/damage/handover

### Instructor Management
- Full CRUD with vehicle assignment

### Logbook (Kniha jízd)
- Manual entry, GPS sync, CSV export, **PDF export** (Czech landscape A4 format)

### Fuel Entries
- Admin form + public QR code mobile form

### Damage Reports
- Admin form + public QR code mobile form with photo upload

### Handover Protocols
- Vehicle condition with fluid checks, 6-step photo capture

### GPS Tracking
- Mock data import, trip list, map visualization
- **Live map** with simulated real-time vehicle positions
- **Teltonika FMB003 TCP receiver** (Codec 8/8 Extended parser)
- **GPS device management** (IMEI → vehicle_id registration)
- **TCP server status** monitoring
- **Test endpoint** for simulating device connection without hardware

### Reports
- Kilometer statistics with charts, vehicle breakdown

### Dashboard
- KPIs, charts, vehicle status, recent trips

## Component Refactoring (2026-05-16)
- [x] PublicHandoverForm.jsx → 4 sub-components
- [x] Vehicles.jsx → 3 sub-components
- [x] Backend server.py → 13 helper functions extracted

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
- [x] Teltonika FMB003 TCP receiver

## P2 Features (Nice to have - Backlog)
- [ ] Email notifications for damage reports
- [ ] Multi-language support
- [ ] Instructor login (separate from admin)
- [ ] Fuel consumption analytics
- [ ] Vehicle maintenance scheduling
- [ ] Sample data for demo

## Technical Notes
- TCP server runs on port 5027 (needs to be exposed in production firewall)
- Teltonika device config: Server IP = your_public_ip, Port = 5027, Protocol = TCP, Codec = Codec 8 Extended
- GPS positions stored in `vehicle_positions` MongoDB collection
- Device IMEI mappings stored in `gps_devices` MongoDB collection
