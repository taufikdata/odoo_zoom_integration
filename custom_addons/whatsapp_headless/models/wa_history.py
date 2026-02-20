from odoo import models, fields, api

class WhatsappHistory(models.Model):
    _name = 'whatsapp.history'
    _description = 'Log Percakapan WhatsApp'
    _order = 'create_date desc'

    # === CORE FIELDS ===
    contact_number = fields.Char(string='Nomor Kontak', required=True, index=True)
    contact_name = fields.Char(string='Nama Kontak')
    message = fields.Text(string='Isi Pesan', required=True)
    from_me = fields.Boolean(string='Dari Saya?', default=False, index=True)
    raw_data = fields.Text(string='Raw Data (JSON)')
    
    # === ADDITIONAL FIELDS ===
    device_number = fields.Char(string='Nomor Device/Gateway', index=True)
    is_group = fields.Boolean(string='Pesan Group?', default=False)
    
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