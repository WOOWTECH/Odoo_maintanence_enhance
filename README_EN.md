<p align="center">
  <img src="docs/screenshots/icon.svg" alt="Maintenance Portal" width="120"/>
</p>

<h1 align="center">Odoo 18 Maintenance Portal</h1>

<p align="center">
  <strong>Self-service portal for external maintenance vendors on Odoo 18</strong><br/>
  View assigned equipment, track maintenance requests, and update work status through the portal
</p>

<p align="center">
  <a href="#features">Features</a> &bull;
  <a href="#architecture">Architecture</a> &bull;
  <a href="#installation">Installation</a> &bull;
  <a href="#screenshots">Screenshots</a> &bull;
  <a href="#configuration">Configuration</a> &bull;
  <a href="#technical-details">Technical Details</a> &bull;
  <a href="README.md">中文文件</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Odoo-18.0-purple?logo=odoo" alt="Odoo 18"/>
  <img src="https://img.shields.io/badge/Python-3.10+-blue?logo=python" alt="Python 3.10+"/>
  <img src="https://img.shields.io/badge/License-LGPL--3-green" alt="License"/>
  <img src="https://img.shields.io/badge/RWD-Desktop%20%7C%20Tablet%20%7C%20Mobile-orange" alt="Responsive"/>
  <img src="https://img.shields.io/badge/i18n-Traditional%20Chinese%20%7C%20English-blue" alt="Bilingual"/>
</p>

---

## Overview

**Maintenance Portal** is an Odoo 18 module that extends the native Maintenance module with a self-service portal for external vendors (Portal Users). Vendors can view their assigned equipment, track maintenance request progress, and update work status directly from the web portal.

<p align="center">
  <img src="docs/screenshots/portal_home_desktop.png" alt="Portal Home" width="720"/>
</p>

### Why This Module?

| Challenge | Solution |
|-----------|----------|
| External vendors can't see assigned equipment info | Portal interface for viewing equipment list and details |
| Repair progress requires back-and-forth calls/emails | Vendors self-update maintenance status via Portal |
| No mobile-friendly interface | Full RWD design for desktop, tablet, and mobile |
| System only has English UI | Built-in Traditional Chinese translation, bilingual support |
| Portal pages don't match Odoo native theme | Follows Odoo 18 native design language seamlessly |

---

## Features

### Equipment Portal

- **Equipment List** — View all assigned equipment with search (name/serial/category) and sorting
- **Equipment Detail** — Full equipment info: name, serial number, category, assignment date, specs
- **Related Requests** — Equipment detail page shows all related maintenance requests
- **Card Layout** — Equipment displayed as clickable cards, entire card links to detail page

### Maintenance Request Portal

- **Request List** — View all assigned maintenance requests with search, sort, and stage filtering
- **Request Detail** — Full request info: equipment, priority, stage, schedule date, description
- **Status Updates** — Vendors can update status directly (Start Work / Mark Done)
- **Portal Chatter** — Built-in comment/discussion area on request detail page (Odoo mail integration)

### Visual Design

