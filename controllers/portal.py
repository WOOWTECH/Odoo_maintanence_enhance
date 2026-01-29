# -*- coding: utf-8 -*-

from collections import OrderedDict
from operator import itemgetter

from odoo import http, _
from odoo.http import request
from odoo.osv.expression import AND
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.exceptions import AccessError, MissingError


class MaintenancePortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        """Add equipment and maintenance request counts to portal home"""
        values = super()._prepare_home_portal_values(counters)

        if 'equipment_count' in counters:
            equipment_count = request.env['maintenance.equipment'].search_count(
                self._get_equipment_domain()
            ) if request.env['maintenance.equipment'].check_access_rights('read', raise_exception=False) else 0
            values['equipment_count'] = equipment_count

        if 'maintenance_request_count' in counters:
            request_count = request.env['maintenance.request'].search_count(
                self._get_maintenance_request_domain()
            ) if request.env['maintenance.request'].check_access_rights('read', raise_exception=False) else 0
            values['maintenance_request_count'] = request_count

        return values

    def _get_equipment_domain(self):
        """Domain for portal user's assigned equipment"""
        return [('portal_user_ids', 'in', request.env.user.id)]

    def _get_maintenance_request_domain(self):
        """Domain for portal user's assigned maintenance requests"""
        return [('portal_user_ids', 'in', request.env.user.id)]

    # ==================== Equipment Routes ====================

    @http.route([
        '/my/equipments',
        '/my/equipments/page/<int:page>'
    ], type='http', auth='user', website=False)
    def portal_my_equipments(self, page=1, sortby=None, search=None, search_in='name', **kw):
        """List equipment assigned to portal user"""
        Equipment = request.env['maintenance.equipment']

        domain = self._get_equipment_domain()

        # Searchable fields
        searchbar_inputs = {
            'name': {'input': 'name', 'label': _('Name')},
            'serial_no': {'input': 'serial_no', 'label': _('Serial Number')},
            'category': {'input': 'category', 'label': _('Category')},
        }

        # Sortable fields
        searchbar_sortings = {
            'name': {'label': _('Name'), 'order': 'name asc'},
            'category': {'label': _('Category'), 'order': 'category_id asc'},
            'serial_no': {'label': _('Serial Number'), 'order': 'serial_no asc'},
        }

        if not sortby:
            sortby = 'name'
        order = searchbar_sortings[sortby]['order']

        # Search
        if search and search_in:
            search_domain = []
            if search_in == 'name':
                search_domain = [('name', 'ilike', search)]
            elif search_in == 'serial_no':
                search_domain = [('serial_no', 'ilike', search)]
            elif search_in == 'category':
                search_domain = [('category_id.name', 'ilike', search)]
            domain = AND([domain, search_domain])

        # Count and pager
        equipment_count = Equipment.search_count(domain)
        pager = portal_pager(
            url='/my/equipments',
            url_args={'sortby': sortby, 'search': search, 'search_in': search_in},
            total=equipment_count,
            page=page,
            step=self._items_per_page
        )

        # Fetch records
        equipments = Equipment.search(
            domain,
            order=order,
            limit=self._items_per_page,
            offset=pager['offset']
        )

        values = self._prepare_portal_layout_values()
        # Get frontend languages for language selector
        frontend_languages = request.env['res.lang']._get_frontend()
        values.update({
            'equipments': equipments,
            'page_name': 'equipments',
            'pager': pager,
            'default_url': '/my/equipments',
            'searchbar_sortings': searchbar_sortings,
            'sortby': sortby,
            'searchbar_inputs': searchbar_inputs,
            'search_in': search_in,
            'search': search,
            'frontend_languages': frontend_languages,
        })

        return request.render('maintenance_portal.portal_my_equipments', values)

    @http.route(['/my/equipments/<int:equipment_id>'], type='http', auth='user', website=False)
    def portal_equipment_detail(self, equipment_id, **kw):
        """Equipment detail page"""
        try:
            equipment = self._document_check_access('maintenance.equipment', equipment_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        # Get related maintenance requests for this equipment
        requests = request.env['maintenance.request'].search([
            ('equipment_id', '=', equipment_id),
            ('portal_user_ids', 'in', request.env.user.id)
        ], order='create_date desc', limit=10)

        values = self._prepare_portal_layout_values()
        frontend_languages = request.env['res.lang']._get_frontend()
        values.update({
            'equipment': equipment,
            'maintenance_requests': requests,
            'page_name': 'equipment_detail',
            'frontend_languages': frontend_languages,
        })

        return request.render('maintenance_portal.portal_equipment_detail', values)

    # ==================== Maintenance Request Routes ====================

    @http.route([
        '/my/maintenance-requests',
        '/my/maintenance-requests/page/<int:page>'
    ], type='http', auth='user', website=False)
    def portal_my_maintenance_requests(self, page=1, sortby=None, filterby=None, search=None, search_in='name', **kw):
        """List maintenance requests assigned to portal user"""
        MaintenanceRequest = request.env['maintenance.request']

        domain = self._get_maintenance_request_domain()

        # Searchable fields
        searchbar_inputs = {
            'name': {'input': 'name', 'label': _('Request')},
            'equipment': {'input': 'equipment', 'label': _('Equipment')},
        }

        # Sortable fields
        searchbar_sortings = {
            'date': {'label': _('Newest'), 'order': 'create_date desc'},
            'name': {'label': _('Name'), 'order': 'name asc'},
            'stage': {'label': _('Stage'), 'order': 'stage_id asc'},
        }

        # Filter options
        stages = request.env['maintenance.stage'].search([])
        searchbar_filters = {
            'all': {'label': _('All'), 'domain': []},
        }
        for stage in stages:
            searchbar_filters[str(stage.id)] = {
                'label': stage.name,
                'domain': [('stage_id', '=', stage.id)]
            }

        if not sortby:
            sortby = 'date'
        order = searchbar_sortings[sortby]['order']

        if not filterby:
            filterby = 'all'
        domain = AND([domain, searchbar_filters.get(filterby, searchbar_filters['all'])['domain']])

        # Search
        if search and search_in:
            search_domain = []
            if search_in == 'name':
                search_domain = [('name', 'ilike', search)]
            elif search_in == 'equipment':
                search_domain = [('equipment_id.name', 'ilike', search)]
            domain = AND([domain, search_domain])

        # Count and pager
        request_count = MaintenanceRequest.search_count(domain)
        pager = portal_pager(
            url='/my/maintenance-requests',
            url_args={'sortby': sortby, 'filterby': filterby, 'search': search, 'search_in': search_in},
            total=request_count,
            page=page,
            step=self._items_per_page
        )

        # Fetch records
        requests = MaintenanceRequest.search(
            domain,
            order=order,
            limit=self._items_per_page,
            offset=pager['offset']
        )

        values = self._prepare_portal_layout_values()
        frontend_languages = request.env['res.lang']._get_frontend()
        values.update({
            'requests': requests,
            'page_name': 'maintenance_requests',
            'pager': pager,
            'default_url': '/my/maintenance-requests',
            'searchbar_sortings': searchbar_sortings,
            'sortby': sortby,
            'searchbar_filters': OrderedDict(sorted(searchbar_filters.items(), key=lambda x: x[0])),
            'filterby': filterby,
            'searchbar_inputs': searchbar_inputs,
            'search_in': search_in,
            'search': search,
            'frontend_languages': frontend_languages,
        })

        return request.render('maintenance_portal.portal_my_maintenance_requests', values)

    @http.route(['/my/maintenance-requests/<int:request_id>'], type='http', auth='user', website=False)
    def portal_maintenance_request_detail(self, request_id, **kw):
        """Maintenance request detail page"""
        try:
            maintenance_request = self._document_check_access('maintenance.request', request_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        # Get all stages for status display
        stages = request.env['maintenance.stage'].search([], order='sequence')

        values = self._prepare_portal_layout_values()
        frontend_languages = request.env['res.lang']._get_frontend()
        values.update({
            'mrequest': maintenance_request,
            'stages': stages,
            'page_name': 'maintenance_request_detail',
            'frontend_languages': frontend_languages,
        })

        return request.render('maintenance_portal.portal_maintenance_request_detail', values)

    @http.route(['/my/maintenance-requests/<int:request_id>/update'], type='http', auth='user', methods=['POST'], website=False, csrf=True)
    def portal_maintenance_request_update(self, request_id, **kw):
        """Update maintenance request status and notes"""
        try:
            maintenance_request = self._document_check_access('maintenance.request', request_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        action = kw.get('action')
        notes = kw.get('notes', '').strip()

        # Handle status update actions
        if action == 'in_progress':
            maintenance_request.action_portal_set_in_progress()
        elif action == 'done':
            maintenance_request.action_portal_set_done()

        # Handle notes update
        if notes:
            maintenance_request.action_portal_add_notes(notes)

        return request.redirect(f'/my/maintenance-requests/{request_id}')

    def _document_check_access(self, model_name, document_id, access_token=None):
        """Check if portal user has access to the document"""
        document = request.env[model_name].browse([document_id])
        document_sudo = document.sudo().exists()

        if not document_sudo:
            raise MissingError(_("This document does not exist."))

        # Check if user is in portal_user_ids
        if request.env.user.id not in document_sudo.portal_user_ids.ids:
            raise AccessError(_("You do not have access to this document."))

        return document_sudo
