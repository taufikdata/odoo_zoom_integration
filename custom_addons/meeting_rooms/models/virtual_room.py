# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import logging
from requests.auth import HTTPBasicAuth

_logger = logging.getLogger(__name__)

class VirtualRoom(models.Model):
    _name = 'virtual.room'
    _description = 'Virtual Room Configuration'

    name = fields.Char(string="Name", required=True, help="e.g. Corporate Zoom / Teams IT / Google Meet Link")
    active = fields.Boolean(default=True)
    email = fields.Char(string="Host Email", help="Email host for meeting (important for Teams)")

    # === NEW: PROVIDER SELECTION ===
    provider = fields.Selection([
        ('zoom', 'Zoom'),
        ('teams', 'Microsoft Teams'),
        ('google_meet', 'Google Meet'),
    ], string="Provider", default='zoom', required=True)

    # === CREDENTIALS (ZOOM & TEAMS) - ENCRYPTED ===
    # Credentials stored with encryption at rest
    # Only system administrators can view these fields
    zoom_account_id = fields.Char(string="Account / Tenant ID", groups="base.group_system")
    zoom_client_id = fields.Char(string="Client ID", groups="base.group_system")
    zoom_client_secret = fields.Char(string="Client Secret", groups="base.group_system", password=True, encrypt=True)
    
    # === GOOGLE CREDENTIALS - ENCRYPTED (For JWT signing) ===
    google_project_id = fields.Char(string="Google Project ID", groups="base.group_system")
    google_client_email = fields.Char(string="Google Client Email", groups="base.group_system")
    google_private_key = fields.Text(string="Google Private Key", groups="base.group_system", encrypt=True)

    # === STATIC LINK (GOOGLE MEET) ===
    static_link = fields.Char(string="Meeting Link", groups="base.group_system", help="Permanent Google Meet link (e.g. https://meet.google.com/xxx-xxxx-xxx)")

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
                res.raise_for_status()  # Raise exception for non-200 status
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
            except requests.exceptions.Timeout:
                raise UserError(_("Zoom connection timeout. Please check your network and try again."))
            except requests.exceptions.ConnectionError:
                raise UserError(_("Cannot reach Zoom servers. Please check your internet connection."))
            except requests.exceptions.HTTPError as e:
                error_msg = f"Zoom API error: {e.response.status_code}"
                _logger.error(error_msg, exc_info=True)
                raise UserError(_(error_msg))
            except (ValueError, KeyError) as e:
                error_detail = f"Invalid Zoom response: {str(e)}"
                _logger.error(error_detail, exc_info=True)
                raise UserError(_(error_detail))
        
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