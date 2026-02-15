from odoo import models, fields, api

class WhatsappHistory(models.Model):
    _name = 'whatsapp.history'
    _description = 'Log Percakapan WhatsApp'
    _order = 'create_date desc'

    # === CORE FIELDS (matches existing DB schema) ===
    sender_number = fields.Char(string='Nomor Pengirim', required=True, index=True)
    sender_name = fields.Char(string='Nama Pengirim')
    message = fields.Text(string='Isi Pesan')
    direction = fields.Selection([
        ('in', 'Masuk (Customer)'),
        ('out', 'Keluar (Sales)')
    ], string='Arah', default='in')
    raw_data = fields.Text(string='Raw Data (JSON)')
    
    # === EXTENDED FIELDS (untuk future) ===
    # partner_id = fields.Many2one('res.partner', string='Contact/Partner', ondelete='set null')  # TODO: Add column after MVP
    # provider = fields.Selection([...], string='Provider')  # TODO: Add column after MVP
    # message_id = fields.Char(string='Message ID')  # TODO: Add column after MVP
    
    # === AUTOMATIC MATCHING (Simplified MVP version) ===
    @api.model_create_multi
    def create(self, vals_list):
        # Logger untuk debugging
        for vals in vals_list:
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"[WhatsApp Create] Creating record: {vals}")
        
        return super().create(vals_list)