# -*- coding: utf-8 -*-

from odoo import models, fields, api, _

from .portal_mail_guard import (
    check_follower_change,
    is_restricted_mail_caller,
    restrict_message_post_kwargs,
)


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

    @api.returns('mail.message', lambda value: value.id)
    def message_post(self, **kwargs):
        """External callers (direct RPC) may only notify current followers and
        only post plain comments, like the portal chatter controller."""
        if is_restricted_mail_caller(self):
            kwargs = restrict_message_post_kwargs(self, kwargs)
        return super().message_post(**kwargs)

    def message_subscribe(self, partner_ids=None, subtype_ids=None):
        check_follower_change(self, partner_ids)
        return super().message_subscribe(partner_ids=partner_ids, subtype_ids=subtype_ids)

    def message_unsubscribe(self, partner_ids=None):
        check_follower_change(self, partner_ids, subscribe=False)
        return super().message_unsubscribe(partner_ids=partner_ids)
