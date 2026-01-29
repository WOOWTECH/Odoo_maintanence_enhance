# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class MaintenanceEquipment(models.Model):
    _inherit = 'maintenance.equipment'

    portal_user_ids = fields.Many2many(
        'res.users',
        'maintenance_equipment_portal_user_rel',
        'equipment_id',
        'user_id',
        string='Portal Users',
        domain=[('share', '=', True)],
        help='External vendors who can view this equipment in portal'
    )

    def _get_portal_url(self):
        """Get the portal URL for this equipment"""
        self.ensure_one()
        return f'/my/equipments/{self.id}'
