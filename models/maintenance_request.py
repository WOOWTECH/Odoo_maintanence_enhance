# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import AccessError, UserError

from .portal_mail_guard import (
    check_follower_change,
    is_restricted_mail_caller,
    restrict_message_post_kwargs,
)

# Upper bound for one portal notes submission (characters).
PORTAL_NOTES_MAX_LENGTH = 10000


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

    # ------------------------------------------------------------------
    # Portal status workflow
    # ------------------------------------------------------------------

    def _portal_is_first_stage(self):
        """Same rule as the portal template: the request is in (one of) the
        lowest-sequence stage(s), which is where "Start Work" is offered."""
        self.ensure_one()
        stage = self.sudo().stage_id
        if not stage:
            return False
        sequences = self.env['maintenance.stage'].sudo().search([]).mapped('sequence')
        return bool(sequences) and stage.sequence == min(sequences)

    def _check_portal_transition(self, action):
        """Only allow external users the transitions the portal UI offers:

        * ``in_progress``: from the first stage, when it is not a done stage;
        * ``done``: from any stage that is not a done stage.

        A closed (done) request is immutable for them; this also prevents
        repeated ``done`` submissions from re-triggering the recurring
        preventive maintenance copy done by core ``write()``.
        Internal users keep the unrestricted behaviour.
        """
        self.ensure_one()
        if self.env.user._is_internal():
            return
        stage = self.sudo().stage_id
        if stage.done:
            raise UserError(_('This maintenance request is already closed and can no longer be updated from the portal.'))
        if action == 'in_progress' and not self._portal_is_first_stage():
            raise UserError(_('Work can only be started on a maintenance request that is still in its first stage.'))

    def action_portal_set_in_progress(self):
        """Portal action: Set request to In Progress stage (next stage after current)"""
        self.ensure_one()
        self._check_portal_access()
        self._check_portal_transition('in_progress')
        # Find the next stage after the current one that is not done
        in_progress_stage = self.env['maintenance.stage'].sudo().search([
            ('done', '=', False),
            ('sequence', '>', self.sudo().stage_id.sequence)
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
        self._check_portal_transition('done')
        done_stage = self.env['maintenance.stage'].sudo().search([
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
            if not isinstance(notes, str):
                raise UserError(_('Portal notes must be text.'))
            if len(notes) > PORTAL_NOTES_MAX_LENGTH:
                raise UserError(_('Portal notes are limited to %s characters.', PORTAL_NOTES_MAX_LENGTH))
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

    # ------------------------------------------------------------------
    # Mail
    # ------------------------------------------------------------------

    def _get_mail_message_access(self, res_ids, operation='read', model_name=None):
        """Allow portal users to post messages on their assigned requests."""
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

    # ------------------------------------------------------------------
    # Access helpers
    # ------------------------------------------------------------------

    def _check_portal_access(self):
        """Verify the current user may run the portal actions on this request.

        * external (non-internal) users must be assigned to the request and
          the request must not be archived;
        * internal users need write access on the request when the call is
          not made in sudo mode (the actions write through ``sudo()``).
        """
        self.ensure_one()
        user = self.env.user
        if not user._is_internal():
            request_sudo = self.sudo()
            if user.id not in request_sudo.portal_user_ids.ids:
                raise AccessError(_('You do not have access to this maintenance request.'))
            if request_sudo.archive:
                raise AccessError(_('This maintenance request is archived.'))
        elif not self.env.su:
            self.check_access('write')
