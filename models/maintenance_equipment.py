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

    def _get_mail_message_access(self, res_ids, operation='read', model_name=None):
        """Allow portal users to post messages on their assigned equipment."""
        if operation == 'create' and self.env.user.has_group('base.group_portal'):
            return 'read'  # Only require read access to post messages
        return super()._get_mail_message_access(res_ids, operation, model_name=model_name)
