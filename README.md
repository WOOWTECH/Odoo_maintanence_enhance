# Odoo Maintenance Portal Enhancement

An Odoo 18 module that extends the maintenance module with a self-service portal for employees to submit and track maintenance requests.

## Features

- **Employee Self-Service Portal**: Submit maintenance requests via web portal
- **Equipment Management**: Track all equipment and their maintenance history
- **Request Tracking**: Real-time status updates on maintenance requests
- **Maintenance Scheduling**: Plan and schedule maintenance activities
- **Multi-language Support**: Traditional Chinese (zh_TW) and English

## Requirements

- Odoo 18.0
- Python 3.10+

## Dependencies

- `base`
- `mail`
- `portal`
- `maintenance`

## Installation

1. Clone this repository to your Odoo addons directory:
   ```bash
   git clone https://github.com/WOOWTECH/Odoo_maintanence_enhance.git
   ```

2. Update the addons path in your Odoo configuration

3. Restart Odoo server

4. Go to Apps menu and install "Maintenance Portal"

## Module Structure

```
maintenance_portal/
├── controllers/
│   └── portal.py              # Portal controllers
├── i18n/
│   ├── maintenance_portal.pot # Translation template
│   └── zh_TW.po               # Traditional Chinese translations
├── models/
│   ├── maintenance_equipment.py
│   └── maintenance_request.py
├── security/
│   ├── ir.model.access.csv
│   └── maintenance_portal_security.xml
├── static/
│   └── src/
│       ├── css/
│       │   └── portal.css     # Portal styling
│       └── img/
│           ├── equipment.svg
│           └── maintenance.svg
├── views/
│   ├── maintenance_equipment_views.xml
│   ├── maintenance_request_views.xml
│   └── portal_templates.xml
├── __init__.py
└── __manifest__.py
```

## Usage

### Backend (Maintenance Team)

1. Navigate to **Maintenance** menu
2. Manage equipment and maintenance requests
3. Assign technicians and schedule repairs
4. Track maintenance history

### Portal (Employees)

1. Access the portal via `/my/maintenance`
2. View equipment assigned to you
3. Submit new maintenance requests
4. Track request status and history

## Screenshots

### Portal Dashboard
Employees can view their equipment and submit maintenance requests through an intuitive interface.

### Request Form
Simple form to describe issues and request maintenance support.

## License

LGPL-3

## Author

WOOWTECH

## Support

For issues and feature requests, please use the [GitHub Issues](https://github.com/WOOWTECH/Odoo_maintanence_enhance/issues) page.
