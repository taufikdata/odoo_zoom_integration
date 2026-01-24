from odoo import models, fields, api
from datetime import timedelta, datetime
import pytz
from odoo.exceptions import ValidationError, UserError, AccessDenied
import requests
import json
import base64

# =============================================================================
# 1. MODEL BARU: VIRTUAL ROOM (ZOOM ACCOUNTS)
# =============================================================================
class VirtualRoom(models.Model):
    _name = 'virtual.room'
    _description = 'Virtual Room (Zoom Accounts)'

    name = fields.Char("Account Name", required=True, help="Contoh: Zoom Pro HR, Zoom Pro IT")
    zoom_account_id = fields.Char("Zoom Account ID", required=True)
    zoom_client_id = fields.Char("Zoom Client ID", required=True)
    zoom_client_secret = fields.Char("Zoom Client Secret", required=True)
    
    def action_test_connection(self):
        self.ensure_one()
        try:
            url = "https://zoom.us/oauth/token"
            auth_str = f"{self.zoom_client_id}:{self.zoom_client_secret}"
            b64_auth = base64.b64encode(auth_str.encode()).decode()
            
            headers = {
                "Authorization": f"Basic {b64_auth}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            params = {
                "grant_type": "account_credentials",
                "account_id": self.zoom_account_id
            }
            
            response = requests.post(url, headers=headers, params=params)
            
            if response.status_code == 200:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Connection Successful!',
                        'message': 'Credentials are valid. You can use this account.',
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                raise UserError(f"Connection Failed! Zoom says: {response.text}")
                
        except Exception as e:
            raise UserError(f"Error connecting to Zoom: {str(e)}")

