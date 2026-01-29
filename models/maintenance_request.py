# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class MaintenanceRequest(models.Model):
    _inherit = 'maintenance.request'

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
        # Find the next stage after the current one that is not done
        in_progress_stage = self.env['maintenance.stage'].search([
            ('done', '=', False),
            ('sequence', '>', self.stage_id.sequence)
        ], order='sequence', limit=1)
        if in_progress_stage:
            self.stage_id = in_progress_stage
            self.message_post(
                body=_('Status updated to "%s" by portal user.') % in_progress_stage.name,
                message_type='comment',
                subtype_xmlid='mail.mt_note'
            )

    def action_portal_set_done(self):
        """Portal action: Set request to Done/Repaired stage"""
        self.ensure_one()
        done_stage = self.env['maintenance.stage'].search([
            ('done', '=', True)
        ], order='sequence', limit=1)
        if done_stage:
            self.stage_id = done_stage
            self.message_post(
                body=_('Status updated to "%s" by portal user.') % done_stage.name,
                message_type='comment',
                subtype_xmlid='mail.mt_note'
            )

    def action_portal_add_notes(self, notes):
        """Portal action: Add notes from portal user"""
        self.ensure_one()
        if notes:
            if self.portal_notes:
                self.portal_notes = f"{self.portal_notes}\n\n---\n\n{notes}"
            else:
                self.portal_notes = notes
            self.message_post(
                body=_('Portal notes updated by portal user.'),
                message_type='comment',
                subtype_xmlid='mail.mt_note'
            )
