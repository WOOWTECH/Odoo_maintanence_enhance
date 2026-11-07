# -*- coding: utf-8 -*-
"""Mail helpers shared by maintenance.equipment and maintenance.request.

Portal vendors may post on the chatter of the equipment / requests they are
assigned to (see ``_get_mail_message_access`` on both models).  The portal
chatter goes through ``/mail/message/post`` which, for non-internal users,
restricts the notified partners to the followers of the document and forces
a plain comment (``ThreadController._prepare_post_data``).  ``message_post``
itself is a public method and can also be called directly through
``/web/dataset/call_kw``; that path does not apply the controller filtering,
so the helpers below re-apply the same rules at the model level.
"""

import logging

from odoo.exceptions import AccessError

_logger = logging.getLogger(__name__)


def is_restricted_mail_caller(records):
    """True when the caller is an external (non-internal) user acting
    without superuser privileges.  Controllers and module actions that
    already filtered their input call ``message_post`` in sudo mode and are
    therefore not affected."""
    env = records.env
    return not env.su and not env.user._is_internal()


def restrict_message_post_kwargs(record, kwargs):
    """Return a copy of ``message_post`` kwargs safe for an external caller.

    * only the parameters the portal chatter itself may send are kept
      (``_get_allowed_message_post_params``);
    * ``partner_ids`` is limited to the current followers of ``record``
      (same rule as core ``_filter_message_post_partners``);
    * the message is forced to a plain comment (``mail.mt_comment``).
    """
    record.ensure_one()
    allowed = record._get_allowed_message_post_params()
    dropped = sorted(set(kwargs) - allowed)
    if dropped:
        _logger.info(
            "maintenance_portal: dropped message_post parameters %s for external user %s on %s",
            dropped, record.env.user.id, record,
        )
    clean = {key: value for key, value in kwargs.items() if key in allowed}

    partner_ids = clean.get('partner_ids') or []
    if partner_ids:
        # sudo: mail.followers - filtering requested partners on the
        # document followers, like core _filter_message_post_partners
        followers = record.env['mail.followers'].sudo().search([
            ('res_model', '=', record._name),
            ('res_id', '=', record.id),
            ('partner_id', 'in', list(partner_ids)),
        ])
        clean['partner_ids'] = followers.partner_id.ids
    clean['message_type'] = 'comment'
    clean['subtype_xmlid'] = 'mail.mt_comment'
    return clean


def check_follower_change(records, partner_ids, subscribe=True):
    """External users may only (un)subscribe themselves.

    Core ``message_subscribe`` / ``message_unsubscribe`` let anyone with
    write access manage the followers of a document.  Portal vendors have a
    (field-restricted) write access on their maintenance requests, which
    would let them add arbitrary partners as followers and then notify them,
    defeating the follower restriction above, or remove the internal
    followers of a request.

    When subscribing, partners that already follow every record are
    tolerated (core ``message_post`` re-subscribes the notified partners when
    ``mail_post_autofollow`` is set, and those are followers by then).
    """
    if not partner_ids or not records or not is_restricted_mail_caller(records):
        return
    others = set(partner_ids) - {records.env.user.partner_id.id}
    if others and subscribe:
        # sudo: mail.followers - reading the current followers of the records
        followers = records.env['mail.followers'].sudo().search([
            ('res_model', '=', records._name),
            ('res_id', 'in', records.ids),
            ('partner_id', 'in', list(others)),
        ])
        followed = {}
        for follower in followers:
            followed.setdefault(follower.partner_id.id, set()).add(follower.res_id)
        record_ids = set(records.ids)
        others = {pid for pid in others if not followed.get(pid, set()) >= record_ids}
    if others:
        raise AccessError(records.env._('Portal users can only follow or unfollow documents for themselves.'))
