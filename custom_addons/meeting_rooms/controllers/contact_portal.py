# File: controllers/contact_portal.py
from odoo import http
from odoo.http import request

class ResPartnerController(http.Controller):

    # Controller 1: Menampilkan daftar kontak (SEMUA KONTAK)
    @http.route('/res_partner_list', type='http', auth='public', website=True)
    def partner_list(self, search='', **kw):
        # Domain dikosongkan agar menarik SEMUA data (Perusahaan & Individu)
        domain = []
        
        # Logika Pencarian (Search)
        if search:
            domain += ['|', ('name', 'ilike', search), ('street', 'ilike', search)]
            
        partners = request.env['res.partner'].sudo().search(domain)
        
        return request.render('meeting_rooms.partner_list_template', {
            'partners': partners,
            'search': search, 
        })

    # Controller 2: Menampilkan kartu profil kontak berdasarkan ID
    @http.route('/res_partner/<model("res.partner"):partner>', type='http', auth='public', website=True)
    def partner_detail(self, partner, **kw):
        # Gunakan sudo() agar public bisa akses tanpa error hak akses
        partner = partner.sudo()
        
        # (Filter is_company dihapus agar profil individu juga bisa diklik)
            
        return request.render('meeting_rooms.partner_detail_template', {
            'partner': partner
        })