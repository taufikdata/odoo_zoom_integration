from odoo import fields, models, api, _
from datetime import datetime, timedelta, date
from odoo.exceptions import AccessDenied, UserError, ValidationError
import pytz
import subprocess
import base64

# put POSIX 'Etc/*' entries at the end to avoid confusing users - see bug 1086728
_tzs = [(tz, tz) for tz in sorted(pytz.all_timezones, key=lambda tz: tz if not tz.startswith('Etc/') else '_')]
def _tz_get(self):
    return _tzs

class MeetingRoomsLocation(models.Model):
    _name = 'room.location'
    _description = 'Meeting Room Location'

    name = fields.Char("Location")
    active = fields.Boolean("active ?", default=True)
    location_address = fields.Text("Address")
    location_description = fields.Text("Description")
    tz = fields.Selection(_tz_get, string='Timezone', default=lambda self: self._context.get('tz'),
                          help="When printing documents and exporting/importing data, time values are computed according to this timezone.\n"
                               "If the timezone is not set, UTC (Coordinated Universal Time) is used.\n"
                               "Anywhere else, time values are computed according to the time offset of your web client.")
    tz_offset = fields.Char("Offset", compute = '_compute_offset')

    def _compute_offset(self):
        for record in self:
            timezone = record.tz or 'UTC'  # Default to UTC if no timezone is set

            time_zone = pytz.timezone(timezone)
            current_time = datetime.now(pytz.utc).astimezone(time_zone)

            timezone_offset = current_time.utcoffset().total_seconds() / 60

            offset_hours = int(timezone_offset // 60)
            offset_minutes = int(abs(timezone_offset) % 60)

            # Format the offset (e.g., +08:00, -05:30, etc.)
            record.tz_offset = f"{'+' if offset_hours >= 0 else '-'}{abs(offset_hours):02d}{abs(offset_minutes):02d}"


class MeetingRooms(models.Model):
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _name = 'meeting.rooms'
    _description = 'Meeting Rooms Booking'

    name = fields.Char("Name")
    subject = fields.Char("Subject")
    room_location = fields.Many2one("room.location", string="Location", required=True)
    start_date = fields.Datetime("Start", required=True)
    end_date = fields.Datetime("End", required=True)
    attendee = fields.Many2many("res.users", string="Attendee")
    description = fields.Text("Description")
    calendar_alarm = fields.Many2one("calendar.alarm", string="Reminder", required=True)
    state = fields.Selection([('draft', 'Draft'),
                              ('confirm', 'Confirm'),('cancel','Cancelled')], string='Status',tracking=True, copy=False,default='confirm')
    recurrency = fields.Boolean('Recurrent', help="Recurrent Meeting")
    rrule_type = fields.Selection([
        ('daily', 'Daily'),
        ('weekly', 'Weekly')
    ], string='Recurrence', help="Let the event automatically repeat at that interval")
    final_date = fields.Date('Repeat Until')
    action = fields.Boolean("Action")
    email_sent = fields.Boolean("Email Sent?")
    version = fields.Integer("Version", default=1)
    calendar_file = fields.Binary(string="Calendar File")
    
    virtual_room_id = fields.Many2one('virtual.room', string="Virtual Room")
    
    # === HOST INFORMATION (FOR PERMISSION CHECKS) ===
    host_user_id = fields.Many2one('res.users', string="Host User", help="Host/owner of the booking link")

    # === FIELDS FOR MULTI-TIMEZONE DISPLAY ===
    multi_timezone_display = fields.Html(
        related='meeting_event_id.multi_timezone_display', 
        string="Timezone Details", 
        readonly=True
    )
    
    # === COMPUTED FIELDS: DISPLAY DATES IN UTC ONLY ===
    # Note: Base start_date/end_date already shows user's timezone (Odoo native)
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

    # === FIELD BARU: USER VIEW TIME (SERVER-SIDE CONVERSION) ===
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

    # =========================================================================
    # Security functions (access control)
    # =========================================================================
    def _check_readonly_access(self):
        """
        Check if user has permission to create/edit/delete meeting rooms.
        Meeting rooms are auto-created from meeting.event, so direct edit is blocked.
        Internal system operations can bypass this check using 'skip_readonly_check' context.
        """
        if self.env.context.get('skip_readonly_check'):
            return True
            
        # English error message
        raise UserError(_(
            "ACCESS DENIED!\n\n"
            "You cannot create, edit, or delete Bookings manually here.\n"
            "Please go to 'Meeting Events' menu to manage schedules."
        ))

    def _get_display_tz_name(self):
        self.ensure_one()
        event = getattr(self, 'meeting_event_id', False)
        if event and event.host_user_id and event.host_user_id.tz:
            return event.host_user_id.tz
        if self.create_uid and self.create_uid.tz:
            return self.create_uid.tz
        return 'UTC'

    def _convert_utc_to_tz(self, dt, tz_name):
        if not dt:
            return dt
        tz = pytz.timezone(tz_name or 'UTC')
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        return dt.astimezone(tz)

    def _tz_offset_str(self, tz_name, ref_dt=None):
        if not ref_dt:
            ref_dt = fields.Datetime.now()
        local_dt = self._convert_utc_to_tz(ref_dt, tz_name)
        utc_offset = local_dt.utcoffset() or timedelta(0)
        offset_total_seconds = utc_offset.total_seconds()
        offset_hours = int(offset_total_seconds // 3600)
        offset_minutes = int(abs(offset_total_seconds) % 3600 // 60)
        return f"{'+' if offset_hours >= 0 else '-'}{abs(offset_hours):02d}{abs(offset_minutes):02d}"

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
        _logger.info(f"User DB TZ    : {current_user.tz} (Value stored in database)")
        _logger.info(f"Context TZ    : {context_tz} (Value sent by Browser/Session)")
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
        SERVER-SIDE HARDCODING SOLUTION: Calculate time based on the timezone of the currently LOGGED-IN user.
        
        This bypasses browser logic and forces server-side calculations which are guaranteed to be correct.
        This field returns TEXT (String), not Datetime, so the browser cannot change it.
        
        Example Output:
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
            
            # Convert Start Date
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

    def send_email_meeting(self):
        self.ensure_one()
        event = getattr(self, 'meeting_event_id', False)
        if event:
            return event.create_calendar_web()
        for rec in self :
            tz_name = rec._get_display_tz_name()
            start_time = rec._convert_utc_to_tz(rec.start_date, tz_name)
            end_time = rec._convert_utc_to_tz(rec.end_date, tz_name)
            create_time = rec._convert_utc_to_tz(rec.create_date, tz_name)
            write_time = rec._convert_utc_to_tz(rec.write_date, tz_name)
            tz_offset_str = rec._tz_offset_str(tz_name, rec.start_date)
            reminder = int(rec.calendar_alarm.duration) if rec.calendar_alarm.duration else 1
            attendee_str = ''
            for user in rec.attendee :
                attendee_str += f'ATTENDEE;ROLE=REQ-PARTICIPANT;RSVP=TRUE;CN="{user.display_name}":mailto:{user.email}'
                if user != rec.attendee[-1]:
                    attendee_str += '\n'
            icsContent = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//ZContent.net//Zap Calendar 1.0//EN
CALSCALE:GREGORIAN
METHOD:REQUEST

BEGIN:VTIMEZONE
TZID:{tz_name}
X-LIC-LOCATION:${tz_name}
BEGIN:STANDARD
DTSTART:19700101T000000
TZOFFSETFROM:{tz_offset_str}
TZOFFSETTO:{tz_offset_str}
TZNAME:${tz_name}
END:STANDARD
END:VTIMEZONE

BEGIN:VEVENT
UID:{rec.id}
SEQUENCE:{rec.version}
SUMMARY:{rec.subject}
DTSTAMP:{create_time}
LAST-MODIFIED:{write_time}
DTSTART;TZID={tz_name}:{start_time}
DTEND;TZID={tz_name}:{end_time}
LOCATION:{rec.room_location.name}
DESCRIPTION:{rec.description}
ORGANIZER;PARTSTAT=ACCEPTED;CN="{rec.create_uid.display_name}":mailto:{rec.create_uid.email}
{attendee_str}
BEGIN:VALARM
TRIGGER:-PT${reminder}M
ACTION:DISPLAY
DESCRIPTION:Reminder
END:VALARM
END:VEVENT
END:VCALENDAR`;
            """
            filename = f"{rec.subject}.ics"
            with open(filename, 'w') as file:
                file.write(icsContent)

            with open(filename, 'rb') as file:
                attachment_calendar = self.env['ir.attachment'].sudo().search(
                    [('res_model', '=', 'meeting.rooms'), ('type', '=', 'binary'), ('res_field', '=', 'calendar_file'),('res_id', '=', rec.id)])
                if attachment_calendar:
                    attachment_calendar.unlink()
                    attachment = self.env['ir.attachment'].sudo().create({
                        'name': filename,
                        'type': 'binary',
                        'res_model': 'meeting.rooms',
                        'res_field': 'calendar_file',
                        'res_id': rec.id,
                        'res_name': filename,
                        'datas': base64.b64encode(file.read()),
                        'public': True
                    })
                else:
                    attachment = self.env['ir.attachment'].sudo().create({
                        'name': filename,
                        'type': 'binary',
                        'res_model': 'meeting.rooms',
                        'res_field': 'calendar_file',
                        'res_id': rec.id,
                        'res_name': filename,
                        'datas': base64.b64encode(file.read()),
                        'public': True
                    })



    def create_calendar_event(self):
        for rec in self :
            tz_name = rec._get_display_tz_name()
            start_time = rec._convert_utc_to_tz(rec.start_date, tz_name)
            end_time = rec._convert_utc_to_tz(rec.end_date, tz_name)
            start_day = start_time.day
            start_month = start_time.month
            start_year = start_time.year
            start_hour = start_time.hour
            start_minute = start_time.minute
            start_second = start_time.second
            end_day = end_time.day
            end_month = end_time.month
            end_year = end_time.year
            end_hour = end_time.hour
            end_minute = end_time.minute
            end_second = end_time.second
            subject = rec.subject
            reminder = int(rec.calendar_alarm.duration) if rec.calendar_alarm.duration else 1
            description = rec.description if rec.description else None

            attendee = ''
            for user in self.attendee :
                if user.display_name and user.email :
                    attendee += 'make new attendee at beginning of attendees with properties {display name:"%s", email:"%s"}\n' %(user.display_name,user.email)

            applescript = """
        set theStartDate to (current date) 
        set year of theStartDate to %s
        set month of theStartDate to %s
        set day of theStartDate to %s
        set hours of theStartDate to %s
        set minutes of theStartDate to %s
        set seconds of theStartDate to %s
        set theEndDate to (current date) 
        set year of theEndDate to %s
        set month of theEndDate to %s
        set day of theEndDate to %s
        set hours of theEndDate to %s
        set minutes of theEndDate to %s
        set seconds of theEndDate to %s
        
        tell application "Calendar"
        activate
            tell calendar "Home"
                set new_event to make new event at end of events with properties {summary:"%s", start date:theStartDate, end date:theEndDate, location:"%s", description:"%s"}
            end tell
            tell new_event
                %s
            end tell
            tell new_event
                make new sound alarm at end of sound alarms with properties {trigger interval:-%s, sound name:"Sosumi"}
            end tell
        end tell
            """ % (start_year, start_month, start_day, start_hour, start_minute, start_second, end_year, end_month, end_day,
                   end_hour, end_minute, end_second, subject,rec.room_location.name,description,attendee,reminder)

            subprocess.run(['osascript', '-e', applescript])


    def run_calendar(self):
        for rec in self :
            self.create_calendar_event()

    def create_calendar_web(self):
        self.ensure_one()
        event = getattr(self, 'meeting_event_id', False)
        if event:
            return event.create_calendar_web()
        return {
            'name': "Create Calendar",
            'type': 'ir.actions.act_url',
            'url': f"/create-icalendar?id={self.id}",
            'target': 'new',
        }

    def action_confirm(self):
        for rec in self:
            rec.state = 'confirm'
            # Activity notifications centralized in meeting.event model

    def action_cancel(self):
        """Cancel meeting room booking with security check."""
        # === SECURITY CHECK FIRST ===
        is_manager = self.env.user.has_group('meeting_rooms.group_meeting_manager')
        for rec in self:
            if rec.create_uid != self.env.user and not is_manager:
                raise UserError(_(
                    f"ACCESS DENIED!\n\n"
                    f"You cannot cancel this booking.\n"
                    f"Only the creator ({rec.create_uid.name}) or a Meeting Administrator can cancel bookings."
                ))
        # ================================
        
        for rec in self :
            tz_name = rec._get_display_tz_name()
            start_time = rec._convert_utc_to_tz(rec.start_date, tz_name)
            end_time = rec._convert_utc_to_tz(rec.end_date, tz_name)
            rec.activity_feedback(['meeting_rooms.mail_act_meeting_rooms_approval'])
            group = []
            for user in rec.attendee :
                group.append(user.partner_id.id)
            value = {'partner_ids': group,
                     'channel_ids': [],
                     'body': f"Meeting {rec.subject} from {start_time} to {end_time} in {rec.room_location.name} Is Cancelled",
                     'attachment_ids': [],
                     'canned_response_ids': [],
                     'message_type': 'comment',
                     'subtype': 'mail.mt_note'}
            rec.message_post(**value)
            rec.state = 'cancel'

    def action_draft(self):
        self.state = 'draft'

    def unlink(self):
        self._check_readonly_access()
        is_manager = self.env.user.has_group('meeting_rooms.group_meeting_manager')
        if self.create_uid != self.env.user and not is_manager:
            raise UserError(_(f"Only the creator ({self.create_uid.name}) or a Meeting Administrator can delete this record."))
        return super(MeetingRooms, self).unlink()

    @api.constrains('start_date', 'end_date', 'room_location')
    def _check_booking_validity(self):
        """
        Validate meeting room availability to prevent double bookings.
        Checks for time overlaps within the same room location.
        Optimized: Uses domain-based search instead of O(n²) loop.
        """
        if self.env.context.get('skip_double_booking_check'):
            return

        for record in self:
            # Validate end_date > start_date
            if record.end_date <= record.start_date:
                raise ValidationError(_("End date cannot be before or equal to start date."))
            
            # OPTIMIZED: Only search for conflicting bookings in same room
            # (not ALL records like before)
            domain = [
                ('id', '!=', record.id),  # Exclude self
                ('room_location', '=', record.room_location.id),  # Same room ONLY
                ('start_date', '<', record.end_date),  # Time overlap check
                ('end_date', '>', record.start_date),
                ('state', '=', 'confirm'),  # Only confirmed bookings
            ]
            
            conflicts = self.search(domain)  # Get only relevant records (not ALL!)
            
            if conflicts:
                # Get first conflict for error message
                conflict = conflicts[0]
                tz_name = record._get_display_tz_name()
                start_time = record._convert_utc_to_tz(conflict.start_date, tz_name)
                end_time = record._convert_utc_to_tz(conflict.end_date, tz_name)
                
                raise ValidationError(
                    _(f"Room conflict: '{record.room_location.name}' is already booked "
                      f"from {start_time.strftime('%Y-%m-%d %H:%M')} to {end_time.strftime('%Y-%m-%d %H:%M')}. "
                      f"Please choose another time slot.")
                )

    @api.model
    def create(self, vals):
        self._check_readonly_access()

        vals['name'] = vals['subject']
        values = super(MeetingRooms, self).create(vals)
        # Activity notifications are centralized in meeting.event model
        # to prevent duplicate notifications (one from meeting.event, one from meeting.rooms).

        if not self.env.context.get('skip_double_booking_check'):
            tz_name = values._get_display_tz_name()
            start_time = values._convert_utc_to_tz(values.start_date, tz_name)
            end_time = values._convert_utc_to_tz(values.end_date, tz_name)
            formatted_start_time = start_time.strftime('%b %d, %Y')
            start_time_hours = start_time.strftime('%H:%M')
            formatted_end_time = end_time.strftime('%b %d, %Y %H:%M')
            end_time_hours = end_time.strftime('%H:%M')
            duration = end_time - start_time
            meeting_hours, remainder = divmod(duration.total_seconds(), 3600)
            meeting_minutes, meeting_seconds = divmod(remainder, 60)
            meeting_hours_str = ""
            if meeting_hours > 0:
                meeting_hours_str = f"{int(meeting_hours)} hours "

            meeting_minutes_str = ""
            if meeting_minutes > 0:
                meeting_minutes_str = f"{int(meeting_minutes)} minutes"

        if values.recurrency :
            if values.rrule_type == "daily" :
                delta = timedelta(days=1)
                start_date = values.start_date
                end_date = values.end_date
                date_count = values.start_date.date()
                while date_count <= values.final_date :
                    start_date += delta
                    end_date += delta
                    date_count += delta
                    value = {
                        'subject' : values.subject,
                        'name' : values.name,
                        'start_date' : start_date,
                        'end_date' : end_date,
                        'description' : values.description,
                        'calendar_alarm' : values.calendar_alarm.id,
                        'attendee' : values.attendee,
                        'room_location' : values.room_location.id
                    }
                    meeting = self.env['meeting.rooms'].sudo().with_context(skip_readonly_check=True).create(value)

            elif values.rrule_type == "weekly":
                delta = timedelta(days=7)
                start_date = values.start_date
                end_date = values.end_date
                date_count = values.start_date.date()
                while date_count <= values.final_date:
                    start_date += delta
                    end_date += delta
                    date_count += delta
                    value = {
                        'subject': values.subject,
                        'name': values.name,
                        'start_date': start_date,
                        'end_date': end_date,
                        'description': values.description,
                        'calendar_alarm': values.calendar_alarm.id,
                        'attendee': values.attendee,
                        'room_location': values.room_location.id
                    }
                    meeting = self.env['meeting.rooms'].sudo().with_context(skip_readonly_check=True).create(value)
        return values

    def write(self, vals):
        """Override write to enforce readonly access control."""
        # 1. If System/Sudo, Bypass all checks
        if self.env.su:
            return super(MeetingRooms, self).write(vals)

        # 2. Check Readonly Context
        self._check_readonly_access()
        if self.env.context.get('force_sync'):
            return super(MeetingRooms, self).write(vals)

        # 3. Check Manual Permission
        is_manager = self.env.user.has_group('meeting_rooms.group_meeting_manager')
        
        # REVISED: Also check if user is the HOST in the parent event
        is_host = False
        for rec in self:
            if rec.meeting_event_id and rec.meeting_event_id.host_user_id == self.env.user:
                is_host = True
                break

        if self.create_uid != self.env.user and not is_manager and not is_host:
            raise UserError(_(f"Only the creator ({self.create_uid.name}), Host, or Meeting Administrator can edit this record."))
        else:
            return super(MeetingRooms, self).write(vals)