# =============================================================================
# 2. MODEL LAMA: MEETING ROOMS (LEGACY)
# =============================================================================
class MeetingRooms(models.Model):
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _name = 'meeting.rooms'
    
    ### PERBAIKAN 1: AGAR TULISAN "FALSE" HILANG, GANTI JADI JUDUL ###
    _rec_name = 'subject' 
    
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

    def action_confirm(self):
        for rec in self:
            tz_name = rec.room_location.tz if rec.room_location else "Asia/Singapore"
            tz = pytz.timezone(tz_name)
            current_offset = datetime.now(pytz.utc).astimezone(tz).utcoffset()
            offset_hours = current_offset.total_seconds() / 3600
            
            start_time = rec.start_date + timedelta(hours=offset_hours)
            end_time = rec.end_date + timedelta(hours=offset_hours)
            
            formatted_start_date = start_time.strftime('%b %d, %Y')
            start_time_str = start_time.strftime('%H:%M')
            end_time_str = end_time.strftime('%H:%M')
            
            duration_delta = rec.end_date - rec.start_date
            total_seconds = duration_delta.total_seconds()
            hours, remainder = divmod(total_seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            duration_str = f"{int(hours)} hours " if hours > 0 else ""
            duration_str += f"{int(minutes)} minutes" if minutes > 0 else ""

            for user in rec.attendee:
                rec.activity_schedule(
                    'meeting_rooms.mail_act_meeting_rooms_approval',
                    note=f"""
                        Hi <b>{user.name}</b>,<br/><br/>
                        I hope this message finds you well. <b>{rec.create_uid.name}</b> has invited you to the "<b>{rec.subject}</b>" meeting.<br/><br/>
                        <table border="0">
                            <tbody>
                                <tr><td style="width:80px;">Date</td><td>: {formatted_start_date}</td></tr>
                                <tr><td>Time</td><td>: {start_time_str} - {end_time_str} ({tz_name}'s Time)</td></tr>
                                <tr><td>Duration</td><td>: {duration_str}</td></tr>
                                <tr><td>Location</td><td>: {rec.room_location.name}</td></tr>
                            </tbody>
                        </table>
                        <br/>Please prepare accordingly.
                    """,
                    user_id=user.id,
                    date_deadline=rec.start_date.date()
                )
            rec.state = 'confirm'

    def action_cancel(self):
        for rec in self:
            rec.activity_feedback(['meeting_rooms.mail_act_meeting_rooms_approval'])
            rec.message_post(body=f"Meeting {rec.subject} Is Cancelled", message_type='comment', subtype_xmlid='mail.mt_note')
            rec.state = 'cancel'

    def action_draft(self):
        for rec in self:
            rec.state = 'draft'

# =============================================================================
# 3. MODEL TAMBAHAN: ROOM LOCATION
# =============================================================================
class RoomLocation(models.Model):
    _name = 'room.location'
    _description = 'Room Location'

    name = fields.Char("Room Name", required=True)
    location_address = fields.Char("Address")
    location_description = fields.Text("Description")
    active = fields.Boolean("Active", default=True)
    tz = fields.Selection([('Asia/Singapore', 'Asia/Singapore'), ('Asia/Jakarta', 'Asia/Jakarta')], string="Timezone", default='Asia/Singapore')

# =============================================================================
# 4. MODEL BARU: MEETING EVENT (MULTI LOCATION & ZOOM)
# =============================================================================
class MeetingEvent(models.Model):
    _name = 'meeting.event'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Meeting Event (Multi Location)'
    
    ### PERBAIKAN TAMPILAN UNTUK MEETING EVENT JUGA ###
    _rec_name = 'subject'

    subject = fields.Char("Subject", required=True)
    room_location_ids = fields.Many2many('room.location', string="Locations", required=True)
    virtual_room_id = fields.Many2one('virtual.room', string="Virtual Room (Zoom)")
    
    start_date = fields.Datetime("Start", required=True)
    end_date = fields.Datetime("End", required=True)
    attendee = fields.Many2many("res.users", string="Attendee")
    description = fields.Text("Description")
    calendar_alarm = fields.Many2one("calendar.alarm", string="Reminder")
    state = fields.Selection([('draft', 'Draft'),('confirm', 'Confirm'),('cancel', 'Cancelled')], string='Status', default='draft', tracking=True)
    
    recurrency = fields.Boolean('Recurrent')
    rrule_type = fields.Selection([('daily', 'Daily'),('weekly', 'Weekly')], string='Recurrence')
    final_date = fields.Date('Repeat Until')
    
    zoom_link = fields.Char("Zoom Link", readonly=True)
    meeting_summary = fields.Text("Meeting Summary")
    
    version = fields.Integer("Version", default=1)
    calendar_file = fields.Binary(string="Calendar File")

    # --- SATPAM (CONSTRAINS) ---
    @api.constrains('start_date', 'end_date', 'room_location_ids', 'attendee', 'virtual_room_id')
    def _check_availability(self):
        for rec in self:
            if rec.start_date >= rec.end_date:
                raise AccessDenied("Start Date must be earlier than End Date")

            # 1. SATPAM LOKASI FISIK
            clashing_rooms = self.env['meeting.rooms'].search([
                ('room_location', 'in', rec.room_location_ids.ids),
                ('state', '=', 'confirm'),
                ('start_date', '<', rec.end_date),
                ('end_date', '>', rec.start_date)
            ])
            if clashing_rooms:
                room_names = ", ".join(clashing_rooms.mapped('room_location.name'))
                raise AccessDenied(f"ROOM CLASH! The following rooms are busy: {room_names}")

            # 2. SATPAM PESERTA
            for person in rec.attendee:
                busy_schedule = self.env['meeting.rooms'].search([
                    ('attendee', 'in', person.id),
                    ('state', '=', 'confirm'),
                    ('start_date', '<', rec.end_date),
                    ('end_date', '>', rec.start_date)
                ])
                if busy_schedule:
                    raise AccessDenied(f"ATTENDEE BUSY! {person.name} is attending: '{busy_schedule[0].subject}'")

            # 3. SATPAM VIRTUAL ROOM (ZOOM)
            if rec.virtual_room_id:
                clashing_zoom = self.search([
                    ('virtual_room_id', '=', rec.virtual_room_id.id),
                    ('state', '=', 'confirm'),
                    ('id', '!=', rec.id),
                    ('start_date', '<', rec.end_date),
                    ('end_date', '>', rec.start_date)
                ])
                if clashing_zoom:
                    raise AccessDenied(f"ZOOM ACCOUNT BUSY! Account '{rec.virtual_room_id.name}' is in use.")

    # --- ZOOM TOKEN HELPER ---
    def get_zoom_access_token(self, account):
        url = "https://zoom.us/oauth/token"
        auth_str = f"{account.zoom_client_id}:{account.zoom_client_secret}"
        b64_auth = base64.b64encode(auth_str.encode()).decode()

        headers = {
            "Authorization": f"Basic {b64_auth}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        params = {"grant_type": "account_credentials", "account_id": account.zoom_account_id}
        response = requests.post(url, headers=headers, params=params)
        if response.status_code == 200:
            return response.json().get("access_token")
        else:
            raise UserError(f"Failed to get Zoom Token from account {account.name}. Check credentials!")

    # --- ACTION BUTTONS ---
    def action_create_zoom_link(self):
        for rec in self:
            if not rec.virtual_room_id:
                raise UserError("Please select a Virtual Room (Zoom Account) first!")

            access_token = self.get_zoom_access_token(rec.virtual_room_id)
            headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
            start_time_str = rec.start_date.strftime('%Y-%m-%dT%H:%M:%SZ')
            
            payload = {
                "topic": rec.subject,
                "type": 2, 
                "start_time": start_time_str,
                "duration": 60,
                "timezone": "UTC",
                "settings": {"host_video": True, "participant_video": True, "join_before_host": False, "mute_upon_entry": True, "auto_recording": "none"}
            }
            
            response = requests.post("https://api.zoom.us/v2/users/me/meetings", headers=headers, data=json.dumps(payload))
            
            if response.status_code == 201:
                meeting_data = response.json()
                rec.zoom_link = meeting_data.get("join_url")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {'title': 'Success', 'message': f'Zoom Link Created!', 'type': 'success', 'sticky': False}
                }
            else:
                raise UserError(f"Failed to create Zoom meeting. Error: {response.text}")

    def action_confirm(self):
        for rec in self:
            first_loc = rec.room_location_ids[0] if rec.room_location_ids else False
            tz_name = first_loc.tz if first_loc else "Asia/Singapore"
            tz = pytz.timezone(tz_name)
            current_offset = datetime.now(pytz.utc).astimezone(tz).utcoffset()
            offset_hours = current_offset.total_seconds() / 3600
            
            start_time = rec.start_date + timedelta(hours=offset_hours)
            end_time = rec.end_date + timedelta(hours=offset_hours)
            
            formatted_start_date = start_time.strftime('%b %d, %Y')
            start_time_str = start_time.strftime('%H:%M')
            end_time_str = end_time.strftime('%H:%M')
            
            duration_delta = rec.end_date - rec.start_date
            total_seconds = duration_delta.total_seconds()
            hours, remainder = divmod(total_seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            duration_str = f"{int(hours)} hours " if hours > 0 else ""
            duration_str += f"{int(minutes)} minutes" if minutes > 0 else ""
            
            loc_names = ", ".join(rec.room_location_ids.mapped('name'))

            # 1. Activity Notification
            for user in rec.attendee:
                rec.activity_schedule(
                    'meeting_rooms.mail_act_meeting_rooms_approval',
                    note=f"""
                        Hi <b>{user.name}</b>,<br/><br/>
                        I hope this message finds you well. <b>{rec.create_uid.name}</b> has invited you to the "<b>{rec.subject}</b>" meeting.<br/><br/>
                        <table border="0">
                            <tbody>
                                <tr><td style="width:80px;">Date</td><td>: {formatted_start_date}</td></tr>
                                <tr><td>Time</td><td>: {start_time_str} - {end_time_str} ({tz_name}'s Time)</td></tr>
                                <tr><td>Duration</td><td>: {duration_str}</td></tr>
                                <tr><td>Location</td><td>: {loc_names}</td></tr>
                            </tbody>
                        </table>
                        <br/>Please prepare accordingly.
                    """,
                    user_id=user.id,
                    date_deadline=rec.start_date.date()
                )

            # 2. Sinkronisasi ke Modul Lama
            meeting_rooms_obj = self.env['meeting.rooms']
            for location in rec.room_location_ids:
                existing = meeting_rooms_obj.search([
                    ('subject', '=', rec.subject),
                    ('room_location', '=', location.id),
                    ('start_date', '=', rec.start_date),
                    ('state', '!=', 'cancel')
                ])
                if not existing:
                    meeting_rooms_obj.create({
                        ### PERBAIKAN 2: ISI JUGA FIELD 'name' AGAR TIDAK KOSONG ###
                        'name': rec.subject, 
                        'subject': rec.subject,
                        'room_location': location.id,
                        'start_date': rec.start_date,
                        'end_date': rec.end_date,
                        'description': rec.description,
                        'attendee': [(6, 0, rec.attendee.ids)],
                        'calendar_alarm': rec.calendar_alarm.id,
                        'state': 'confirm'
                    })

            rec.state = 'confirm'

    def action_cancel(self):
        meeting_rooms_obj = self.env['meeting.rooms']
        for rec in self:
            rec.activity_feedback(['meeting_rooms.mail_act_meeting_rooms_approval'])
            rec.message_post(body=f"Meeting Cancelled", message_type='comment', subtype_xmlid='mail.mt_note')
            
            # Sinkronisasi Cancel
            linked_bookings = meeting_rooms_obj.search([
                ('subject', '=', rec.subject),
                ('start_date', '=', rec.start_date),
                ('room_location', 'in', rec.room_location_ids.ids),
                ('state', '!=', 'cancel')
            ])
            for booking in linked_bookings:
                booking.action_cancel()

            rec.state = 'cancel'

    def action_draft(self):
        meeting_rooms_obj = self.env['meeting.rooms']
        for rec in self:
            # Hapus data di modul lama agar bersih saat re-confirm
            linked_bookings = meeting_rooms_obj.search([
                ('subject', '=', rec.subject),
                ('start_date', '=', rec.start_date),
                ('room_location', 'in', rec.room_location_ids.ids)
            ])
            linked_bookings.unlink()
            rec.state = 'draft'

    def action_get_meeting_summary(self):
        # Placeholder function
        pass
    
    def action_send_email(self):
        # Placeholder function
        pass