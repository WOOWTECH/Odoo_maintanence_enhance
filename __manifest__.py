# -*- coding: utf-8 -*-
{
    'name': 'Maintenance Portal',
    'version': '18.0.1.0.0',
    'category': 'Maintenance',
    'summary': 'Portal interface for external maintenance vendors',
    'description': """
Maintenance Portal
==================

This module extends the Maintenance module to allow external vendors (Portal Users)
to view assigned equipment and update maintenance request status through the portal.

Features:
---------
* Assign Portal Users to Equipment and Maintenance Requests (Many2many)
* Portal interface for viewing assigned equipment
* Portal interface for viewing and updating maintenance requests
* Status update workflow for portal users
* Bilingual support (English/Traditional Chinese)

Note: This module does NOT depend on the website module.
    """,
    'author': 'WoowTech',
    'website': 'https://www.woowtech.com',
    'depends': ['maintenance', 'portal'],
    'data': [
        'security/maintenance_portal_security.xml',
        'security/ir.model.access.csv',
        'views/maintenance_equipment_views.xml',
        'views/maintenance_request_views.xml',
        'views/portal_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'maintenance_portal/static/src/css/portal.css',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
