from odoo import models, fields

class ContainerTrackingStatus(models.Model):
    _name = 'container.tracking.status'
    _description = 'Master Data EDI Status Container'
    _rec_name = 'code'

    code = fields.Char(string='Kode Status (EDI)', required=True)
    name = fields.Char(string='Keterangan / Terjemahan', required=True)

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'Kode Status EDI sudah ada! Tidak boleh duplikat.')
    ]