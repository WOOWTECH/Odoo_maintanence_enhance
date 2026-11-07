# -*- coding: utf-8 -*-
"""Model-level regression tests for the portal vendor workflow.

* review:maintenance-portal-stage-transition-not-enforced-server-side
* review:maintenance-portal-mail-post-access-downgraded-to-read
"""

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged

from .common import MaintenancePortalCommon


@tagged('post_install', '-at_install', 'maintenance_portal')
class TestPortalStageTransitions(MaintenancePortalCommon, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_maintenance_portal()

    def _as_vendor_controller(self, record):
        """The portal controller works on a sudo record of the vendor env."""
        return record.with_user(self.vendor).sudo()

    def _count_requests(self, name):
        return self.env['maintenance.request'].with_context(active_test=False).search_count([('name', '=', name)])

    # --- closed requests are immutable for portal vendors -------------------

    def test_vendor_cannot_reclose_scrapped_request(self):
        req = self._create_request(self.stage_scrap, name='MP scrapped')
        close_date = req.close_date
        for record in (self._as_vendor_controller(req), req.with_user(self.vendor)):
            with self.assertRaises(UserError):
                record.action_portal_set_done()
            with self.assertRaises(UserError):
                record.action_portal_set_in_progress()
        self.assertEqual(req.stage_id, self.stage_scrap)
        self.assertEqual(req.close_date, close_date)

    def test_vendor_repeated_done_does_not_copy_recurring_request(self):
        req = self._create_request(self.stage_progress, name='MP recurring', **self._recurring_vals())
        vendor_req = self._as_vendor_controller(req)
        vendor_req.action_portal_set_done()
        self.assertEqual(req.stage_id, self.stage_repaired)
        after_first = self._count_requests('MP recurring')
        self.assertEqual(after_first, 2, "closing a recurring preventive request schedules exactly one next request")
        req.close_date = '2020-01-01'
        for _attempt in range(3):
            with self.assertRaises(UserError):
                vendor_req.action_portal_set_done()
        self.assertEqual(self._count_requests('MP recurring'), after_first)
        self.assertEqual(str(req.close_date), '2020-01-01')

    def test_vendor_start_work_only_from_first_stage(self):
        req = self._create_request(self.stage_progress, name='MP in progress')
        with self.assertRaises(UserError):
            self._as_vendor_controller(req).action_portal_set_in_progress()
        self.assertEqual(req.stage_id, self.stage_progress)

    def test_vendor_happy_path(self):
        req = self._create_request(self.stage_new, name='MP happy')
        vendor_req = self._as_vendor_controller(req)
        vendor_req.action_portal_set_in_progress()
        self.assertEqual(req.stage_id, self.stage_progress)
        vendor_req.action_portal_set_done()
        self.assertEqual(req.stage_id, self.stage_repaired)
        self.assertTrue(req.close_date)
        notes = req.message_ids.filtered(lambda m: 'by portal user' in (m.body or ''))
        self.assertEqual(len(notes), 2)

    def test_vendor_can_close_request_without_stage(self):
        req = self._create_request(self.stage_new, name='MP no stage')
        req.stage_id = False
        self._as_vendor_controller(req).action_portal_set_done()
        self.assertEqual(req.stage_id, self.stage_repaired)

    def test_unassigned_vendor_refused(self):
        req = self._create_request(self.stage_new, name='MP other vendor')
        with self.assertRaises(AccessError):
            req.with_user(self.vendor_other).sudo().action_portal_set_done()
        self.assertEqual(req.stage_id, self.stage_new)

    def test_archived_request_refused(self):
        req = self._create_request(self.stage_new, name='MP archived')
        req.archive = True
        with self.assertRaises(AccessError):
            self._as_vendor_controller(req).action_portal_set_done()
        self.assertEqual(req.stage_id, self.stage_new)

    def test_internal_manager_unchanged(self):
        req = self._create_request(self.stage_scrap, name='MP internal')
        req.with_user(self.manager).action_portal_set_done()
        self.assertEqual(req.stage_id, self.stage_repaired)
        req.stage_id = self.stage_repaired
        # admin / sudo callers keep the previous behaviour as well
        req.action_portal_set_done()
        self.assertEqual(req.stage_id, self.stage_repaired)

    def test_portal_notes_length_limited(self):
        req = self._create_request(self.stage_new, name='MP notes')
        vendor_req = req.with_user(self.vendor)
        vendor_req.action_portal_add_notes('checked the pump')
        self.assertEqual(req.portal_notes, 'checked the pump')
        with self.assertRaises(UserError):
            vendor_req.action_portal_add_notes('x' * 10001)
        self.assertEqual(req.portal_notes, 'checked the pump')


@tagged('post_install', '-at_install', 'maintenance_portal')
class TestPortalMessagePost(MaintenancePortalCommon, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_maintenance_portal()
        cls.request_rec = cls._create_request(cls.stage_new, name='MP chatter')
        cls.equipment.message_subscribe(partner_ids=cls.manager.partner_id.ids)

    def _notified_partners(self, message):
        return self.env['mail.notification'].sudo().search([
            ('mail_message_id', '=', message.id),
        ]).res_partner_id

    def _assert_rpc_post_filtered(self, record):
        message = record.with_user(self.vendor).message_post(
            body='hello',
            partner_ids=[self.victim.id, self.manager.partner_id.id],
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )
        message = message.sudo()
        self.assertNotIn(self.victim, message.partner_ids)
        self.assertIn(self.manager.partner_id, message.partner_ids, "followers can still be mentioned")
        self.assertEqual(message.message_type, 'comment')
        self.assertEqual(message.subtype_id, self.env.ref('mail.mt_comment'))
        self.assertEqual(message.author_id, self.vendor.partner_id)
        self.assertNotIn(self.victim, self._notified_partners(message))
        self.assertFalse(self.env['mail.mail'].sudo().search([
            ('mail_message_id', '=', message.id),
            ('recipient_ids', 'in', self.victim.ids),
        ]))

    def test_rpc_message_post_equipment_filters_partners(self):
        self._assert_rpc_post_filtered(self.equipment)

    def test_rpc_message_post_request_filters_partners(self):
        self._assert_rpc_post_filtered(self.request_rec)

    def test_rpc_message_post_drops_unexpected_parameters(self):
        for kwargs in (
            {'subtype_id': self.env.ref('mail.mt_note').id},
            {'message_type': 'notification', 'subtype_xmlid': 'mail.mt_note'},
            {'email_layout_xmlid': 'mail.mail_notification_light', 'subtype_xmlid': 'mail.mt_note'},
        ):
            message = self.request_rec.with_user(self.vendor).message_post(body='hello', **kwargs).sudo()
            self.assertEqual(message.subtype_id, self.env.ref('mail.mt_comment'), kwargs)
            self.assertEqual(message.message_type, 'comment', kwargs)

    def test_sudo_and_internal_posts_untouched(self):
        # module actions / controllers post in sudo mode
        msg = self.equipment.with_user(self.vendor).sudo().message_post(
            body='note', partner_ids=[self.victim.id],
            message_type='comment', subtype_xmlid='mail.mt_note',
        )
        self.assertIn(self.victim, msg.partner_ids)
        self.assertEqual(msg.subtype_id, self.env.ref('mail.mt_note'))
        # internal users keep the standard behaviour
        msg = self.request_rec.with_user(self.manager).message_post(
            body='internal', partner_ids=[self.victim.id],
            message_type='comment', subtype_xmlid='mail.mt_note',
        )
        self.assertIn(self.victim, msg.sudo().partner_ids)

    def test_rpc_message_post_autofollow_keeps_working(self):
        # core re-subscribes the (already filtered) partners with autofollow
        message = self.request_rec.with_user(self.vendor).with_context(mail_post_autofollow=True).message_post(
            body='autofollow', partner_ids=[self.manager.partner_id.id, self.victim.id],
            message_type='comment', subtype_xmlid='mail.mt_comment',
        ).sudo()
        self.assertEqual(message.partner_ids, self.manager.partner_id)
        self.assertNotIn(self.victim, self.request_rec.message_partner_ids)

    def test_vendor_cannot_add_or_remove_other_followers(self):
        vendor_req = self.request_rec.with_user(self.vendor)
        with self.assertRaises(AccessError):
            vendor_req.message_subscribe(partner_ids=[self.victim.id])
        self.assertNotIn(self.victim, self.request_rec.message_partner_ids)
        with self.assertRaises(AccessError):
            vendor_req.message_unsubscribe(partner_ids=self.manager.partner_id.ids)
        self.assertIn(self.manager.partner_id, self.request_rec.message_partner_ids)
        # following / unfollowing oneself still works
        vendor_req.message_subscribe(partner_ids=self.vendor.partner_id.ids)
        self.assertIn(self.vendor.partner_id, self.request_rec.message_partner_ids)
        vendor_req.message_unsubscribe(partner_ids=self.vendor.partner_id.ids)
        self.assertNotIn(self.vendor.partner_id, self.request_rec.message_partner_ids)
