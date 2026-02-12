# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import uuid
import pytz
from werkzeug.urls import url_join

# Timezone helper
_tzs = [(tz, tz) for tz in sorted(pytz.all_timezones, key=lambda tz: tz if not tz.startswith('Etc/') else '_')]
def _tz_get(self):
    return _tzs

class ResUsers(models.Model):
    _inherit = 'res.users'

    # Back-reference to booking links
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

    name = fields.Char(string="Link Title", required=True, default="My Booking Link")
    
    user_id = fields.Many2one(
        'res.users', 
        string="Host User", 
        required=True, 
        default=lambda self: self.env.user,
        ondelete='restrict',  # Prevent host user deletion if booking link exists
    )
    
    token = fields.Char("Token", required=True, copy=False, readonly=True, index=True, default=lambda self: self._generate_token())
    active = fields.Boolean(default=True)
    booking_url = fields.Char("Full URL", compute="_compute_url")
    
    # FEATURE: Timezone selection for booking portal (public/non-odoo users)
    tz = fields.Selection(_tz_get, string='Timezone for Guests', 
                          default=lambda self: self.env.user.tz or 'UTC',
                          help="Timezone displayed in booking portal for external guests")

    # Helper fields for display and permissions
    is_current_user = fields.Boolean(compute='_compute_permissions')
    is_admin = fields.Boolean(compute='_compute_permissions')

    # === DATABASE GUARANTEE: PREVENT DUPLICATE TOKENS ===
    _sql_constraints = [
        ('token_unique', 'UNIQUE(token)', 'Booking Link token must be unique! System detected duplicate token.')
    ]

    @api.depends('user_id')
    def _compute_permissions(self):
        # REVISED: Check Meeting Manager Group, NOT System Administrator
        # Previously: has_group('base.group_system') -> Wrong target
        is_admin_user = self.env.user.has_group('meeting_rooms.group_meeting_manager')
        
        for rec in self:
            rec.is_current_user = (rec.user_id == self.env.user)
            rec.is_admin = is_admin_user

    def _generate_token(self):
        """
        Generate unique token and verify against database to prevent duplicate tokens.
        """
        while True:
            # Generate random 12-digit token
            new_token = uuid.uuid4().hex[:12]
            
            # Check database if this token already exists
            existing_link = self.env['meeting.booking.link'].sudo().search([('token', '=', new_token)], limit=1)
            
            # If not in use (safe), return this token
            if not existing_link:
                return new_token

    @api.depends('token')
    def _compute_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for rec in self:
            if rec.token:
                rec.booking_url = url_join(base_url, f"/book/{rec.token}")
            else:
                rec.booking_url = False

    def action_regenerate_token(self):
        # Ensure regenerate token uses duplicate-safe function
        for rec in self:
            rec.token = self._generate_token()

    # @api.model
    # def action_open_my_links(self):
    #     """
    #     Open list of booking links owned by current user.
    #     User can view, create, edit, and delete their own booking links.
    #     """
    #     return {
    #         'type': 'ir.actions.act_window',
    #         'name': 'My Booking Links',
    #         'res_model': 'meeting.booking.link',
    #         'view_mode': 'kanban,tree,form',
    #         'domain': [('user_id', '=', self.env.user.id)],
    #         'context': {'default_user_id': self.env.user.id},
    #         'target': 'current',
    #     }

    # def init(self):
    #     """
    #     This function is automatically called when module is upgraded.
    #     Purpose: force update has_booking_link field in ResUsers model.
    #     """
    #     all_links = self.search([])
    #     users_with_links = all_links.mapped('user_id')
        
    #     if users_with_links:
    #         users_with_links.write({'has_booking_link': True})

    # ========================================================
    # DATABASE INITIALIZATION
    # ========================================================
    def init(self):
        # Call parent class init method as best practice
        super(MeetingBookingLink, self).init()
        
        """
        Purpose: Drop old database constraints that blocked multiple links per user.
        """
        try:
            self.env.cr.execute("""
                ALTER TABLE meeting_booking_link 
                DROP CONSTRAINT IF EXISTS meeting_booking_link_user_id_uniq;
            """)
        except Exception:
            pass