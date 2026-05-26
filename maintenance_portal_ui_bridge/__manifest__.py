# -*- coding: utf-8 -*-
{
    'name': 'Maintenance Portal × Portal UI Bridge',
    'version': '18.0.1.0.0',
    'category': 'Hidden',
    'summary': 'Bridges Maintenance Portal with Portal User UI (wt-* design system)',
    'description': """
When both maintenance_portal and woow_portal_ui are installed,
this bridge module auto-installs and replaces the native Odoo
portal table/card layout with the wt-* design system components
(card grid, detail cards, progress bar, badges, etc.).
    """,
    'author': 'WoowTech',
    'website': 'https://www.woowtech.com',
    'license': 'LGPL-3',
    'depends': ['maintenance_portal', 'woow_portal_ui'],
    'auto_install': True,
    'data': [
        'views/portal_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'maintenance_portal_ui_bridge/static/src/css/bridge.css',
        ],
    },
    'installable': True,
    'application': False,
}
