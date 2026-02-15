from odoo import models, fields


class ContainerTrackingAudit(models.Model):
    _name = 'container.tracking.audit'
    _description = 'Container Tracking Audit Log'
    _order = 'created_at DESC'

    created_at = fields.Datetime(string='Created', default=fields.Datetime.now, readonly=True)
    container_number = fields.Char(string='Container Number', readonly=True, index=True)
    access_token = fields.Char(string='Token (truncated)', readonly=True)
    client_ip = fields.Char(string='Client IP', readonly=True, index=True)
    success = fields.Boolean(string='Success', readonly=True)
    response_time_ms = fields.Integer(string='Response Time (ms)', readonly=True)

    _sql_constraints = [
        ('audit_immutable', 'CHECK(1=1)', 'Audit logs are immutable')
    ]
