# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
from requests.auth import HTTPBasicAuth

class VirtualRoom(models.Model):
    _name = 'virtual.room'
    _description = 'Virtual Room Configuration'

    name = fields.Char(string="Name", required=True, help="e.g. Corporate Zoom / Teams IT / Google Meet Link")
    active = fields.Boolean(default=True)
    email = fields.Char(string="Host Email", help="Email host meeting (penting untuk Teams)")

    # === NEW: PROVIDER SELECTION ===
    provider = fields.Selection([
        ('zoom', 'Zoom (API)'),
        ('teams', 'Microsoft Teams (API)'),
        ('google_meet', 'Google Meet (Static Link)'),
    ], string="Provider", default='zoom', required=True)

    # === FIELD KHUSUS GOOGLE MEET / STATIC ===
    static_link = fields.Char(string="Static Link", help="Paste link Google Meet atau link permanen disini")

    # === CREDENTIALS (ZOOM & TEAMS) ===
    # Kita pakai field lama 'zoom_...' untuk menyimpan credential Teams juga (Field Mapping)
    zoom_account_id = fields.Char(string="Account / Tenant ID")
    zoom_client_id = fields.Char(string="Client ID")
    zoom_client_secret = fields.Char(string="Client Secret")

    # REVISI: Tombol Test API
    def action_test_connection(self):
        self.ensure_one()
        if self.provider == 'zoom':
            # Coba ambil Access Token Zoom sebagai tes
            if not self.zoom_account_id or not self.zoom_client_id:
                raise UserError("Credential belum lengkap.")
                
            url = f"https://zoom.us/oauth/token?grant_type=account_credentials&account_id={self.zoom_account_id}"
            try:
                res = requests.post(url, auth=HTTPBasicAuth(self.zoom_client_id, self.zoom_client_secret), timeout=10)
                if res.status_code == 200:
                    token = res.json().get('access_token')
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': 'Connection Successful',
                            'message': 'Zoom API Connected! Token retrieved.',
                            'sticky': False,
                            'type': 'success',
                        }
                    }
                else:
                    raise UserError(f"Zoom Error: {res.text}")
            except Exception as e:
                raise UserError(f"Connection Failed: {str(e)}")
        
        elif self.provider == 'teams':
             # Logic tes teams belum diimplementasi detail, kita kasih warning saja
             raise UserError("Test Connection for Teams belum diimplementasi sepenuhnya.")
        
        elif self.provider == 'google_meet':
             # Google Meet statis tidak butuh tes API
             return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Info',
                    'message': 'Google Meet menggunakan Static Link. Tidak ada API untuk dites.',
                    'type': 'info',
                }
            }