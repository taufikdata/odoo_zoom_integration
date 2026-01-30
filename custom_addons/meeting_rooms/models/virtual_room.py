# -*- coding: utf-8 -*-
from odoo import models, fields

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