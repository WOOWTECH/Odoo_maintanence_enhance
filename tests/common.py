# -*- coding: utf-8 -*-

from odoo.tests import new_test_user


class MaintenancePortalCommon:
    """Shared fixtures: one assigned portal vendor, one internal maintenance
    manager following the documents, and an unrelated partner (the would-be
    victim of notification abuse)."""

    @classmethod
    def _setup_maintenance_portal(cls):
        env = cls.env
        cls.stage_new = env.ref('maintenance.stage_0')
        cls.stage_progress = env.ref('maintenance.stage_1')
        cls.stage_repaired = env.ref('maintenance.stage_3')
        cls.stage_scrap = env.ref('maintenance.stage_4')

        cls.vendor = new_test_user(
            env, login='mp_vendor', groups='base.group_portal',
            name='MP Vendor', email='mp_vendor@example.com',
        )
        cls.vendor_other = new_test_user(
            env, login='mp_vendor_other', groups='base.group_portal',
            name='MP Other Vendor', email='mp_vendor_other@example.com',
        )
        cls.manager = new_test_user(
            env, login='mp_manager',
            groups='base.group_user,maintenance.group_equipment_manager',
            name='MP Manager', email='mp_manager@example.com',
        )
        cls.victim = env['res.partner'].create({
            'name': 'MP Unrelated Partner',
            'email': 'mp_victim@example.com',
        })

        cls.equipment = env['maintenance.equipment'].create({
            'name': 'MP Chiller',
            'portal_user_ids': [(6, 0, cls.vendor.ids)],
        })
        cls.equipment_unassigned = env['maintenance.equipment'].create({
            'name': 'MP Boiler (not assigned to vendor)',
        })

    @classmethod
    def _create_request(cls, stage, **vals):
        values = {
            'name': 'MP Request',
            'equipment_id': cls.equipment.id,
            'stage_id': stage.id,
            'portal_user_ids': [(6, 0, cls.vendor.ids)],
        }
        values.update(vals)
        req = cls.env['maintenance.request'].create(values)
        # internal follower so follower-filtering keeps someone legitimate
        req.message_subscribe(partner_ids=cls.manager.partner_id.ids)
        return req

    @classmethod
    def _recurring_vals(cls):
        return {
            'maintenance_type': 'preventive',
            'recurring_maintenance': True,
            'repeat_interval': 1,
            'repeat_unit': 'month',
            'repeat_type': 'forever',
        }
