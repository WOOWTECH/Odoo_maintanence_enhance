# -*- coding: utf-8 -*-
"""HTTP regression tests for the portal vendor pages.

Run as an authenticated portal vendor:

* POST /my/maintenance-requests/<id>/update cannot change a closed request,
  and repeated "done" submissions do not copy recurring requests
  (review:maintenance-portal-stage-transition-not-enforced-server-side);
* /web/dataset/call_kw message_post cannot notify non-followers, while the
  portal chatter (/mail/message/post) keeps working
  (review:maintenance-portal-mail-post-access-downgraded-to-read);
* detail pages honour archive / multi-company rules (hardening).
"""

import re

from odoo.tests import HttpCase, tagged

from .common import MaintenancePortalCommon


@tagged('post_install', '-at_install', 'maintenance_portal')
class TestPortalHttp(MaintenancePortalCommon, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_maintenance_portal()
        cls.equipment.message_subscribe(partner_ids=cls.manager.partner_id.ids)

    def setUp(self):
        super().setUp()
        self.authenticate('mp_vendor', 'mp_vendor')

    def _detail_url(self, req):
        return f'/my/maintenance-requests/{req.id}'

    def _csrf_from(self, req):
        response = self.url_open(self._detail_url(req))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.url.endswith(self._detail_url(req)), response.url)
        match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
        self.assertTrue(match, "the detail page renders the update form")
        return match.group(1)

    def _post_action(self, req, action, csrf_token):
        response = self.url_open(
            f'{self._detail_url(req)}/update',
            data={'csrf_token': csrf_token, 'action': action},
            allow_redirects=False,
        )
        self.assertIn(response.status_code, (302, 303))
        return response

    def _count_requests(self, name):
        return self.env['maintenance.request'].with_context(active_test=False).search_count([('name', '=', name)])

    # --- stage transitions -------------------------------------------------

    def test_post_cannot_change_closed_request(self):
        req = self._create_request(self.stage_scrap, name='MP http scrapped', **self._recurring_vals())
        close_date = req.close_date
        csrf = self._csrf_from(req)
        for action in ('done', 'in_progress', 'done'):
            response = self._post_action(req, action, csrf)
            self.assertTrue(response.headers['Location'].endswith(self._detail_url(req)))
        req.invalidate_recordset()
        self.assertEqual(req.stage_id, self.stage_scrap)
        self.assertEqual(req.close_date, close_date)
        self.assertEqual(self._count_requests('MP http scrapped'), 1)

    def test_repeated_done_post_copies_recurring_request_once(self):
        req = self._create_request(self.stage_progress, name='MP http recurring', **self._recurring_vals())
        csrf = self._csrf_from(req)
        self._post_action(req, 'done', csrf)
        req.invalidate_recordset()
        self.assertEqual(req.stage_id, self.stage_repaired)
        self.assertEqual(self._count_requests('MP http recurring'), 2)
        for _attempt in range(2):
            self._post_action(req, 'done', csrf)
        self.assertEqual(self._count_requests('MP http recurring'), 2)

    def test_ui_flow_start_then_done(self):
        req = self._create_request(self.stage_new, name='MP http flow')
        csrf = self._csrf_from(req)
        self._post_action(req, 'in_progress', csrf)
        req.invalidate_recordset()
        self.assertEqual(req.stage_id, self.stage_progress)
        self._post_action(req, 'done', csrf)
        req.invalidate_recordset()
        self.assertEqual(req.stage_id, self.stage_repaired)
        page = self.url_open(self._detail_url(req))
        self.assertEqual(page.status_code, 200)
        self.assertNotIn('value="done"', page.text)
        self.assertNotIn('value="in_progress"', page.text)

    # --- chatter / message_post --------------------------------------------

    def _call_kw_message_post(self, record):
        return self.make_jsonrpc_request(
            f'/web/dataset/call_kw/{record._name}/message_post',
            {
                'model': record._name,
                'method': 'message_post',
                'args': [[record.id]],
                'kwargs': {
                    'body': 'rpc post',
                    'partner_ids': [self.victim.id],
                    'message_type': 'comment',
                    'subtype_xmlid': 'mail.mt_comment',
                },
            },
        )

    def test_rpc_message_post_does_not_notify_non_followers(self):
        req = self._create_request(self.stage_new, name='MP http rpc chatter')
        for record in (self.equipment, req):
            message_id = self._call_kw_message_post(record)
            message = self.env['mail.message'].browse(message_id)
            self.assertEqual(message.model, record._name)
            self.assertEqual(message.author_id, self.vendor.partner_id)
            self.assertNotIn(self.victim, message.partner_ids)
            self.assertFalse(self.env['mail.notification'].search([
                ('mail_message_id', '=', message.id),
                ('res_partner_id', '=', self.victim.id),
            ]))

    def test_portal_chatter_post_still_works(self):
        req = self._create_request(self.stage_new, name='MP http portal chatter')
        for record in (self.equipment, req):
            self.make_jsonrpc_request('/mail/message/post', {
                'thread_model': record._name,
                'thread_id': record.id,
                'post_data': {
                    'body': 'portal chatter %s' % record._name,
                    'message_type': 'comment',
                    'partner_ids': [self.manager.partner_id.id, self.victim.id],
                },
            })
            message = self.env['mail.message'].search([
                ('model', '=', record._name), ('res_id', '=', record.id),
                ('author_id', '=', self.vendor.partner_id.id),
            ], order='id desc', limit=1)
            self.assertTrue(message, "portal chatter post on %s" % record._name)
            self.assertIn('portal chatter', str(message.body))
            self.assertIn(self.manager.partner_id, message.partner_ids)
            self.assertNotIn(self.victim, message.partner_ids)

    # --- detail page access (hardening) -------------------------------------

    def test_archived_request_hidden(self):
        req = self._create_request(self.stage_new, name='MP http archived')
        req.archive = True
        response = self.url_open(self._detail_url(req), allow_redirects=False)
        self.assertIn(response.status_code, (302, 303))
        self.assertTrue(response.headers['Location'].endswith('/my'))
        listing = self.url_open('/my/maintenance-requests')
        self.assertEqual(listing.status_code, 200)
        self.assertNotIn('MP http archived', listing.text)

    def test_archived_equipment_hidden(self):
        self.equipment.active = False
        response = self.url_open(f'/my/equipments/{self.equipment.id}', allow_redirects=False)
        self.assertIn(response.status_code, (302, 303))
        self.assertTrue(response.headers['Location'].endswith('/my'))

    def test_other_company_request_hidden(self):
        other_company = self.env['res.company'].create({'name': 'MP Other Company'})
        self.env.user.company_ids |= other_company
        team = self.env['maintenance.team'].create({'name': 'MP Other Team', 'company_id': other_company.id})
        req = self._create_request(self.stage_new, name='MP http other company', equipment_id=False,
                                   maintenance_team_id=team.id, company_id=other_company.id)
        response = self.url_open(self._detail_url(req), allow_redirects=False)
        self.assertIn(response.status_code, (302, 303))
        self.assertTrue(response.headers['Location'].endswith('/my'))
        # and it is not updatable either
        own = self._create_request(self.stage_new, name='MP http own')
        csrf = self._csrf_from(own)
        self._post_action(req, 'done', csrf)
        req.invalidate_recordset()
        self.assertEqual(req.stage_id, self.stage_new)

    def test_equipment_link_only_when_assigned(self):
        assigned = self._create_request(self.stage_new, name='MP http assigned eq')
        page = self.url_open(self._detail_url(assigned))
        self.assertIn(f'href="/my/equipments/{self.equipment.id}"', page.text)
        unassigned = self._create_request(self.stage_new, name='MP http unassigned eq',
                                          equipment_id=self.equipment_unassigned.id)
        page = self.url_open(self._detail_url(unassigned))
        self.assertEqual(page.status_code, 200)
        self.assertIn(self.equipment_unassigned.name, page.text)
        self.assertNotIn(f'href="/my/equipments/{self.equipment_unassigned.id}"', page.text)
