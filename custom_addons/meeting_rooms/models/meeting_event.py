# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import datetime, timedelta
import pytz
import base64
import logging
import requests
import re
from requests.auth import HTTPBasicAuth
import urllib.parse
import json
import time

_logger = logging.getLogger(__name__)

# Helper for timezone
_tzs = [(tz, tz) for tz in sorted(pytz.all_timezones, key=lambda tz: tz if not tz.startswith('Etc/') else '_')]
def _tz_get(self):
    return _tzs

class MeetingEvent(models.Model):
    _name = 'meeting.event'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Meeting Event (Master)'
    _rec_name = 'subject'

    # ==========================================================
    # FIELDS DEFINITION
    # ==========================================================
    @api.model
    def create(self, vals):
        """
        Create a new meeting event with validation and auto-add creator as attendee.
        
        Args:
            vals: Dictionary of field values for the new record
            
        Returns:
            New meeting.event record
            
        Raises:
            ValidationError: If end_date <= start_date
        """
        # POINT 6: Validate date range before creation
        if vals.get('start_date') and vals.get('end_date'):
            start_date = fields.Datetime.to_datetime(vals['start_date'])
            end_date = fields.Datetime.to_datetime(vals['end_date'])
            if end_date <= start_date:
                raise ValidationError(_("End date must be after start date."))
        
        res = super(MeetingEvent, self).create(vals)
        if res.create_uid.id not in res.attendee.ids:
            # Add creator as attendee WITHOUT context to avoid timezone conversion
            res.write({
                'attendee': [(4, res.create_uid.id)] 
            })
        return res

    # =========================
    # =========================
    # MAIN FIELDS
    # =========================
    subject = fields.Char("Subject", required=True, tracking=True)
    room_location_ids = fields.Many2many('room.location', string="Locations")
    virtual_room_id = fields.Many2one('virtual.room', string="Virtual Room Provider")

    start_date = fields.Datetime("Start", required=True)
    end_date = fields.Datetime("End", required=True)
    attendee = fields.Many2many("res.users", string="Attendee")
    description = fields.Text("Description")
    calendar_alarm = fields.Many2one("calendar.alarm", string="Reminder")

    # === NEW FIELD: TO USER EKSTERNAL ===
    guest_partner_id = fields.Many2one(
        'res.partner', 
        string="External Guest", 
        help="Guest data from booking portal"
    )
    host_user_id = fields.Many2one(
        'res.users',
        string="Host User",
        default=lambda self: self.env.user,
        help="Primary host for timezone and ownership context"
    )
    guest_emails = fields.Char(
        string="Guest Emails",
        help="Additional guest emails (comma-separated) from booking portal"
    )
    guest_tz = fields.Char(
        string="Guest Timezone",
        help="Timezone selected by guest when booking through booking link",
        default='UTC'
    )
    # ========================================

    zoom_id = fields.Char(string="Meeting ID", readonly=True, copy=False) 
    zoom_link = fields.Char(string="Join URL", readonly=True, copy=False)
    zoom_invitation = fields.Text(string="Invitation Text", copy=False)
    zoom_start_url = fields.Char(string='Start URL', readonly=True, copy=False)
    ai_summary = fields.Html(string='AI Summary Result', sanitize=False, copy=False)

    recurrency = fields.Boolean('Recurrent', help="Recurrent Meeting")
    rrule_type = fields.Selection([
        ('daily', 'Daily'),
        ('weekly', 'Weekly')
    ], string='Recurrence', help="Let the event automatically repeat at that interval")
    final_date = fields.Date('Repeat Until')

    version = fields.Integer("Version", default=1)
    calendar_file = fields.Binary(string="Calendar File")

    state = fields.Selection(
        [('draft', 'Draft'), ('confirm', 'Confirm'), ('cancel', 'Cancelled')],
        string='Status', default='draft', tracking=True
    )

    meeting_room_ids = fields.One2many(
        'meeting.rooms', 
        'meeting_event_id', 
        string="Booked Rooms List",
        readonly=True 
    )

    # === FIELD FOR MULTI-TIMEZONE DISPLAY ===
    multi_timezone_display = fields.Html(
        string="Timezone Details", 
        compute='_compute_multi_timezone_display', 
        store=True,
        help="Display list of local times for each selected room."
    )

    # Computed fields: Display dates in UTC
    start_date_utc_str = fields.Char(
        string="Start (UTC)",
        compute='_compute_utc_date_strings',
        help="Start date/time in UTC timezone"
    )
    end_date_utc_str = fields.Char(
        string="End (UTC)",
        compute='_compute_utc_date_strings',
        help="End date/time in UTC timezone"
    )

    # === NEW FIELD: USER VIEW TIME (SERVER-SIDE CONVERSION) ===
    # This field displays meeting time in the timezone of the currently logged-in user
    # Calculated on server (Python), not in browser. So it cannot be falsified!
    user_view_start_date = fields.Char(
        string="Start Time (My Timezone)",
        compute='_compute_user_view_time',
        help="Waktu meeting dikonversi ke timezone user yang sedang login saat ini."
    )
    
    user_view_end_date = fields.Char(
        string="End Time (My Timezone)",
        compute='_compute_user_view_time',
        help="Waktu meeting dikonversi ke timezone user yang sedang login saat ini."
    )

    # ==========================================================
    # Helper: Compute local times (eliminate code duplication)
    # ==========================================================
    def _compute_local_times(self, tz_name=None):
        """
        Convert meeting times to local timezone with proper DST handling.
        
        This method consolidates timezone conversion logic used in multiple places.
        Properly handles DST by converting the meeting datetime itself, not using current offset.
        
        Args:
            tz_name: Timezone name (if None, uses creator timezone)
        
        Returns:
            dict with keys: 'tz', 'tz_name', 'local_start', 'local_end', 
                           'formatted_date', 'start_time_hours', 'end_time_hours',
                           'tz_offset_str'
        """
        self.ensure_one()
        
        if not tz_name:
            tz_name = (self.host_user_id.tz or self.create_uid.tz or 'UTC')
        
        tz = pytz.timezone(tz_name)
        
        # ✅ CORRECT: Convert the MEETING datetime to its timezone (handles DST correctly)
        start_dt = self.start_date
        end_dt = self.end_date
        if start_dt and start_dt.tzinfo is None:
            start_dt = pytz.utc.localize(start_dt)
        if end_dt and end_dt.tzinfo is None:
            end_dt = pytz.utc.localize(end_dt)

        local_start = start_dt.astimezone(tz)
        local_end = end_dt.astimezone(tz)
        
        # Format strings
        formatted_date = local_start.strftime('%b %d, %Y')
        start_time_hours = local_start.strftime('%H:%M')
        end_time_hours = local_end.strftime('%H:%M')
        
        # Timezone offset string for ICS
        utc_offset = local_start.utcoffset()
        offset_total_seconds = utc_offset.total_seconds()
        offset_hours = int(offset_total_seconds // 3600)
        offset_minutes = int(abs(offset_total_seconds) % 3600 // 60)
        tz_offset_str = f"{'+' if offset_hours >= 0 else '-'}{abs(offset_hours):02d}{abs(offset_minutes):02d}"
        
        return {
            'tz': tz,
            'tz_name': tz_name,
            'local_start': local_start,
            'local_end': local_end,
            'formatted_date': formatted_date,
            'start_time_hours': start_time_hours,
            'end_time_hours': end_time_hours,
            'tz_offset_str': tz_offset_str,
        }

    @api.depends('start_date', 'end_date')
    def _compute_utc_date_strings(self):
        """
        DEBUG MODE: Check current user timezone.
        """
        # --- ADD THIS LOG FOR DEBUGGING ---
        import logging
        _logger = logging.getLogger(__name__)
        
        current_user = self.env.user
        context_tz = self.env.context.get('tz')
        
        _logger.info("="*50)
        _logger.info(f"DEBUG TIMEZONE CHECK")
        _logger.info(f"User Login    : {current_user.name} (ID: {current_user.id})")
        _logger.info(f"User DB TZ    : {current_user.tz} (Yang tersimpan di database)")
        _logger.info(f"Context TZ    : {context_tz} (Yang dikirim oleh Browser/Session)")
        _logger.info("="*50)
        # -------------------------
        """
        Display start and end dates in UTC timezone for reference.
        
        This helps users see the actual UTC values stored in database,
        useful for cross-timezone coordination.
        """
        for rec in self:
            if rec.start_date:
                start_dt = rec.start_date
                if isinstance(start_dt, str):
                    start_dt = fields.Datetime.to_datetime(start_dt)
                if start_dt.tzinfo is None:
                    start_dt = pytz.utc.localize(start_dt)
                rec.start_date_utc_str = start_dt.strftime('%Y-%m-%d %H:%M:%S UTC')
            else:
                rec.start_date_utc_str = ''

            if rec.end_date:
                end_dt = rec.end_date
                if isinstance(end_dt, str):
                    end_dt = fields.Datetime.to_datetime(end_dt)
                if end_dt.tzinfo is None:
                    end_dt = pytz.utc.localize(end_dt)
                rec.end_date_utc_str = end_dt.strftime('%Y-%m-%d %H:%M:%S UTC')
            else:
                rec.end_date_utc_str = ''

    @api.depends('start_date', 'end_date')
    def _compute_user_view_time(self):
        """
        SOLUSI HARDCODE VIA SERVER: Hitung jam berdasarkan Timezone User yang sedang LOGIN.
        
        Ini mem-bypass logika browser dan memaksa hitungan server yang pasti benar.
        Field ini mengembalikan TEXT (String), bukan Datetime, agar browser tidak bisa ubah.
        
        Contoh Output:
        - User Login Jakarta → "12/02/2026 14:00:00 (Asia/Jakarta)"
        - User Login Makassar → "12/02/2026 15:00:00 (Asia/Makassar)"
        - User Login Jayapura → "12/02/2026 16:00:00 (Asia/Jayapura)"
        """
        for rec in self:
            # Get timezone of the user currently viewing this screen
            current_user_tz = self.env.user.tz or 'UTC'
            
            try:
                tz = pytz.timezone(current_user_tz)
            except:
                tz = pytz.utc
            
            # Konversi Start Date
            if rec.start_date:
                utc_start = pytz.utc.localize(rec.start_date)
                local_start = utc_start.astimezone(tz)
                rec.user_view_start_date = f"{local_start.strftime('%d/%m/%Y %H:%M:%S')} ({current_user_tz})"
            else:
                rec.user_view_start_date = "Not Set"
            
            # Konversi End Date
            if rec.end_date:
                utc_end = pytz.utc.localize(rec.end_date)
                local_end = utc_end.astimezone(tz)
                rec.user_view_end_date = f"{local_end.strftime('%d/%m/%Y %H:%M:%S')} ({current_user_tz})"
            else:
                rec.user_view_end_date = "Not Set"

    @api.depends('start_date', 'end_date', 'room_location_ids', 'host_user_id', 'virtual_room_id', 'zoom_link')
    def _compute_multi_timezone_display(self):
        """
        Generate HTML table showing local times for each selected room and virtual meeting.
        
        This computed field creates a visual timezone breakdown that can be displayed in:
        - Form views (meeting_event, meeting.rooms)
        - Activity notifications
        
        The table shows:
        - Physical room locations with their local timezones
        - Virtual meeting platforms (Zoom, etc.) using host timezone
        """
        for rec in self:
            if not rec.start_date or not rec.end_date:
                rec.multi_timezone_display = False
                continue

            html = """
            <table style="width:100%; font-size:13px; color:#444; border:1px solid #eee; background-color:#f9f9f9;">
                <tr style="background-color:#efefef;">
                    <th style="padding:5px; text-align:left;">Location</th>
                    <th style="padding:5px; text-align:left;">Local Time</th>
                </tr>
            """
            
            # Helper function for timezone conversion
            def get_time_str(dt, tz_name):
                """Convert datetime to local time string in given timezone."""
                tz = pytz.timezone(tz_name)
                utc_dt = pytz.utc.localize(dt) if dt.tzinfo is None else dt
                local_dt = utc_dt.astimezone(tz)
                return local_dt.strftime('%H:%M')

            # 1. Loop Physical Rooms
            if rec.room_location_ids:
                for room in rec.room_location_ids:
                    # Determine Room Timezone
                    r_tz = room.tz or rec.host_user_id.tz or 'UTC'
                    
                    start_str = get_time_str(rec.start_date, r_tz)
                    end_str = get_time_str(rec.end_date, r_tz)
                    
                    html += f"""
                    <tr>
                        <td style="padding:5px; border-bottom:1px solid #eee;">🏢 {room.name}</td>
                        <td style="padding:5px; border-bottom:1px solid #eee;">
                            <b>{start_str} - {end_str}</b> <span style="color:#888; font-size:11px;">({r_tz})</span>
                        </td>
                    </tr>
                    """
            
            # 2. Add Virtual Room Row (If link exists)
            if rec.zoom_link or rec.virtual_room_id:
                # Virtual follows Host
                h_tz = rec.host_user_id.tz or 'UTC'
                start_str = get_time_str(rec.start_date, h_tz)
                end_str = get_time_str(rec.end_date, h_tz)
                
                provider_name = "Online Meeting"
                if rec.virtual_room_id:
                    provider_name = dict(rec.virtual_room_id._fields['provider'].selection).get(rec.virtual_room_id.provider, "Virtual")

                html += f"""
                <tr>
                    <td style="padding:5px; border-bottom:1px solid #eee;">🎥 {provider_name} (Host)</td>
                    <td style="padding:5px; border-bottom:1px solid #eee;">
                        <b>{start_str} - {end_str}</b> <span style="color:#888; font-size:11px;">({h_tz})</span>
                    </td>
                </tr>
                """

            html += "</table>"
            rec.multi_timezone_display = html

    # ==========================================================
    # LOGIC: REGENERATE ACTIVITY
    # ==========================================================
    def _regenerate_all_activities(self):
        """
        Regenerate activity notifications for all meeting attendees.
        
        FEATURE: Each attendee receives activity in their own timezone!
        
        This method:
        1. Deletes all existing activities for this meeting
        2. For each attendee, creates activity with their timezone
        3. Email and dates are shown according to attendee's timezone
        4. Triggers email automation for internal users (external users get email only via "SEND EMAIL & DOWNLOAD ICS")
        
        Context:
            mail_activity_automation_skip: If True, skip activity generation
        """
        self.ensure_one()
        ev = self

        if self.env.context.get('mail_activity_automation_skip'):
            return

        # 1. DELETE OLD ACTIVITIES
        old_activities = self.env['mail.activity'].search([
            ('res_id', '=', ev.id),
            ('res_model', '=', 'meeting.event')
        ])
        old_activities.unlink()

        loc_name = ", ".join(ev.room_location_ids.mapped('name')) if ev.room_location_ids else "Virtual"
        
        virtual_room_info = ""
        if ev.zoom_link:
            virtual_room_info = f"<br/><br/><b>Online Meeting:</b> <a href='{ev.zoom_link}' target='_blank'>Click to Join</a>"
        elif ev.virtual_room_id:
            virtual_room_info = f"<br/>(Virtual Room: {ev.virtual_room_id.name})"

        # 3. REGENERATE - EACH ATTENDEE WITH THEIR OWN TIMEZONE
        for user in ev.attendee:
            # Get attendee's timezone (not host's timezone!)
            attendee_tz = user.tz or 'UTC'
            
            # Compute local times using attendee's timezone
            local_times = ev._compute_local_times(attendee_tz)
            
            formatted_start_time = local_times['formatted_date']
            start_time_hours = local_times['start_time_hours']
            end_time_hours = local_times['end_time_hours']
            tz_name = local_times['tz_name']
            
            duration = local_times['local_end'] - local_times['local_start']
            meeting_hours, remainder = divmod(duration.total_seconds(), 3600)
            meeting_minutes, meeting_seconds = divmod(remainder, 60)
            meeting_hours_str = f"{int(meeting_hours)} hours " if meeting_hours > 0 else ""
            meeting_minutes_str = f"{int(meeting_minutes)} minutes" if meeting_minutes > 0 else ""

            # Generate note with attendee's timezone
            # Use host_user_id instead of create_uid (host is the owner of the booking link)
            host_name = ev.host_user_id.name if ev.host_user_id else ev.create_uid.name
            activity_note = f"""
                <p>Hi <b>{user.name}</b>,</p>
                <p>I hope this message finds you well. <b>{host_name}</b> has invited you to the "{ev.subject}" meeting</p>
                
                <p><b>Schedule Details (in your timezone {tz_name}):</b></p>
                <table border="0" style="margin-bottom: 10px;">
                    <tbody>
                        <tr>
                            <td style="width:120px;">Date</td>
                            <td>: {formatted_start_time}</td>
                        </tr>
                        <tr>
                            <td>Time</td>
                            <td>: <b>{start_time_hours} - {end_time_hours}</b> ({tz_name})</td>
                        </tr>
                        <tr>
                            <td>Time (UTC)</td>
                            <td>: {ev.start_date} - {ev.end_date}</td>
                        </tr>
                        <tr>
                            <td>Duration</td>
                            <td>: {meeting_hours_str}{meeting_minutes_str}</td>
                        </tr>
                        <tr>
                            <td>Location</td>
                            <td>: {loc_name} {virtual_room_info}</td>
                        </tr>
                    </tbody>
                </table>
                
                <p><b>Timezone Breakdown:</b></p>
                {ev.multi_timezone_display}
            """
            
            if ev.zoom_link:
                activity_note += f"<p><a href='{ev.zoom_link}' style='background:#00A09D; color:white; padding:5px 10px; text-decoration:none; border-radius:4px;'>Join Meeting</a></p>"

            activity_note += "<br/>"
            
            # Use date_deadline in attendee's timezone
            # Activities will trigger email automation to internal users
            ev.sudo().activity_schedule(
                'meeting_rooms.mail_act_meeting_rooms_approval',
                user_id=user.id,
                date_deadline=local_times['local_start'].date(),
                note=activity_note
            )

    def _can_shared_action(self):
        """Allow actions for admin, creator, or host only."""
        self.ensure_one()
        user = self.env.user
        
        from .constants import GroupNames
        
        # LOGGING DEBUG (No PII - only log IDs, not names)
        _logger.info(f"Permission check - User ID: {user.id}, Creator ID: {self.create_uid.id}, Host ID: {self.host_user_id.id if self.host_user_id else None}")

        # 1. Admin selalu boleh
        if user.has_group(GroupNames.MEETING_MANAGER):
            _logger.info(f"Permission approved: User {user.id} is admin")
            return True
            
        # 2. Creator boleh
        if self.create_uid == user:
            _logger.info(f"Permission approved: User {user.id} is creator")
            return True
            
        # 3. Host boleh
        if self.host_user_id == user:
            _logger.info(f"Permission approved: User {user.id} is host")
            return True
            
        _logger.warning(f"Permission denied: User {user.id} is not admin/creator/host")
        return False

    # ==========================
    # OVERRIDE UNLINK (PERMANENT DELETE)
    # ==========================
    def unlink(self):
        """
        Ensure that when user deletes an Event from database,
        the corresponding Zoom meeting is also deleted from Zoom server.
        """
        # 1. CHECK SUPERUSER (Sudo)
        if self.env.su:
            # Sudo can delete anything, but still need to handle Zoom cleanup
            for rec in self:
                if rec.zoom_id and rec.virtual_room_id and rec.virtual_room_id.provider == 'zoom':
                    try:
                        rec.sudo()._logic_delete_zoom_meeting(rec.zoom_id, context_room=rec.virtual_room_id)
                    except Exception as e:
                        _logger.warning(f"Failed to delete Zoom on Unlink: {str(e)}")
            return super(MeetingEvent, self).unlink()

        # 2. CHECK PERMISSION FOR REGULAR USERS
        is_manager = self.env.user.has_group('meeting_rooms.group_meeting_manager')
        
        for rec in self:
            # User can DELETE IF: Admin OR Creator OR Host
            is_owner = (rec.create_uid == self.env.user) or (rec.host_user_id == self.env.user)
            
            if not is_manager and not is_owner:
                raise UserError(_("ACCESS DENIED: You can only delete meetings where you are the Host or Creator."))

        # 3. PROCESS ZOOM DELETION
        for rec in self:
            if rec.zoom_id and rec.virtual_room_id and rec.virtual_room_id.provider == 'zoom':
                try:
                    # Use sudo() to read credentials if user access is limited
                    rec.sudo()._logic_delete_zoom_meeting(rec.zoom_id, context_room=rec.virtual_room_id)
                except Exception as e:
                    _logger.warning(f"Failed to delete Zoom on Unlink: {str(e)}")
        
        # Continue deleting record in Odoo (this will also invoke built-in Record Rules as double check)
        return super(MeetingEvent, self).unlink()

    # ==========================
    # WRITE / EDIT LOGIC (TRANSACTION-SAFE)
    # ==========================
    def write(self, vals):
        """
        Update meeting event with transaction-safe Zoom meeting management.
        
        When rescheduling (changing dates/virtual room):
        1. Store old Zoom credentials for deletion
        2. Commit changes to database (may fail if conflict)
        3. If successful, delete old Zoom meeting using stored credentials
        4. Regenerate activities if meeting is confirmed
        
        Args:
            vals: Dictionary of field values to update
            
        Returns:
            Result of super().write()
        
        Context:
            skip_rooms_sync: Skip automatic meeting.rooms synchronization
        """
        vals = dict(vals)
        
        # 1. CHECK SUPERUSER (Sudo)
        # If called with .sudo(), self.env.su will be True.
        # Bypass all permission checks so action_confirm can run.
        if self.env.su:
            return super(MeetingEvent, self).write(vals)

        # 2. CHECK PERMISSION FOR REGULAR USERS
        # User must be Admin OR Creator OR Host to edit meeting
        is_manager = self.env.user.has_group('meeting_rooms.group_meeting_manager')
        
        for rec in self:
            # User can EDIT IF: Admin OR Creator OR Host
            is_owner = (rec.create_uid == self.env.user) or (rec.host_user_id == self.env.user)
            
            if not is_manager and not is_owner:
                raise UserError(_("ACCESS DENIED: You cannot edit this meeting because you are not the Host or Creator."))
        
        # 3. PROCESS MEETING EDIT (Extended logic for allowed field editing)
        use_sudo_write = False

        # If user is not manager & not owner, don't continue
        # (Already blocked above, but as extra safety)
        if not is_manager and not is_owner:
            if not self.env.user.has_group('base.group_user'):
                raise UserError(_("You are not allowed to edit this meeting."))

            # Drop unchanged protected fields commonly sent by the form.
            blocked_fields = {
                'start_date',
                'end_date',
                'state',
                'meeting_room_ids',
                'zoom_id',
                'zoom_link',
                'zoom_start_url',
                'zoom_invitation',
                'ai_summary',
                'create_uid',
                'create_date',
                'write_date',
                'host_user_id',
            }
            for field_name in list(blocked_fields):
                if field_name in vals:
                    new_val = vals[field_name]
                    if field_name in {'start_date', 'end_date'}:
                        new_val = fields.Datetime.to_datetime(new_val)
                        if any(fields.Datetime.to_datetime(getattr(rec, field_name)) != new_val for rec in self):
                            raise UserError(_(
                                "You can only update meeting details (location, attendees, and description). "
                                "Start/end time, cancel, and delete are restricted to host or administrator."
                            ))
                    vals.pop(field_name, None)

            allowed_fields = {
                'subject',
                'description',
                'room_location_ids',
                'virtual_room_id',
                'attendee',
                'calendar_alarm',
                'guest_partner_id',
                'guest_emails',
                'recurrency',
                'rrule_type',
                'final_date',
            }
            extra_fields = set(vals.keys()) - allowed_fields
            if extra_fields:
                raise UserError(_(
                    "You can only update meeting details (location, attendees, and description). "
                    "Start/end time, cancel, and delete are restricted to host or administrator."
                ))

            use_sudo_write = True

        reschedule_fields = ['start_date', 'end_date', 'virtual_room_id']
        is_rescheduling = any(f in vals for f in reschedule_fields)

        # 1. Prepare to delete (BUT WAIT)
        zoom_meetings_to_delete = {}
        work = self.sudo() if use_sudo_write else self
        
        if is_rescheduling:
            for rec in work:
                if rec.zoom_id and rec.virtual_room_id and rec.virtual_room_id.provider == 'zoom':
                    # Store ID and the Record Object of the Virtual Room
                    zoom_meetings_to_delete[rec.id] = {
                        'id': rec.zoom_id,
                        'room': rec.virtual_room_id
                    }
            
            # Reset fields in vals to clear UI
            vals['zoom_id'] = False
            vals['zoom_link'] = False
            vals['zoom_start_url'] = False
            vals['zoom_invitation'] = False
            vals['ai_summary'] = False 

        trigger_fields = ['room_location_ids', 'subject', 'attendee', 'zoom_link']
        is_update_needed = is_rescheduling or any(f in vals for f in trigger_fields)
        
        # 2. COMMIT TO DB (This might raise Validation Error if clash)
        res = super(MeetingEvent, work).write(vals)

        # 3. IF SUCCESS, DELETE ZOOM USING OLD CREDENTIALS
        if is_rescheduling:
            # Invalidate cache to ensure zoom fields are properly cleared
            work.invalidate_cache(['zoom_id', 'zoom_link', 'zoom_start_url', 'zoom_invitation', 'ai_summary'])
            
            for rec in work:
                old_data = zoom_meetings_to_delete.get(rec.id)
                if old_data:
                    # Pass the OLD room record to the delete logic
                    rec._logic_delete_zoom_meeting(old_data['id'], context_room=old_data['room'])
            
            for ev in work:
                if ev.state == 'confirm':
                    ev.message_post(body="<b>Schedule Changed.</b> Old meeting link has been deleted. Please click 'Generate Meeting Link' again.")

        # 4. Sync Rooms (Updates timestamps, freeing old slots)
        for ev in work:
            if not self.env.context.get('skip_rooms_sync'):
                ev._sync_rooms_from_event()

            if ev.state == 'confirm' and is_update_needed:
                ev._regenerate_all_activities()
                        
        return res

    # ==========================
    # ACTION CONFIRM (FINAL FIX UI REFRESH)
    # ==========================
    def action_confirm(self):
        """
        Confirm meeting event and trigger activities and room synchronization.
        
        This action:
        1. Regenerates activity notifications for all attendees
        2. Changes state to 'confirm'
        3. Synchronizes meeting.rooms records
        4. Force reload form view to display updated status
        """
        # INITIAL LOGGING
        _logger.info(f"Confirm action initiated by user {self.env.user.id}")

        target_id = None
        for ev in self:
            # 1. Check Permission
            if not ev._can_shared_action():
                _logger.error(f"Permission denied for user {self.env.user.id} on meeting {ev.id}")
                raise UserError(_("You are not authorized to confirm this meeting. You must be the Host or Creator."))

            # 2. Determine Target Write (Bypass Rule if needed)
            # If user is Host but not Creator, they need SUDO to write status
            target = ev
            if ev.create_uid != self.env.user and not self.env.user.has_group('meeting_rooms.group_meeting_manager'):
                _logger.info(f"Using sudo for user {self.env.user.id} to confirm meeting {ev.id}")
                target = ev.sudo()

            try:
                _logger.info(f"Step 1: Regenerating schedule activities for meeting {ev.id}")
                # Create schedule activities (without triggering email automation)
                target._regenerate_all_activities()
                
                _logger.info(f"Step 2: Writing state confirm for meeting {ev.id}")
                target.write({'state': 'confirm'})
                
                _logger.info(f"Step 3: Syncing rooms for meeting {ev.id}")
                from .constants import ContextKey
                target.with_context(**{ContextKey.SKIP_BOOKING_CHECK: True})._sync_rooms_from_event()
                
                _logger.info(f"SUCCESS: Meeting {ev.id} confirmed by user {self.env.user.id}")
                target_id = ev.id
                
            except ValidationError:
                raise  # Re-raise validation errors as-is
            except UserError:
                raise  # Re-raise user errors as-is
            except Exception as e:
                _logger.error(f"Error during confirmation process for meeting {ev.id}: {str(e)}", exc_info=True)
                error_msg = str(e).replace("\\n", "\n")
                raise UserError(_(f"A system error occurred during meeting confirmation:\n\n{error_msg}"))
            
        # 4. FORCE REFRESH FORM VIEW
        # Reload form with latest database data to update status bar
        if target_id:
            return {
                'type': 'ir.actions.act_window',
                'view_mode': 'form',
                'res_model': 'meeting.event',
                'res_id': target_id,
                'target': 'current',
                'flags': {'mode': 'readonly'},
            }
        return True

    # ==========================================================
    # Virtual room actions & helpers
    # ==========================================================
    
    def _get_zoom_supported_timezone(self, tz_name=None):
        """
        Convert user timezone to Zoom-supported timezone.
        Uses 2 methods:
        1. Manual Mapping (For special cases like Indonesia).
        2. Smart Offset Matching (Find major city with same offset).
        """
        # 1. Determine Source Timezone
        if not tz_name:
            tz_name = (self.host_user_id.tz or self.create_uid.tz or 'UTC')
        
        # 2. METHOD A: Manual Mapping (Primary - For special regions)
        mapping = {
            'Asia/Makassar': 'Asia/Singapore',      
            'Asia/Ujung_Pandang': 'Asia/Singapore', 
            'Asia/Jakarta': 'Asia/Bangkok',         
            'Asia/Pontianak': 'Asia/Bangkok',       
            'Asia/Jayapura': 'Asia/Tokyo',          
        }
        
        if tz_name in mapping:
            final_tz = mapping[tz_name]
            _logger.info(f"ZOOM TZ (Manual): {tz_name} -> {final_tz}")
            return final_tz

        # 3. METHOD B: Smart Offset Matching (For users outside mapping)
        # If user timezone not in mapping, check if Zoom supports it natively?
        # For safety, we find a "major city" with same offset.
        
        try:
            user_tz = pytz.timezone(tz_name)
            # Calculate current user offset (e.g.: +01:00)
            user_now = datetime.now(user_tz)
            user_offset = user_now.utcoffset()

            # List of "safe major cities" definitely supported by Zoom (Representative)
            safe_zones = [
                'UTC',
                'Asia/Singapore', 'Asia/Bangkok', 'Asia/Tokyo', 'Asia/Seoul', 'Asia/Dubai', 'Asia/Kolkata',
                'Europe/London', 'Europe/Paris', 'Europe/Berlin', 'Europe/Moscow',
                'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles', 'America/Sao_Paulo',
                'Australia/Sydney', 'Pacific/Auckland'
            ]

            # Check one-by-one for matching offset with User
            for safe_name in safe_zones:
                safe_tz = pytz.timezone(safe_name)
                safe_now = datetime.now(safe_tz)
                safe_offset = safe_now.utcoffset()

                # If offset matches exactly (daylight saving differences ignored)
                if user_offset == safe_offset:
                    _logger.info(f"ZOOM TZ (Smart Match): {tz_name} -> {safe_name} (Same Offset)")
                    return safe_name
            
            # If no match found, return original (hope Zoom supports it)
            # or default to UTC for safety and avoid errors.
            _logger.warning(f"ZOOM TZ: No match found for {tz_name}, defaulting to UTC")
            return 'UTC'

        except Exception as e:
            _logger.error(f"ZOOM TZ Error: {e}")
            return 'UTC'

    def _logic_delete_zoom_meeting(self, meeting_id, context_room=None):
        """
        Delete a Zoom meeting from Zoom server.
        
        Args:
            meeting_id: Zoom meeting ID (must be numeric string)
            context_room: virtual.room record with credentials (uses self.virtual_room_id if None)
        """
        try:
            if not meeting_id.isdigit(): 
                return 
            
            url = f"https://api.zoom.us/v2/meetings/{meeting_id}"
            headers = self._get_zoom_headers(context_room)
            
            res = requests.delete(url, headers=headers, timeout=10)
            if res.status_code == 204:
                _logger.info(f"Zoom Meeting {meeting_id} deleted successfully.")
                self.message_post(body=f"Previous Zoom Meeting ({meeting_id}) deleted from server.")
            else:
                _logger.warning(f"Failed to delete Zoom {meeting_id}: {res.text}")
        except Exception as e:
            _logger.error(f"Error deleting zoom: {e}")

    def action_generate_virtual_link(self):
        """
        Generate virtual meeting link based on selected provider (Zoom/Teams/Google Meet).
        
        Raises:
            UserError: If no virtual room is selected
        """
        self.ensure_one()
        if not self._can_shared_action():
            raise UserError(_("You are not allowed to generate meeting links."))

        target = self if (self.create_uid == self.env.user or self.env.user.has_group('meeting_rooms.group_meeting_manager')) else self.sudo()
        if not target.virtual_room_id:
            raise UserError(_("Please select a Virtual Room first."))
        
        provider = getattr(target.virtual_room_id, 'provider', 'zoom')
        
        if provider == 'zoom':
            target._logic_generate_zoom()
        elif provider == 'google_meet':
            target._logic_generate_google_meet()
        elif provider == 'teams':
            target._logic_generate_teams()
        else:
            target._logic_generate_manual_link()

    def _get_zoom_credentials(self, context_room=None):
        """
        Extract Zoom API credentials from virtual room configuration.
        
        Args:
            context_room: virtual.room record (uses self.virtual_room_id if None)
            
        Returns:
            Tuple of (account_id, client_id, client_secret)
            
        Raises:
            UserError: If credentials are missing
        """
        room = (context_room or self.virtual_room_id).sudo()
        if not room:
             raise UserError(_("Virtual Room configuration missing."))
             
        account_id = room.zoom_account_id
        client_id = room.zoom_client_id
        client_secret = room.zoom_client_secret

        if not account_id or not client_id or not client_secret:
            raise UserError(_("Zoom Credentials (Account/Client/Secret) missing for room %s.") % room.name)    
        return account_id, client_id, client_secret

    def _get_zoom_access_token(self, context_room=None):
        """
        Obtain OAuth access token from Zoom API.
        
        Args:
            context_room: virtual.room record with credentials
            
        Returns:
            Access token string
            
        Raises:
            UserError: If authentication fails
        """
        account_id, client_id, client_secret = self._get_zoom_credentials(context_room)
        url = f"https://zoom.us/oauth/token?grant_type=account_credentials&account_id={account_id}"
        try:
            response = requests.post(url, auth=HTTPBasicAuth(client_id, client_secret), timeout=30)
            response.raise_for_status()
            return response.json()['access_token']
        except requests.exceptions.Timeout:
            _logger.error(f"Zoom auth timeout for meeting {self.id}")
            raise UserError(_("Zoom connection timeout. Please check your network."))
        except requests.exceptions.ConnectionError:
            _logger.error(f"Zoom connection error for meeting {self.id}")
            raise UserError(_("Cannot reach Zoom servers. Check your internet connection."))
        except requests.exceptions.HTTPError as e:
            error_code = e.response.status_code if hasattr(e, 'response') else 'Unknown'
            _logger.error(f"Zoom API error {error_code} for meeting {self.id}")
            raise UserError(_(f"Zoom authentication failed (HTTP {error_code}). Check your credentials."))
        except (ValueError, KeyError) as e:
            _logger.error(f"Invalid Zoom response for meeting {self.id}: {str(e)}", exc_info=True)
            raise UserError(_("Zoom returned invalid response. Please try again later."))

    def _get_zoom_headers(self, context_room=None):
        """
        Build HTTP headers with Zoom OAuth token for API requests.
        
        Args:
            context_room: virtual.room record with credentials
            
        Returns:
            Dictionary of HTTP headers
        """
        token = self._get_zoom_access_token(context_room)
        return {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}

    def _logic_generate_zoom(self):
        """
        Create a new Zoom meeting via Zoom API.
        
        Uses creator's timezone for meeting scheduling (virtual meeting context).
        Automatically maps unsupported timezones to Zoom-compatible equivalents.
        
        Raises:
            UserError: If meeting link already exists or API call fails
        """
        # Refresh record to get latest data from database
        self.invalidate_cache()
        
        if self.zoom_id:
            raise UserError(_("Meeting Link already exists! If you want to regenerate, please save the form first to clear the old link."))

        duration_seconds = (self.end_date - self.start_date).total_seconds()
        duration_minutes = int(duration_seconds / 60)

        # Use creator timezone for virtual meeting scheduling
        tz_name = self.host_user_id.tz or self.create_uid.tz or 'UTC'
        zoom_tz = self._get_zoom_supported_timezone(tz_name)

        url = "https://api.zoom.us/v2/users/me/meetings"
        headers = self._get_zoom_headers() 
        
        start_time_utc = self.start_date.strftime('%Y-%m-%dT%H:%M:%SZ')
        
        payload = {
            "topic": self.subject,
            "type": 2, 
            "start_time": start_time_utc,
            "duration": duration_minutes,
            "timezone": zoom_tz, 
            "settings": {
                "host_video": True,
                "participant_video": True,
                "auto_recording": "cloud"
            }
        }
        
        try:
            res = requests.post(url, headers=headers, json=payload, timeout=30)
            res.raise_for_status()
            zoom_response = res.json()
        except Exception as e:
            raise UserError(_("Failed to create Zoom meeting: %s") % e)

        join_url = zoom_response.get('join_url', '')
        meeting_id = str(zoom_response.get('id', ''))
        password = zoom_response.get('password', '')

        self.write({
            'zoom_id': meeting_id,
            'zoom_link': join_url,
            'zoom_start_url': zoom_response.get('start_url', ''),
        })

        self._generate_invitation_text("Zoom Meeting", join_url, meeting_id, password, zoom_tz)
        
        self.message_post(body=f"Zoom Meeting Created ({zoom_tz}): <a href='{join_url}' target='_blank'>{join_url}</a>")

    def _get_google_meet_credentials(self, context_room=None):
        """
        Extract Google Meet API credentials from virtual room configuration.
        
        Args:
            context_room: virtual.room record (uses self.virtual_room_id if None)
            
        Returns:
            Tuple of (project_id, client_email, private_key)
            
        Raises:
            UserError: If credentials are missing
        """
        room = (context_room or self.virtual_room_id).sudo()
        if not room:
            raise UserError(_("Virtual Room configuration missing."))
        
        project_id = room.google_project_id
        client_email = room.google_client_email
        private_key = room.google_private_key

        if not project_id or not client_email or not private_key:
            raise UserError(_("Google Meet Credentials (Project ID / Client Email / Private Key) missing for room %s.") % room.name)
        
        return project_id, client_email, private_key

    def _get_google_meet_access_token(self, context_room=None):
        """
        Generate OAuth access token from Google service account credentials.
        
        Args:
            context_room: virtual.room record with credentials
            
        Returns:
            Access token string
            
        Raises:
            UserError: If authentication fails
        """
        project_id, client_email, private_key = self._get_google_meet_credentials(context_room)
        
        # Clean input - remove all whitespace issues
        raw_input = private_key.strip()
        
        # Try multiple parsing strategies
        private_key_str = None
        
        # Strategy 1: Check if it already starts with -----BEGIN (direct key paste)
        if raw_input.startswith('-----BEGIN'):
            private_key_str = raw_input
        else:
            # Strategy 2: Try to find private_key field using regex (works even with broken JSON)
            import re
            
            # Pattern 1: Look for "private_key":"-----BEGIN...-----END PRIVATE KEY-----"
            pattern1 = r'"private_key"\s*[:=]\s*"(-----BEGIN[^"]*-----END PRIVATE KEY-----)"'
            match = re.search(pattern1, raw_input, re.DOTALL)
            
            if match:
                private_key_str = match.group(1)
            else:
                # Pattern 2: More flexible - look for anything between -----BEGIN and -----END
                pattern2 = r'(-----BEGIN PRIVATE KEY-----.*?-----END PRIVATE KEY-----)'
                match = re.search(pattern2, raw_input, re.DOTALL)
                
                if match:
                    private_key_str = match.group(1)
                else:
                    raise UserError(_(
                        "Cannot find valid private key. Please:\n"
                        "1. Open the JSON file with a text editor\n"
                        "2. Find the 'private_key' field\n"
                        "3. Copy ONLY the value from -----BEGIN PRIVATE KEY----- to -----END PRIVATE KEY-----\n"
                        "4. Paste it here"
                    ))
        
        # Clean the extracted key
        private_key_str = private_key_str.strip()
        
        # Replace escaped newlines (\\n becomes actual newline)
        private_key_str = private_key_str.replace('\\n', '\n')
        
        # Final validation
        if not private_key_str.startswith('-----BEGIN'):
            raise UserError(_("Private key extraction failed. Start: %s") % private_key_str[:50])
        
        # Create JWT token
        from datetime import datetime, timedelta
        
        now = datetime.utcnow()
        exp = now + timedelta(seconds=3600)
        
        header = {'alg': 'RS256', 'typ': 'JWT'}
        payload = {
            'iss': client_email,
            'scope': 'https://www.googleapis.com/auth/calendar',
            'aud': 'https://oauth2.googleapis.com/token',
            'exp': int(exp.timestamp()),
            'iat': int(now.timestamp())
        }
        
        # Encode JWT
        import base64
        header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip('=')
        payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
        message = f"{header_b64}.{payload_b64}"
        
        # Sign JWT with private key
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
            from cryptography.hazmat.backends import default_backend
            
            # Convert string to bytes
            private_key_bytes = private_key_str.encode('utf-8')
            
            private_key_obj = serialization.load_pem_private_key(
                private_key_bytes,
                password=None,
                backend=default_backend()
            )
            
            signature = private_key_obj.sign(
                message.encode(),
                padding.PKCS1v15(),
                hashes.SHA256()
            )
            
            signature_b64 = base64.urlsafe_b64encode(signature).decode().rstrip('=')
            jwt_token = f"{message}.{signature_b64}"
        except Exception as e:
            _logger.error("JWT signing failed: %s", e)
            raise UserError(_("Failed to generate JWT token: %s") % e)
        
        # Exchange JWT for access token
        url = 'https://oauth2.googleapis.com/token'
        payload_token = {
            'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
            'assertion': jwt_token
        }
        
        try:
            response = requests.post(url, data=payload_token, timeout=30)
            response_data = response.json()
            
            # Log full response for debugging
            _logger.info("Google OAuth Response: %s", response_data)
            
            if response.status_code != 200:
                error_msg = response_data.get('error', 'Unknown error')
                error_desc = response_data.get('error_description', '')
                raise UserError(_(
                    "Google authentication failed!\n\n"
                    "Error: %s\n"
                    "Description: %s\n\n"
                    "Please check:\n"
                    "1. APIs are enabled (Calendar API & Meet API)\n"
                    "2. Service account has correct permissions\n"
                    "3. Private key is correct"
                ) % (error_msg, error_desc))
            
            if 'access_token' not in response_data:
                raise UserError(_(
                    "No access_token in Google response.\n\n"
                    "Response: %s\n\n"
                    "This usually means the service account doesn't have proper permissions."
                ) % str(response_data))
            
            return response_data['access_token']
        except requests.exceptions.RequestException as e:
            _logger.error("Google Auth Request Error: %s", e)
            raise UserError(_("Failed to connect to Google: %s") % str(e))
        except UserError:
            raise
        except Exception as e:
            _logger.error("Google Auth Error: %s", e)
            raise UserError(_("Google authentication failed: %s") % str(e))

    def _logic_generate_google_meet(self):
        """
        Use static Google Meet link from Virtual Room configuration.
        
        Simple approach: reuse the permanent Google Meet link provided by user.
        No API calls required - just assign the static link to the meeting.
        
        Raises:
            UserError: If meeting link already exists or static link not configured
        """
        # Refresh record to get latest data from database
        self.invalidate_cache()
        
        if self.zoom_id:
            raise UserError(_("Meeting Link already exists! If you want to regenerate, please save the form first to clear the old link."))

        room = self.virtual_room_id.sudo()
        
        if not room.static_link:
            raise UserError(_(
                "Google Meet link not configured!\n\n"
                "Please configure a permanent Google Meet link in the Virtual Room settings:\n"
                "1. Go to meet.google.com\n"
                "2. Create a meeting for later\n"
                "3. Copy the link\n"
                "4. Paste it in Virtual Room configuration"
            ))
        
        meet_link = room.static_link.strip()
        
        # Validate link format
        if not meet_link.startswith('http'):
            meet_link = 'https://' + meet_link
        
        self.write({
            'zoom_id': 'Google Meet',
            'zoom_link': meet_link,
            'zoom_start_url': meet_link,
        })
        
        self._generate_invitation_text("Google Meet", meet_link)
        self.message_post(body=f"Google Meet Link Assigned: <a href='{meet_link}' target='_blank'>{meet_link}</a>")

    def _get_teams_token(self):
        """
        Obtain OAuth token from Microsoft Azure AD for Teams API access.
        
        Returns:
            Access token string
            
        Raises:
            UserError: If credentials missing or authentication fails
        """
        room = self.virtual_room_id.sudo()
        tenant_id = room.zoom_account_id
        client_id = room.zoom_client_id
        client_secret = room.zoom_client_secret

        if not tenant_id or not client_id or not client_secret:
            raise UserError(_("For Teams, please fill: Account ID (Tenant), Client ID, and Secret."))

        url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        payload = {
            'grant_type': 'client_credentials',
            'client_id': client_id,
            'client_secret': client_secret,
            'scope': 'https://graph.microsoft.com/.default'
        }
        
        try:
            res = requests.post(url, data=payload, timeout=30)
            res.raise_for_status()
            return res.json().get('access_token')
        except Exception as e:
             raise UserError(_("Failed to login to Microsoft Azure: %s") % e)

    def _logic_generate_teams(self):
        """
        Create a new Microsoft Teams meeting via Microsoft Graph API.
        
        Requires:
        - Azure AD tenant ID, client ID, and client secret in virtual room config
        - Valid host email address
        
        Raises:
            UserError: If credentials missing, user not found, or API call fails
        """
        # Refresh record to get latest data from database
        self.invalidate_cache()
        
        if self.zoom_id:
            raise UserError(_("Meeting Link already exists! If you want to regenerate, please save the form first to clear the old link."))

        token = self._get_teams_token()
        room = self.virtual_room_id.sudo()
        host_email = room.email or self.env.user.email
        if not host_email:
             raise UserError(_("Host Email required for Teams Meeting."))

        try:
            user_url = f"https://graph.microsoft.com/v1.0/users/{host_email}"
            user_res = requests.get(user_url, headers={'Authorization': 'Bearer ' + token}, timeout=30)
            if user_res.status_code != 200:
                 raise UserError(_("User with email %s not found in Azure AD.") % host_email)
            azure_user_id = user_res.json().get('id')
        except Exception as e:
            raise UserError(_("Failed to find Azure user: %s") % e)

        create_url = f"https://graph.microsoft.com/v1.0/users/{azure_user_id}/onlineMeetings"
        
        start_dt = self.start_date.isoformat() + "Z" 
        end_dt = self.end_date.isoformat() + "Z"   
        
        payload = {
            "startDateTime": start_dt,
            "endDateTime": end_dt,
            "subject": self.subject,
        }

        try:
            res = requests.post(create_url, headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}, json=payload, timeout=30)
            res.raise_for_status()
            data = res.json()
            join_url = data.get('joinWebUrl')
            
            self.write({
                'zoom_id': 'Microsoft Teams', 
                'zoom_link': join_url,
                'zoom_start_url': join_url,
            })
            
            self._generate_invitation_text("Microsoft Teams", join_url)
            self.message_post(body=f"Teams Meeting Created: <a href='{join_url}' target='_blank'>Join Teams</a>")

        except Exception as e:
            raise UserError(_("Failed to create Teams meeting: %s") % e)

    def _logic_generate_manual_link(self):
        raise UserError(_("Provider logic not implemented yet."))

    def _generate_invitation_text(self, provider_name, url, mid=False, pwd=False, tz_info=False):
        """
        Generate invitation text for meeting.
        
        Args:
            provider_name: Name of the meeting provider (Zoom/Teams/Google Meet)
            url: Meeting join URL
            mid: Meeting ID (optional, provider-specific)
            pwd: Password (IGNORED for security - not included in invitation)
            tz_info: Timezone information string (optional)
            
        Security Note: 
            Password parameter is intentionally ignored and never included in invitation text.
            Users receive passwords through secure provider notification channels only.
        """
        text = (
            f"Topic: {self.subject}\n"
            f"Time: {self.start_date} (UTC)\n"
        )
        if tz_info:
             text += f"Timezone Reference: {tz_info}\n"

        text += f"\nJoin {provider_name}\n{url}\n\n"
        
        if mid and mid != 'Google Meet' and mid != 'Microsoft Teams':
            text += f"Meeting ID: {mid}\n"
        # Password is NOT included for security reasons
        self.write({'zoom_invitation': text})

    def action_get_ai_summary(self):
        """
        Fetch AI-generated meeting summary from Zoom API.
        
        Only available for Zoom meetings with AI summary feature enabled.
        Summary must be generated by Zoom after meeting concludes.
        
        Raises:
            UserError: If provider is not Zoom, no meeting ID, or summary unavailable
        """
        self.ensure_one()
        if not self._can_shared_action():
            raise UserError(_("You are not allowed to generate AI summaries."))

        target = self if (self.create_uid == self.env.user or self.env.user.has_group('meeting_rooms.group_meeting_manager')) else self.sudo()
        provider = getattr(target.virtual_room_id, 'provider', 'zoom')
        if provider != 'zoom':
            raise UserError(_("AI Summary only available for Zoom."))

        if not target.zoom_id:
            raise UserError(_("No Meeting ID found."))
        
        new_summary = target._logic_fetch_formatted_summary(target.zoom_id)
        if not new_summary:
            raise UserError(_("Failed to fetch summary. Meeting might not have AI Summary enabled or is not finished yet."))

        header_style = "border-top: 2px solid #00A09D; margin-top: 20px; padding-top: 10px; color: #00A09D;"
        divider = f"<div style='{header_style}'><h3>✨ Meeting AI Summary Result</h3></div>"
        target.write({'ai_summary': divider + new_summary})

    def _logic_fetch_formatted_summary(self, mid):
        """
        Fetch and format Zoom AI summary with fallback to past meeting UUID.
        
        Args:
            mid: Zoom meeting ID
            
        Returns:
            HTML-formatted summary string or False if not found
        """
        content = self._try_fetch_summary(mid)
        if not content:
            uuid = self._find_past_meeting_uuid(mid)
            if uuid:
                encoded_uuid = urllib.parse.quote(urllib.parse.quote(uuid, safe=''), safe='')
                content = self._try_fetch_summary(encoded_uuid)
        return content

    def _try_fetch_summary(self, mid):
        """
        Attempt to fetch Zoom AI summary for a meeting.
        
        Args:
            mid: Zoom meeting ID or UUID
            
        Returns:
            HTML-formatted summary string or False if summary not available
        """
        url = f"https://api.zoom.us/v2/meetings/{mid}/meeting_summary"
        try:
            res = requests.get(url, headers=self._get_zoom_headers(), timeout=30)
            if res.status_code != 200:
                _logger.error("Zoom API Error: Status %s - Body: %s", res.status_code, res.text)
                return False

            data = res.json()
            html_content = ""
            title = data.get('summary_title')
            if title: html_content += f"<h2>{title}</h2>"
            overview = data.get('summary_overview')
            if overview:
                html_content += (f"<div style='background-color:#f8f9fa; padding:15px; margin-bottom: 20px;'>"
                                 f"<strong style='color:#00A09D;'>Quick Recap:</strong><br/>{overview}</div>")
            
            details = data.get('summary_details', [])
            if details:
                html_content += "<hr/><h4>📝 Detailed Summary:</h4>"
                for item in details:
                    label = item.get('label') or 'Topic'
                    summary_text = item.get('summary', '')
                    if isinstance(summary_text, list): summary_text = " ".join(summary_text)
                    html_content += (f"<div style='margin-bottom: 15px;'><strong style='font-size: 1.1em; color: #2C3E50;'>{label}</strong>"
                                     f"<p>{summary_text}</p></div>")
            return html_content
        except Exception as e:
            _logger.error("Zoom Summary Exception: %s", e)
            return False

    def _find_past_meeting_uuid(self, mid):
        """
        Find UUID of the most recent past meeting instance.
        
        Used for fetching AI summaries which require UUID instead of meeting ID.
        
        Args:
            mid: Zoom meeting ID
            
        Returns:
            Meeting UUID string or False if not found
        """
        url = f"https://api.zoom.us/v2/past_meetings/{mid}/instances"
        try:
            res = requests.get(url, headers=self._get_zoom_headers(), timeout=30)
            if res.status_code == 200 and res.json().get('meetings'):
                return res.json()['meetings'][-1].get('uuid')
        except Exception:
            return False
        return False

    def _get_alarm_id(self):
        """
        Get calendar alarm/reminder ID for this meeting.
        
        Returns:
            Alarm ID if configured, otherwise first available alarm, or False
        """
        self.ensure_one()
        if self.calendar_alarm:
            return self.calendar_alarm.id
        alarm = self.env['calendar.alarm'].search([], limit=1)
        return alarm.id if alarm else False

    def _sync_rooms_from_event(self):
        """
        Synchronize meeting.rooms records to match current event configuration.
        
        This method:
        1. Creates or updates meeting.rooms records for each location
        2. Cancels meeting.rooms for removed locations
        3. Preserves existing records when possible
        
        Only processes confirmed meetings (state='confirm').
        
        Context:
            skip_event_sync: Prevents infinite recursion
            skip_booking_check: Bypasses double-booking validation
            skip_readonly_check: Allows system to modify readonly meeting.rooms
        """
        MeetingRooms = self.env['meeting.rooms']
        for ev in self:
            if ev.state != 'confirm':
                continue
            
            existing = MeetingRooms.search([('meeting_event_id', '=', ev.id)])
            by_loc = {r.room_location.id: r for r in existing if r.room_location}
            alarm_id = ev._get_alarm_id()
            keep_ids = []

            for loc in ev.room_location_ids:
                vals = {
                    'meeting_event_id': ev.id,
                    'subject': ev.subject,
                    'name': ev.subject,
                    'room_location': loc.id,
                    'virtual_room_id': ev.virtual_room_id.id,
                    'host_user_id': ev.host_user_id.id if ev.host_user_id else None,
                    'start_date': ev.start_date,
                    'end_date': ev.end_date,
                    'description': ev.description,
                    'attendee': [(6, 0, ev.attendee.ids)],
                    'recurrency': ev.recurrency,
                    'rrule_type': ev.rrule_type,
                    'final_date': ev.final_date,
                    'state': 'confirm',
                }

                if alarm_id:
                    vals['calendar_alarm'] = alarm_id

                if loc.id in by_loc:
                    by_loc[loc.id].with_context(skip_event_sync=True, skip_booking_check=True, skip_readonly_check=True).write(vals)
                    keep_ids.append(by_loc[loc.id].id)
                else:
                    new_b = MeetingRooms.with_context(skip_event_sync=True, skip_booking_check=True, skip_readonly_check=True).create(vals)
                    keep_ids.append(new_b.id)

            leftovers = existing.filtered(lambda r: r.id not in keep_ids)
            if leftovers:
                leftovers.with_context(skip_event_sync=True, skip_booking_check=True, skip_readonly_check=True).write({'state': 'cancel'})

    # =========================================================
    # CONSTRAINTS - TRIPLE VALIDATION
    # =========================================================
    @api.constrains('start_date', 'end_date', 'room_location_ids', 'virtual_room_id', 'attendee', 'state')
    def _check_double_booking(self):
        """
        Prevent double booking across three dimensions: locations, virtual rooms, and attendees.
        
        Validation applies only to confirmed meetings and checks for time overlaps:
        1. Physical room location conflicts
        2. Virtual room account conflicts (one Zoom account can't host multiple meetings)
        3. Attendee conflicts (people can't be in two meetings simultaneously)
        
        Context:
            skip_double_booking_check: Bypass all validation (use with caution)
            
        Raises:
            ValidationError: If any conflict is detected
        """
        if self.env.context.get('skip_double_booking_check'):
            return

        for ev in self:
            if ev.state != 'confirm':
                continue

            base_domain = [
                ('id', '!=', ev.id),                
                ('state', '=', 'confirm'), 
                ('start_date', '<', ev.end_date),   
                ('end_date', '>', ev.start_date),   
            ]

            if ev.room_location_ids:
                domain_loc = base_domain + [('room_location_ids', 'in', ev.room_location_ids.ids)]
                conflict_loc = self.search(domain_loc, limit=1)
                if conflict_loc:
                    clashed_rooms = set(ev.room_location_ids.mapped('name')) & set(conflict_loc.room_location_ids.mapped('name'))
                    raise ValidationError(_(
                        f"Location Conflict!\n"
                        f"\n"
                        f"The following room(s) are already booked: {', '.join(clashed_rooms)}\n"
                        f"Conflicting meeting: '{conflict_loc.subject}'"
                    ))

            if ev.virtual_room_id:
                domain_virtual = base_domain + [('virtual_room_id', '=', ev.virtual_room_id.id)]
                conflict_virtual = self.search(domain_virtual, limit=1)
                if conflict_virtual:
                    raise ValidationError(_(
                        f"Virtual Room Conflict!\n"
                        f"\n"
                        f"The virtual room '{ev.virtual_room_id.name}' is already in use.\n"
                        f"Conflicting meeting: '{conflict_virtual.subject}'"
                    ))

            if ev.attendee:
                domain_user = base_domain + [('attendee', 'in', ev.attendee.ids)]
                conflict_user = self.search(domain_user, limit=1)
                if conflict_user:
                    busy_people = set(ev.attendee.mapped('name')) & set(conflict_user.attendee.mapped('name'))
                    if busy_people:
                        raise ValidationError(_(
                            f"Attendee Conflict!\n"
                            f"\n"
                            f"The following person(s) have another meeting scheduled:\n"
                            f"{', '.join(busy_people)}\n"
                            f"\n"
                            f"Conflicting meeting: '{conflict_user.subject}'"
                        ))

    # ==========================
    # ICS / CALENDAR GENERATION (FIXED & ROBUST)
    # ==========================
    def _generate_timezone_breakdown_html(self):
        """
        Generate HTML table showing meeting times in all relevant timezones.
        Includes: physical locations + virtual room (host timezone)
        """
        self.ensure_one()
        
        breakdown = "<h4 style='color: #2c3e50; margin-top: 20px; margin-bottom: 10px;'>Timezone Breakdown:</h4>"
        breakdown += "<table style='width:100%; font-size:13px; color:#444; border:1px solid #ddd; background-color:#f9f9f9;'>"
        breakdown += "<tr style='background-color:#e8e8e8;'><th style='padding:8px; text-align:left;'>Location</th><th style='padding:8px; text-align:left;'>Local Time</th></tr>"
        
        # Add physical room locations
        if self.room_location_ids:
            for location in self.room_location_ids:
                # Get location timezone (if not set, use host timezone)
                loc_tz_name = getattr(location, 'tz', None) or (self.host_user_id.tz or self.create_uid.tz or 'UTC')
                local_times = self._compute_local_times(loc_tz_name)
                start_time = local_times['start_time_hours']
                end_time = local_times['end_time_hours']
                breakdown += f"<tr><td style='padding:8px; border-bottom:1px solid #ddd;'>🏢 {location.name}</td><td style='padding:8px; border-bottom:1px solid #ddd;'><b>{start_time} - {end_time}</b> <span style='color:#888; font-size:11px;'>({loc_tz_name})</span></td></tr>"
        
        # Add virtual room (in host timezone)
        if self.zoom_link or self.virtual_room_id:
            host_tz_name = self.host_user_id.tz or self.create_uid.tz or 'UTC'
            local_times = self._compute_local_times(host_tz_name)
            start_time = local_times['start_time_hours']
            end_time = local_times['end_time_hours']
            provider_name = "Zoom (Host)"
            if self.virtual_room_id:
                provider_name = f"{self.virtual_room_id.provider.replace('_', ' ').title() or 'Virtual Room'} (Host)"
            breakdown += f"<tr><td style='padding:8px; border-bottom:1px solid #ddd;'>🎥 {provider_name}</td><td style='padding:8px; border-bottom:1px solid #ddd;'><b>{start_time} - {end_time}</b> <span style='color:#888; font-size:11px;'>({host_tz_name})</span></td></tr>"
        
        breakdown += "</table>"
        return breakdown

    def _generate_ics_full_content(self, recipient_name=None, recipient_tz=None):
        """
        Generate full formatted content for ICS DESCRIPTION field.
        Includes: greeting, schedule details (date/time/utc/duration), location, and timezone breakdown.
        Similar to activity format for consistency.
        
        Args:
            recipient_name: Name of email recipient (for greeting)
            recipient_tz: Timezone of recipient
        """
        self.ensure_one()
        
        if not recipient_name:
            recipient_name = self.create_uid.name
        if not recipient_tz:
            recipient_tz = self.host_user_id.tz or self.create_uid.tz or 'UTC'
        
        # Get recipient local times
        local_times = self._compute_local_times(recipient_tz)
        local_start = local_times['local_start']
        local_end = local_times['local_end']
        start_date_str = local_start.strftime('%b %d, %Y')
        start_time_str = local_start.strftime('%H:%M')
        end_time_str = local_end.strftime('%H:%M')
        
        # Get UTC times
        utc_start = self.start_date
        utc_end = self.end_date
        if utc_start and utc_start.tzinfo is None:
            utc_start = pytz.utc.localize(utc_start)
        if utc_end and utc_end.tzinfo is None:
            utc_end = pytz.utc.localize(utc_end)
        utc_start_str = utc_start.strftime('%Y-%m-%d %H:%M:%S')
        utc_end_str = utc_end.strftime('%Y-%m-%d %H:%M:%S')
        
        # Calculate duration
        duration = self.end_date - self.start_date
        duration_hours = int(duration.total_seconds() // 3600)
        duration_minutes = int((duration.total_seconds() % 3600) // 60)
        duration_str = ""
        if duration_hours > 0:
            duration_str = f"{duration_hours} hours "
        if duration_minutes > 0:
            duration_str += f"{duration_minutes} minutes"
        
        # Room locations
        loc_names = ", ".join(self.room_location_ids.mapped('name')) if self.room_location_ids else "Virtual"
        
        # Build content (without greeting - start directly from "I hope...")
        lines = [
            f"I hope this message finds you well. {self.create_uid.name} has invited you to the \"{self.subject}\" meeting",
            "",
            f"Schedule Details (in your timezone {recipient_tz}):",
            "",
            f"Date\t: {start_date_str}",
            f"Time\t: {start_time_str} - {end_time_str} ({recipient_tz})",
            f"Time (UTC)\t: {utc_start_str} - {utc_end_str}",
            f"Duration\t: {duration_str}",
            f"Location\t: {loc_names}",
            ""
        ]
        
        # Add online meeting link if exists
        if self.zoom_link:
            lines.append(f"Online Meeting: {self.zoom_link}")
            lines.append("")
        
        # Add timezone breakdown
        lines.append("Timezone Breakdown:")
        lines.append("")
        
        # Add physical rooms with their timezones
        if self.room_location_ids:
            for location in self.room_location_ids:
                loc_tz_name = getattr(location, 'tz', None) or (self.host_user_id.tz or self.create_uid.tz or 'UTC')
                loc_times = self._compute_local_times(loc_tz_name)
                loc_start_time = loc_times['start_time_hours']
                loc_end_time = loc_times['end_time_hours']
                lines.append(f"🏢 {location.name}\t{loc_start_time} - {loc_end_time} ({loc_tz_name})")
        
        # Add virtual room
        if self.zoom_link or self.virtual_room_id:
            host_tz_name = self.host_user_id.tz or self.create_uid.tz or 'UTC'
            host_times = self._compute_local_times(host_tz_name)
            host_start_time = host_times['start_time_hours']
            host_end_time = host_times['end_time_hours']
            provider_name = f"{self.virtual_room_id.provider.replace('_', ' ').title() or 'Virtual Room'} (Host)" if self.virtual_room_id else "Zoom (Host)"
            lines.append(f"🎥 {provider_name}\t{host_start_time} - {host_end_time} ({host_tz_name})")
        
        return "\n".join(lines)

    def _generate_ics_content_string(self, rec, local_times, tz_name, tz_offset_str, attendee_email):
        """
        Helper to generate ICS string for a specific timezone.
        POIN 1: Setiap attendee mendapat ICS dengan timezone mereka sendiri.
        """
        create_time = rec.create_date.strftime('%Y%m%dT%H%M%SZ')
        dt_start = local_times['local_start'].strftime('%Y%m%dT%H%M%S')
        dt_end = local_times['local_end'].strftime('%Y%m%dT%H%M%S')
        
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Odoo Meeting Rooms//EN",
            "METHOD:REQUEST",
            "BEGIN:VTIMEZONE",
            f"TZID:{tz_name}",
            "BEGIN:STANDARD",
            "DTSTART:19700101T000000",
            f"TZOFFSETFROM:{tz_offset_str}",
            f"TZOFFSETTO:{tz_offset_str}",
            f"TZNAME:{tz_name}",
            "END:STANDARD",
            "END:VTIMEZONE",
            "BEGIN:VEVENT",
            f"UID:meeting_event_{rec.id}",
            f"SUMMARY:{rec.subject}",
            f"DTSTAMP:{create_time}",
            f"DTSTART;TZID={tz_name}:{dt_start}",
            f"DTEND;TZID={tz_name}:{dt_end}",
            f"ORGANIZER;CN=\"{rec.create_uid.name}\":mailto:{rec.create_uid.email}",
            f"ATTENDEE;ROLE=REQ-PARTICIPANT;RSVP=TRUE;CN=\"Participant\":mailto:{attendee_email}",
        ]
        
        # Include full formatted content in ICS description
        ics_description = rec.description or ''
        # Get recipient name and timezone from attendee_email
        recipient_name = 'Participant'
        for target in [rec.guest_partner_id] + list(rec.attendee):
            if target and target.email == attendee_email:
                recipient_name = target.name
                break
        ics_description += '\n' + rec._generate_ics_full_content(recipient_name, tz_name)
        # Escape newlines for ICS format
        ics_description = ics_description.replace('\n', '\\n')
        lines.append(f"DESCRIPTION:{ics_description}")
        
        
        loc_name = ", ".join(rec.room_location_ids.mapped('name')) if rec.room_location_ids else "Virtual"
        if rec.zoom_link:
            lines.append(f"LOCATION:{rec.zoom_link}")
        else:
            lines.append(f"LOCATION:{loc_name}")
        
        lines.append("END:VEVENT")
        lines.append("END:VCALENDAR")
        
        return "\r\n".join(lines)

    def _send_calendar_emails_silent(self):
        """
        Send personalized calendar emails to all attendees (internal + external).
        This is the silent version of create_calendar_web() - returns nothing, just sends emails.
        Used for auto-sending when confirm or generate link buttons are clicked.
        """
        self.ensure_one()
        rec = self
        
        # 1. Build recipient list
        targets = []
        
        # A. Internal Users (Use their Odoo Timezone)
        for user in rec.attendee:
            if user.email:
                targets.append({
                    'email': user.email,
                    'name': user.name,
                    'tz': user.tz or 'UTC',
                    'type': 'user'
                })
        
        # B. Guest Partner
        host_tz = rec.host_user_id.tz or rec.create_uid.tz or 'UTC'
        guest_tz = rec.guest_tz or host_tz
        if rec.guest_partner_id and rec.guest_partner_id.email:
            targets.append({
                'email': rec.guest_partner_id.email,
                'name': rec.guest_partner_id.name,
                'tz': guest_tz,
                'type': 'partner'
            })
        
        # C. Extra Emails (Raw strings) - Use same timezone as guest booking
        if rec.guest_emails:
            extras = [e.strip() for e in re.split(r'[;\n,]+', rec.guest_emails) if e.strip()]
            for e in extras:
                targets.append({
                    'email': e,
                    'name': 'Guest',
                    'tz': guest_tz,
                    'type': 'guest'
                })
        
        if not targets:
            _logger.info(f"No email recipients configured for meeting {rec.id}")
            return
        
        # 2. BATCH PROCESS - Send emails in batches of 50
        sent_count = 0
        BATCH_SIZE = 50
        
        for batch_start in range(0, len(targets), BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, len(targets))
            batch = targets[batch_start:batch_end]
            
            for target in batch:
                try:
                    target_tz = target['tz']
                    
                    # A. Calculate times in THEIR timezone
                    local_times = rec._compute_local_times(target_tz)
                    tz_name = local_times['tz_name']
                    tz_offset_str = local_times['tz_offset_str']
                    formatted_date = local_times['formatted_date']
                    start_str = local_times['start_time_hours']
                    end_str = local_times['end_time_hours']
                    
                    # B. Generate ICS content for this timezone
                    ics_content = self._generate_ics_content_string(
                        rec, local_times, tz_name, tz_offset_str, target['email']
                    )
                    
                    # Create Attachment
                    filename = f"invitation_{rec.id}_{target['type']}.ics"
                    encoded_ics = base64.b64encode(ics_content.encode('utf-8'))
                    
                    attachment = self.env['ir.attachment'].sudo().create({
                        'name': filename,
                        'type': 'binary',
                        'res_model': 'meeting.event',
                        'res_id': rec.id,
                        'datas': encoded_ics,
                        'public': True
                    })
                    
                    # C. Generate Email Body for this recipient (with their times)
                    loc_name = ", ".join(rec.room_location_ids.mapped('name')) if rec.room_location_ids else "Virtual"
                    virtual_link = ""
                    if rec.zoom_link:
                        virtual_link = f"<br/><b>Join Link:</b> <a href='{rec.zoom_link}' target='_blank'>Click Here</a>"
                    
                    # Generate timezone breakdown HTML
                    tz_breakdown = rec._generate_timezone_breakdown_html()
                    
                    email_body = f"""
                    <div style="font-family: sans-serif;">
                        Hi <b>{target['name']}</b>,<br/><br/>
                        <b>{rec.create_uid.name}</b> has invited you to a meeting.<br/><br/>
                        <table border="0" style="background-color: #f9f9f9; padding: 15px; border-radius: 5px; width: 100%; max-width: 600px;">
                            <tbody>
                                <tr><td style="width:100px;"><b>Topic</b></td><td>: {rec.subject}</td></tr>
                                <tr><td><b>Date</b></td><td>: {formatted_date}</td></tr>
                                <tr><td><b>Time</b></td><td>: <span style="font-size: 1.1em; color: #00A09D; font-weight: bold;">{start_str} - {end_str}</span> ({tz_name})</td></tr>
                                <tr><td><b>Location</b></td><td>: {loc_name} {virtual_link}</td></tr>
                            </tbody>
                        </table>
                        <br/>
                        {tz_breakdown}
                        <br/>
                        <p style="color: #666; font-size: 0.9em;">* Attached is the calendar file (.ics) converted to your timezone ({tz_name}).</p>
                    </div>
                    """
                    
                    # D. Send Email
                    mail_values = {
                        'subject': f"Invitation: {rec.subject} @ {start_str} ({tz_name})",
                        'email_from': rec.create_uid.email_formatted,
                        'email_to': target['email'],
                        'body_html': email_body,
                        'attachment_ids': [(4, attachment.id)],
                        'auto_delete': True,
                    }
                    self.env['mail.mail'].sudo().create(mail_values).send()
                    sent_count += 1
                    
                except Exception as e:
                    _logger.error(f"Failed to send email to {target.get('email')}: {str(e)}")
            
            # Commit after every batch
            if (batch_start + BATCH_SIZE) % (BATCH_SIZE * 2) == 0:
                self.env.cr.commit()
        
        _logger.info(f"Sent {sent_count} personalized invitation emails for meeting {rec.id}")

    def create_calendar_web(self):
        """
        Generate ICS calendar file and send PERSONALIZED email invitations to attendees.
        
        POIN 1 & 4: Setiap peserta mendapat email INDIVIDUAL dengan:
        - Waktu sesuai timezone MEREKA
        - File ICS dengan VTIMEZONE disesuaikan ke timezone mereka
        - Subject email menampilkan jam mereka
        
        Also regenerates activity notifications for all attendees with latest meeting info.
        
        Returns:
            Action dictionary to download ICS file
        """
        self.ensure_one()
        rec = self
        
        # 0. Regenerate activities for all attendees (with activity notes containing meeting details)
        _logger.info(f"Regenerating activities for meeting {rec.id}")
        rec._regenerate_all_activities()
        
        # 1. Build recipient list with structure for tracking
        targets = []
        
        # A. Internal Users (Use their Odoo Timezone)
        for user in rec.attendee:
            if user.email:
                targets.append({
                    'email': user.email,
                    'name': user.name,
                    'tz': user.tz or 'UTC',
                    'type': 'user'
                })
        
        # B. Guest Partner
        host_tz = rec.host_user_id.tz or rec.create_uid.tz or 'UTC'
        guest_tz = rec.guest_tz or host_tz
        if rec.guest_partner_id and rec.guest_partner_id.email:
            targets.append({
                'email': rec.guest_partner_id.email,
                'name': rec.guest_partner_id.name,
                'tz': guest_tz,
                'type': 'partner'
            })
        
        # C. Extra Emails (Raw strings) - Use same timezone as guest booking
        if rec.guest_emails:
            extras = [e.strip() for e in re.split(r'[;\n,]+', rec.guest_emails) if e.strip()]
            for e in extras:
                targets.append({
                    'email': e,
                    'name': 'Guest',
                    'tz': guest_tz,
                    'type': 'guest'
                })
        
        # 2. BATCH PROCESS - Send emails in batches of 50 to prevent timeout
        last_attachment_id = False
        sent_count = 0
        BATCH_SIZE = 50
        
        for batch_start in range(0, len(targets), BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, len(targets))
            batch = targets[batch_start:batch_end]
            
            for target in batch:
                try:
                    target_tz = target['tz']
                    
                    # A. Calculate times in THEIR timezone
                    local_times = rec._compute_local_times(target_tz)
                    tz_name = local_times['tz_name']
                    tz_offset_str = local_times['tz_offset_str']
                    formatted_date = local_times['formatted_date']
                    start_str = local_times['start_time_hours']
                    end_str = local_times['end_time_hours']
                    
                    # B. Generate ICS content for this timezone
                    ics_content = self._generate_ics_content_string(
                        rec, local_times, tz_name, tz_offset_str, target['email']
                    )
                    
                    # Create Attachment
                    filename = f"invitation_{rec.id}_{target['type']}.ics"
                    encoded_ics = base64.b64encode(ics_content.encode('utf-8'))
                    
                    attachment = self.env['ir.attachment'].sudo().create({
                        'name': filename,
                        'type': 'binary',
                        'res_model': 'meeting.event',
                        'res_id': rec.id,
                        'datas': encoded_ics,
                        'public': True
                    })
                    last_attachment_id = attachment.id
                    
                    # C. Generate Email Body for this recipient (with their times)
                    loc_name = ", ".join(rec.room_location_ids.mapped('name')) if rec.room_location_ids else "Virtual"
                    virtual_link = ""
                    if rec.zoom_link:
                        virtual_link = f"<br/><b>Join Link:</b> <a href='{rec.zoom_link}' target='_blank'>Click Here</a>"
                    
                    # Generate timezone breakdown HTML
                    tz_breakdown = rec._generate_timezone_breakdown_html()
                    
                    email_body = f"""
                    <div style="font-family: sans-serif;">
                        Hi <b>{target['name']}</b>,<br/><br/>
                        <b>{rec.create_uid.name}</b> has invited you to a meeting.<br/><br/>
                        <table border="0" style="background-color: #f9f9f9; padding: 15px; border-radius: 5px; width: 100%; max-width: 600px;">
                            <tbody>
                                <tr><td style="width:100px;"><b>Topic</b></td><td>: {rec.subject}</td></tr>
                                <tr><td><b>Date</b></td><td>: {formatted_date}</td></tr>
                                <tr><td><b>Time</b></td><td>: <span style="font-size: 1.1em; color: #00A09D; font-weight: bold;">{start_str} - {end_str}</span> ({tz_name})</td></tr>
                                <tr><td><b>Location</b></td><td>: {loc_name} {virtual_link}</td></tr>
                            </tbody>
                        </table>
                        <br/>
                        {tz_breakdown}
                        <br/>
                        <p style="color: #666; font-size: 0.9em;">* Attached is the calendar file (.ics) converted to your timezone ({tz_name}).</p>
                    </div>
                    """
                    
                    # D. Send Email with ICS attachment
                    mail = self.env['mail.mail'].sudo().create({
                        'subject': f"Invitation: {rec.subject} @ {start_str} ({tz_name})",
                        'email_from': rec.create_uid.email_formatted,
                        'email_to': target['email'],
                        'body_html': email_body,
                        'auto_delete': True,
                    })
                    # Explicitly attach ICS file
                    mail.attachment_ids = [(6, 0, [attachment.id])]
                    mail.send()
                    sent_count += 1
                    
                except Exception as e:
                    _logger.error(f"Failed to send email to {target.get('email')}: {str(e)}")
            
            # Commit after every batch to free resources
            if (batch_start + BATCH_SIZE) % (BATCH_SIZE * 2) == 0:
                self.env.cr.commit()
        
        # 3. Log activity
        rec.message_post(body=f"Personalized invitations sent to {sent_count} recipients (with individual timezone conversions).")
        
        # Return download for host (last generated ICS)
        if last_attachment_id:
            return {
                'type': 'ir.actions.act_url',
                'url': f'/web/content/{last_attachment_id}?download=true',
                'target': 'self',
            }

    # ==========================
    # ACTION CANCEL (DELETE ZOOM & RESET FIELDS)
    # ==========================
    def action_cancel(self):
        """
        Cancel meeting event and clean up associated resources.
        
        This action:
        1. Security check (only creator or admin can cancel)
        2. Deletes Zoom meeting from server (if exists)
        3. Posts cancellation message to chatter
        4. Deletes all activity notifications
        5. Cancels all child meeting.rooms records
        6. Resets all virtual meeting fields
        7. Changes state to 'cancel'
        """
        # === SECURITY CHECK FIRST (BEFORE TOUCHING ZOOM) ===
        is_manager = self.env.user.has_group('meeting_rooms.group_meeting_manager')
        for ev in self:
            if ev.create_uid != self.env.user and not is_manager:
                raise UserError(_(
                    f"ACCESS DENIED!\n\n"
                    f"You cannot cancel this meeting.\n"
                    f"Only the creator ({ev.create_uid.name}) or a Meeting Administrator can cancel meetings."
                ))
        # ====================================================
        
        MeetingRooms = self.env['meeting.rooms']
        for ev in self:
            # 1. Delete Zoom Meeting from Server (only after security check passed)
            if ev.zoom_id and ev.virtual_room_id and ev.virtual_room_id.provider == 'zoom':
                ev._logic_delete_zoom_meeting(ev.zoom_id, context_room=ev.virtual_room_id)

            # 2. Post cancellation message
            loc_name = ", ".join(ev.room_location_ids.mapped('name')) or "Virtual"
            msg_body = f"Meeting <b>{ev.subject}</b> from {ev.start_date} to {ev.end_date} in <b>{loc_name}</b> Is Cancelled"
            ev.message_post(body=msg_body)

            # 3. Delete all activities
            existing_activities = self.env['mail.activity'].search([
                ('res_id', '=', ev.id),
                ('res_model', '=', 'meeting.event')
            ])
            existing_activities.unlink()

            # 4. Cancel child meeting.rooms records
            rooms = MeetingRooms.search([('meeting_event_id', '=', ev.id)])
            if rooms:
                rooms.with_context(skip_event_sync=True, skip_booking_check=True, skip_readonly_check=True).write({'state': 'cancel'})
            
            # 5. Cancel event and reset all virtual meeting fields
            ev.write({
                'state': 'cancel',
                'zoom_id': False,
                'zoom_link': False,
                'zoom_start_url': False,
                'zoom_invitation': False,
                'ai_summary': False
            })
        return True

    def action_draft(self):
        """
        Reset meeting event to draft state.
        
        Also resets all associated meeting.rooms records to draft.
        """
        MeetingRooms = self.env['meeting.rooms']
        for ev in self:
            rooms = MeetingRooms.search([('meeting_event_id', '=', ev.id)])
            if rooms:
                rooms.with_context(skip_event_sync=True, skip_booking_check=True, skip_readonly_check=True).write({'state': 'draft'})
            ev.write({'state': 'draft'})
        return True

    # ==========================
    # CRON JOB HANDLER (OPTIMIZED)
    # ==========================
    @api.model
    def _cron_auto_delete_activities(self):
        """
        Scheduled job to delete stale activity notifications.
        
        OPTIMIZATION: Added limit to prevent timeout on large datasets.
        Processes 1000 records per execution to maintain server stability.
        
        This method is called by Odoo cron scheduler (configured in data/cron_job.xml).
        """
        limit_count = 1000  # Limit per run to prevent timeout
        
        # Delete stale activities for meeting.event (parent)
        activities_event = self.env['mail.activity'].search([
            ('res_model', '=', 'meeting.event'),
            ('date_deadline', '<', fields.Date.today())
        ], limit=limit_count)

        # Delete stale activities for meeting.rooms (child)
        activities_rooms = self.env['mail.activity'].search([
            ('res_model', '=', 'meeting.rooms'),
            ('date_deadline', '<', fields.Date.today())
        ], limit=limit_count)

        # Combine results
        all_activities = activities_event + activities_rooms
        count = len(all_activities)

        if count > 0:
            all_activities.unlink()
            _logger.info(f"CRON JOB: Deleted {count} Stale Activities (Limit applied).")
    
    @api.model
    def _cron_delete_old_ics_files(self):
        """
        NEW CRON: Delete .ics attachments older than 3 months to save storage space.
        
        Runs weekly to prevent database bloat from accumulated calendar files.
        Deletes up to 1000 old attachments per execution.
        """
        three_months_ago = datetime.now() - timedelta(days=90)
        
        # Search attachments linked to this module
        attachments = self.env['ir.attachment'].search([
            ('res_model', 'in', ['meeting.event', 'meeting.rooms']),
            ('res_field', '=', 'calendar_file'),
            ('create_date', '<', three_months_ago)
        ], limit=1000)
        
        if attachments:
            count = len(attachments)
            attachments.unlink()
            _logger.info(f"CRON CLEANUP: Deleted {count} old ICS files.")
        else:
            _logger.info("CRON CLEANUP: No old ICS files to delete.")

    # ==========================
    # SMART BUTTON ACTION
    # ==========================
    def open_zoom_link(self):
        """
        Open virtual meeting link in new browser tab.
        
        Automatically prepends 'https://' if protocol is missing.
        
        Returns:
            Action dictionary to open URL in new window
        """
        self.ensure_one()
        # Auto-fix missing HTTPS protocol
        if self.zoom_link and not self.zoom_link.startswith(('http://', 'https://')):
            return {
                'type': 'ir.actions.act_url',
                'url': 'https://' + self.zoom_link,
                'target': 'new',
            }
        
        if self.zoom_link:
            return {
                'type': 'ir.actions.act_url',
                'url': self.zoom_link,
                'target': 'new',
            }