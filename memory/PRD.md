# Fleet Manager - PRD (Product Requirements Document)

## Original Problem Statement
Create a fleet management app for a small driving school with vehicle management, instructor management, driving logbook (kniha jízd), fuel entries via QR code, damage reporting via QR code, handover protocols, GPS tracker data import, and map visualization.

## User Choices
- **Language**: Czech (kniha jízd)
- **Authentication**: Admin (email/password + Google OAuth), Instructor (PIN kód)
- **Maps**: OpenStreetMap (Leaflet)
- **GPS Hardware**: Teltonika FMB003 (Codec 8 / 8 Extended over TCP)

## Architecture
- **Frontend**: React + Tailwind CSS + Shadcn/UI
- **Backend**: FastAPI + Motor (async MongoDB)
- **Database**: MongoDB
- **Auth**: JWT (bcrypt + PyJWT) + Emergent Google OAuth
- **Maps**: Leaflet with OpenStreetMap tiles
- **PDF**: reportlab
- **GPS Protocol**: Teltonika Codec 8/8E TCP (asyncio server on port 5027)

## Core Requirements - All Done
- [x] Vehicle CRUD with instructor assignment
- [x] Instructor CRUD with PIN management
- [x] Driving logbook with CSV + PDF export
- [x] Fuel entry management with QR code mobile forms
- [x] Damage reporting with photo upload and QR code access
- [x] Handover protocols with fluid checks and photos
- [x] GPS trip import (mock) with map visualization
- [x] Live GPS map with real-time vehicle positions
- [x] Teltonika FMB003 TCP receiver
- [x] GPS device management (IMEI → vehicle)
- [x] Dashboard with KPIs and charts
- [x] Reports with custom date ranges
- [x] Admin login (email/password + Google OAuth)
- [x] Instructor PIN login with role-based access
- [x] Fuel consumption analytics (l/100km, costs, trends)

## Authentication System
- **Admin**: Email/password login + Google OAuth (Emergent Auth)
- **Instructor**: PIN code login (4-6 digits, set by admin)
- **JWT**: access_token (12h) + refresh_token (7d) in httponly cookies
- **Role-based access**: Admin = full access, Instructor = read-only limited navigation
- **Admin credentials**: admin@autoskola.cz / Admin123!

## P2 Features (Backlog)
- [ ] Email notifications for damage reports
- [ ] Multi-language support
- [ ] Vehicle maintenance scheduling
- [ ] Sample data for demo
- [ ] Geofencing alerts
