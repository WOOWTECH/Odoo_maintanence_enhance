# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import AccessError


class MaintenanceRequest(models.Model):
    _inherit = 'maintenance.request'

    # Fields that portal users are allowed to write via RPC
    _PORTAL_WRITABLE_FIELDS = {'portal_notes'}

    portal_user_ids = fields.Many2many(
        'res.users',
        'maintenance_request_portal_user_rel',
        'request_id',
        'user_id',
        string='Portal Users',
        domain=[('share', '=', True)],
        help='External vendors who can view and update this request in portal'
    )
    portal_notes = fields.Text(
        string='Portal Notes',
        help='Notes from portal user about the maintenance work performed'
    )

    def write(self, vals):
        """Restrict portal users to only write allowed fields.

        The check is skipped in sudo mode (self.env.su) to allow internal
        action methods (action_portal_set_in_progress, etc.) to modify
        stage_id via self.sudo().
        """
        if not self.env.su and self.env.user.has_group('base.group_portal'):
            forbidden = set(vals.keys()) - self._PORTAL_WRITABLE_FIELDS
            if forbidden:
                raise AccessError(
                    _('Portal users are not allowed to modify: %s') % ', '.join(sorted(forbidden))
                )
        return super().write(vals)

    @api.onchange('equipment_id')
    def _onchange_equipment_portal_users(self):
        """Inherit portal users from equipment when equipment is selected"""
        if self.equipment_id and self.equipment_id.portal_user_ids:
            self.portal_user_ids = self.equipment_id.portal_user_ids

    def _get_portal_url(self):
        """Get the portal URL for this maintenance request"""
        self.ensure_one()
        return f'/my/maintenance-requests/{self.id}'

    def action_portal_set_in_progress(self):
        """Portal action: Set request to In Progress stage (next stage after current)"""
        self.ensure_one()
        self._check_portal_access()
        # Find the next stage after the current one that is not done
        in_progress_stage = self.env['maintenance.stage'].search([
            ('done', '=', False),
            ('sequence', '>', self.stage_id.sequence)
        ], order='sequence', limit=1)
        if in_progress_stage:
            self.sudo().stage_id = in_progress_stage
            self.sudo().message_post(
                body=_('Status updated to "%s" by portal user.') % in_progress_stage.name,
                message_type='comment',
                subtype_xmlid='mail.mt_note'
            )
        return True

    def action_portal_set_done(self):
        """Portal action: Set request to Done/Repaired stage"""
        self.ensure_one()
        self._check_portal_access()
        done_stage = self.env['maintenance.stage'].search([
            ('done', '=', True)
        ], order='sequence', limit=1)
        if done_stage:
            self.sudo().stage_id = done_stage
            self.sudo().message_post(
                body=_('Status updated to "%s" by portal user.') % done_stage.name,
                message_type='comment',
                subtype_xmlid='mail.mt_note'
            )
        return True

    def action_portal_add_notes(self, notes):
        """Portal action: Add notes from portal user"""
        self.ensure_one()
        self._check_portal_access()
        if notes:
            if self.portal_notes:
                self.portal_notes = f"{self.portal_notes}\n\n---\n\n{notes}"
            else:
                self.portal_notes = notes
            self.sudo().message_post(
                body=_('Portal notes updated by portal user.'),
                message_type='comment',
                subtype_xmlid='mail.mt_note'
            )
        return True

    def _get_mail_message_access(self, res_ids, operation='read', model_name=None):
        """Allow portal users to post messages on their assigned requests."""
        if operation == 'create' and self.env.user.has_group('base.group_portal'):
            return 'read'  # Only require read access to post messages
        return super()._get_mail_message_access(res_ids, operation, model_name=model_name)

    def _check_portal_access(self):
        """Verify the current user has portal access to this request."""
        if self.env.user.has_group('base.group_portal'):
            if self.env.user.id not in self.portal_user_ids.ids:
                raise AccessError(_('You do not have access to this maintenance request.'))
