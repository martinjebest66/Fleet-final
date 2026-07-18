# Fleet Manager - PRD (Product Requirements Document)

## Original Problem Statement
Fleet management app for a driving school with vehicle/instructor management, driving logbook (kniha jízd), fuel entries via QR, damage reporting, handover protocols, GPS tracking, and analytics.

## Architecture
- **Frontend**: React + Tailwind CSS + Shadcn/UI + Recharts + Leaflet
- **Backend**: FastAPI + Motor (async MongoDB) + reportlab (PDF)
- **Auth**: JWT (bcrypt + PyJWT) + Emergent Google OAuth
- **GPS Protocol**: Teltonika Codec 8/8E TCP server (asyncio, port 5027)
- **OBD-II**: 21 mapped parameters from FMB003
- **Deployment**: Docker (multi-stage) + docker-compose + Nginx reverse proxy

## All Implemented Features
- [x] Vehicle CRUD with QR codes
- [x] Instructor CRUD with PIN management
- [x] Driving logbook (CSV + PDF export)
- [x] Fuel entries (admin + QR mobile forms)
- [x] Damage reports with photo upload + QR
- [x] Handover protocols with fluid checks + 6 photos
- [x] GPS trip import (mock) + trip history on map
- [x] Live GPS map with vehicle positions
- [x] Teltonika FMB003 TCP receiver (real Codec 8/8E)
- [x] GPS device management (IMEI → vehicle)
- [x] OBD-II diagnostics dashboard (RPM, temp, fuel, DTC, etc.)
- [x] Auto-trip detection from GPS positions
- [x] Tracker setup guide (6-step wizard)
- [x] Dashboard with KPIs and charts
- [x] Reports with date ranges
- [x] Fuel consumption analytics (l/100km, costs, trends)
- [x] Admin login (email/password + Google OAuth)
- [x] Instructor PIN login with role-based access
- [x] PDF export for logbook
- [x] Docker deployment files (Dockerfile, docker-compose, nginx, guide)

## Credentials
- Admin: admin@autoskola.cz / Admin123!
- Instructor: inst_aba594d9cd55 / PIN 1234

## Deployment
- Azure VM (Ubuntu 24.04 LTS) recommended
- Ports: 80 (HTTP), 5027 (GPS TCP), 22 (SSH)
- Guide: `/deploy/AZURE_DEPLOY_GUIDE.md`

## Backlog
- [ ] Email notifications for damage reports
- [ ] Multi-language support
- [ ] Vehicle maintenance scheduling
- [ ] Geofencing alerts
- [ ] CSV/GPX import from Ruhavik
- [ ] HTTPS via Let's Encrypt (documented in guide)
- [ ] Split server.py into /backend/routes/ (refactoring)