- **Odoo Native Style** — Follows Odoo 18 Portal design language, uses native purple theme (#714B67)
- **Responsive Design (RWD)** — Perfect adaptation for desktop (1280px+), tablet (768px), mobile (375px)
- **Native Card System** — Portal home cards use `portal.portal_docs_entry` native template, matching "Connection & Security" and other native cards exactly
- **64x64 Illustration Icons** — SVG icons use Odoo native illustration style (#C1DBF6 / #FBDBD0 / #374874 palette)
- **Scoped CSS** — All custom CSS scoped to module pages, never pollutes login page or home page native theme

### Security

- **Access Control** — Portal users can only view equipment and requests assigned to them (`portal_user_ids`)
- **Document Access Check** — Every access verified through `_document_check_access`
- **SQL Injection Prevention** — Search input auto-escapes SQL LIKE wildcards
- **CSRF Protection** — All POST requests protected with CSRF tokens
- **Odoo ACL** — Follows Odoo native `ir.model.access` permission control

### Internationalization

- **Traditional Chinese** — Complete `zh_TW.po` translation file
- **English** — Default English interface
- **Translation Template** — `.pot` template provided for extending to other languages

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  Maintenance Portal                      │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │              Portal Frontend                       │  │
│  │                                                    │  │
│  │  /my/home                Portal home cards         │  │
│  │  /my/equipments          Equipment list            │  │
│  │  /my/equipments/<id>     Equipment detail          │  │
│  │  /my/maintenance-requests     Request list         │  │
│  │  /my/maintenance-requests/<id>  Request detail     │  │
│  │                                                    │  │
│  └───────────────────────┬────────────────────────────┘  │
│                          │                               │
│  ┌───────────────────────▼────────────────────────────┐  │
│  │           Controllers (portal.py)                  │  │
│  │                                                    │  │
│  │  MaintenancePortal(CustomerPortal)                 │  │
│  │  ├── _prepare_home_portal_values()  Counters       │  │
│  │  ├── portal_my_equipments()         List           │  │
│  │  ├── portal_equipment_detail()      Detail         │  │
│  │  ├── portal_my_maintenance_requests() List         │  │
│  │  ├── portal_maintenance_request_detail() Detail    │  │
│  │  ├── portal_maintenance_request_update() Update    │  │
│  │  └── _document_check_access()       Auth check     │  │
│  └───────────────────────┬────────────────────────────┘  │
│                          │                               │
│  ┌───────────────────────▼────────────────────────────┐  │
│  │              Models (ORM)                          │  │
│  │                                                    │  │
│  │  maintenance.equipment (inherit)                   │  │
│  │  └── portal_user_ids: Many2many(res.users)        │  │
│  │                                                    │  │
│  │  maintenance.request (inherit)                     │  │
│  │  ├── portal_user_ids: Many2many(res.users)        │  │
│  │  ├── action_portal_set_in_progress()              │  │
│  │  └── action_portal_set_done()                     │  │
│  └───────────────────────┬────────────────────────────┘  │
│                          │                               │
├──────────────────────────┼──────────────────────────────┤
│                          ▼                               │
│  ┌──────────────────────────────────────────────────┐   │
│  │              Odoo 18 Framework                    │   │
│  │  maintenance │ portal │ mail │ base               │   │
│  └──────────────────────────────────────────────────┘   │
│                          │                               │
│  ┌──────────────────────────────────────────────────┐   │
│  │              PostgreSQL                           │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### Module Dependencies

```
maintenance_portal
    ├── maintenance    (Odoo native maintenance module)
    └── portal         (Odoo native portal framework)
         └── mail      (Chatter messaging system)
```

---

## Screenshots

### Portal Home — Equipment & Maintenance Cards

Portal home page displays "Equipment" and "Maintenance Requests" cards using the native `portal.portal_docs_entry` template, matching "Connection & Security" and other native cards exactly.

<p align="center">
  <img src="docs/screenshots/portal_home_desktop.png" alt="Portal Home Desktop" width="720"/>
</p>

### Equipment List

Displays all assigned equipment as cards, with search by name/serial/category and sorting options.

<p align="center">
  <img src="docs/screenshots/equipment_list_desktop.png" alt="Equipment List" width="720"/>
</p>

### Equipment Detail

Full equipment information page including basic data, technical specs, and related maintenance requests.

<p align="center">
  <img src="docs/screenshots/equipment_detail_desktop.png" alt="Equipment Detail" width="720"/>
</p>

### Maintenance Request List

Lists all assigned maintenance requests with stage filtering, search, and sorting.

<p align="center">
  <img src="docs/screenshots/request_list_desktop.png" alt="Request List" width="720"/>
</p>

### Maintenance Request Detail

Complete request information page with equipment info, priority, schedule date, description, and status update action buttons.

<p align="center">
  <img src="docs/screenshots/request_detail_desktop.png" alt="Request Detail" width="720"/>
</p>

### Responsive Design — Mobile

All pages fully adapt to mobile screens with automatic layout adjustments for cards and tables.

<p align="center">
  <img src="docs/screenshots/portal_home_mobile.png" alt="Mobile Home" width="280"/>
  &nbsp;&nbsp;
  <img src="docs/screenshots/equipment_list_mobile.png" alt="Mobile Equipment List" width="280"/>
  &nbsp;&nbsp;
  <img src="docs/screenshots/request_detail_mobile.png" alt="Mobile Request Detail" width="280"/>
</p>

---

## Installation

### Prerequisites

- **Odoo 18.0** (Community or Enterprise)
- **Python 3.10+**
- **PostgreSQL 13+**

### Option 1: Direct Installation

```bash
# 1. Clone this repository
git clone https://github.com/WOOWTECH/Odoo_maintanence_enhance.git

# 2. Copy module to addons path
cp -r Odoo_maintanence_enhance/maintenance_portal /path/to/odoo/addons/

# 3. Update module list and install
odoo -u maintenance_portal -d your_database --stop-after-init
```

### Option 2: Docker / Podman Deployment

```bash
# 1. Copy module to addons bind mount directory
cp -r maintenance_portal /path/to/docker/addons/

# 2. Upgrade module in container
docker exec <container> odoo -u maintenance_portal -d <database> --stop-after-init

# 3. Restart container
docker restart <container>
```

### Install in Odoo

1. Go to **Apps** menu
2. Click **Update Apps List**
3. Search for "Maintenance Portal"
4. Click Install

---

## Configuration

### 1. Assign Equipment to External Vendors

1. Navigate to **Maintenance > Equipment**
2. Open an equipment record
3. Add the vendor's Portal account to the **Portal Users** field

### 2. Assign Maintenance Requests to Vendors

1. Navigate to **Maintenance > Maintenance Requests**
2. Open a request record
3. Add the vendor to the **Portal Users** field

### 3. Vendor Portal Workflow

1. Vendor logs in via `/web/login` with their Portal account
2. Sees "Equipment" and "Maintenance Requests" cards on the "My Account" home page
3. Clicks through to equipment list or request list
4. Views details and updates maintenance status

---

## Technical Details

### Directory Structure

```
maintenance_portal/
├── controllers/
│   ├── __init__.py
│   └── portal.py                   # Portal controllers (6 routes)
├── docs/
│   ├── plans/
│   │   └── 2026-03-23-woowtech-brand-portal-redesign.md
│   └── screenshots/                # Feature screenshots
├── i18n/
│   ├── maintenance_portal.pot      # Translation template
│   └── zh_TW.po                    # Traditional Chinese translation
├── models/
│   ├── __init__.py
│   ├── maintenance_equipment.py    # Equipment model extension
│   └── maintenance_request.py      # Maintenance request model extension
├── security/
│   ├── ir.model.access.csv         # ACL access control
│   └── maintenance_portal_security.xml  # Security rules
├── static/
│   └── src/
│       ├── css/
│       │   └── portal.css          # Module-scoped CSS (purple theme + RWD)
│       └── img/
│           ├── equipment.svg       # Equipment icon (64x64 illustration)
│           └── maintenance.svg     # Maintenance icon (64x64 illustration)
├── tests/
│   ├── test_portal_v1.py           # V1 unit tests (103 tests)
│   ├── test_portal_v2.py           # V2 integration tests (56 tests)
│   └── test_portal_v3.py           # V3 visual/RWD tests (80 tests)
├── views/
│   ├── maintenance_equipment_views.xml  # Backend equipment view extension
│   ├── maintenance_request_views.xml    # Backend request view extension
│   └── portal_templates.xml        # Portal frontend templates (QWeb)
├── __init__.py
├── __manifest__.py
├── README.md                       # Chinese README
└── README_EN.md                    # English README
```

### Portal Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/my/equipments` | GET | Equipment list (search/sort/pagination) |
| `/my/equipments/<id>` | GET | Equipment detail |
| `/my/maintenance-requests` | GET | Request list (search/sort/filter/pagination) |
| `/my/maintenance-requests/<id>` | GET | Request detail |
| `/my/maintenance-requests/<id>/update` | POST | Update maintenance status |

### CSS Design Principles

- **No Native Theme Override** — Login page and Portal home maintain Odoo native purple, unaffected by module
- **Scoped Selectors** — All CSS selectors scoped to `.maintenance-detail-card`, `.maintenance-equipment-card`, and other module-specific classes
- **CSS Custom Properties** — Uses `--wt-primary: #714B67` variables for unified brand color management
- **Responsive Breakpoints** — Mobile optimization at `max-width: 767px` and `max-width: 575px`

### Test Coverage

| Test Suite | Tests | Pass | Fail | Coverage |
|------------|-------|------|------|----------|
| V1 Unit Tests | 103 | 103 | 0 | Models, controllers, permissions |
| V2 Integration Tests | 56 | 56 | 0 (1 expected) | Portal flows, search/sort/filter |
| V3 Visual Tests | 80 | 80 | 0 (9 warnings) | RWD, CSS scoping, native compat |
| **Total** | **239** | **239** | **0** | |

---

## Changelog

### v18.0.1.0.0 (2026-04)

- **Initial Release** — Complete maintenance portal module
- **Equipment Management** — Portal equipment list, detail page, search and sort
- **Maintenance Requests** — Portal request list, detail page, status update workflow
- **Odoo Native Style** — Uses `portal.portal_docs_entry` template, 64x64 illustration icons
- **Scoped CSS** — Purple theme follows Odoo native, CSS never pollutes native pages
- **RWD** — Full responsive design (desktop/tablet/mobile)
- **Traditional Chinese** — Complete `zh_TW` translation
- **Testing** — V1/V2/V3 three-phase testing, 239 tests all passing

---

## License

This project is licensed under **LGPL-3**.

---

## Support

- **Company:** [WoowTech](https://www.woowtech.com)
- **Issues:** [GitHub Issues](https://github.com/WOOWTECH/Odoo_maintanence_enhance/issues)

---

<p align="center">
  <sub>Built with care by <a href="https://github.com/WOOWTECH">WOOWTECH</a> &bull; Powered by Odoo 18</sub>
</p>
