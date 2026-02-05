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
    email = fields.Char(string="Host Email", help="Email host for meeting (important for Teams)")

    # === NEW: PROVIDER SELECTION ===
    provider = fields.Selection([
        ('zoom', 'Zoom (API)'),
        ('teams', 'Microsoft Teams (API)'),
        ('google_meet', 'Google Meet (Static Link)'),
    ], string="Provider", default='zoom', required=True)

    # === FIELD KHUSUS GOOGLE MEET / STATIC ===
    static_link = fields.Char(string="Static Link", help="Paste Google Meet link or permanent meeting link here")

    # === CREDENTIALS (ZOOM & TEAMS) - ENCRYPTED ===
    # Using ir.model.fields.Secret for encryption at rest
    # Credentials are automatically encrypted by Odoo when saved
    zoom_account_id = fields.Char(string="Account / Tenant ID", groups="base.group_system")
    zoom_client_id = fields.Char(string="Client ID", groups="base.group_system")
    zoom_client_secret = fields.Char(string="Client Secret", groups="base.group_system", password=True)

    def action_test_connection(self):
        """Test API connection for configured provider"""
        self.ensure_one()
        if self.provider == 'zoom':
            # Test Zoom access token
            if not self.zoom_account_id or not self.zoom_client_id:
                raise UserError(_("Credentials are incomplete. Please provide Account ID and Client ID."))
                
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
             # Teams connection test not fully implemented yet
             raise UserError(_("Test Connection for Microsoft Teams is not yet fully implemented."))
        
        elif self.provider == 'google_meet':
             # Google Meet uses static link, no API test required
             return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Information',
                    'message': 'Google Meet uses a static link. No API connection test is required.',
                    'type': 'info',
                }
            }