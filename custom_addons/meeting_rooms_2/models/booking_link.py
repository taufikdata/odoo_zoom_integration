# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import uuid
from werkzeug.urls import url_join

class ResUsers(models.Model):
    _inherit = 'res.users'

    # Relasi balik ke booking link
    booking_link_ids = fields.One2many('meeting.booking.link', 'user_id', string="Booking Links")
    
    # Boolean field to indicate if user already has a booking link
    has_booking_link = fields.Boolean(compute='_compute_has_booking_link', store=True)

    @api.depends('booking_link_ids')
    def _compute_has_booking_link(self):
        """Check if user has any booking links using relation, not database query."""
        for user in self:
            # OPTIMIZED: Use One2many relation instead of search_count (much faster!)
            user.has_booking_link = bool(user.booking_link_ids)

class MeetingBookingLink(models.Model):
    _name = 'meeting.booking.link'
    _description = 'Booking Link Configuration'
    _rec_name = 'name'

    _sql_constraints = [
        ('user_id_uniq', 'unique(user_id)', 'This user already has a Booking Link! Cannot create duplicate.')
    ]

    name = fields.Char(string="Link Title", required=True, default="My Booking Link")
    
    user_id = fields.Many2one(
        'res.users', 
        string="Host User", 
        required=True, 
        # default=lambda self: self.env.user,
    )
    
    token = fields.Char("Token", required=True, copy=False, readonly=True, index=True, default=lambda self: self._generate_token())
    active = fields.Boolean(default=True)
    booking_url = fields.Char("Full URL", compute="_compute_url")

    # Helper fields for display and permissions
    is_current_user = fields.Boolean(compute='_compute_permissions')
    is_admin = fields.Boolean(compute='_compute_permissions')

    @api.depends('user_id')
    def _compute_permissions(self):
        # REVISED: Check Meeting Manager Group, NOT System Administrator
        # Previously: has_group('base.group_system') -> Wrong target
        is_admin_user = self.env.user.has_group('meeting_rooms_2.group_meeting_manager')
        
        for rec in self:
            rec.is_current_user = (rec.user_id == self.env.user)
            rec.is_admin = is_admin_user

    def _generate_token(self):
        return uuid.uuid4().hex[:12]

    @api.depends('token')
    def _compute_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for rec in self:
            if rec.token:
                rec.booking_url = url_join(base_url, f"/book/{rec.token}")
            else:
                rec.booking_url = False

    def action_regenerate_token(self):
        for rec in self:
            rec.token = uuid.uuid4().hex[:12]

    @api.model
    def action_open_my_link(self):
        my_link = self.search([('user_id', '=', self.env.user.id)], limit=1)
        if not my_link:
            my_link = self.create({
                'name': f"{self.env.user.name}'s Booking Link",
                'user_id': self.env.user.id
            })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Edit My Booking Link',
            'res_model': 'meeting.booking.link',
            'res_id': my_link.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def init(self):
        """
        This function is automatically called when module is upgraded.
        Purpose: force update has_booking_link field in ResUsers model.
        """
        all_links = self.search([])
        users_with_links = all_links.mapped('user_id')
        
        if users_with_links:
            users_with_links.write({'has_booking_link': True})