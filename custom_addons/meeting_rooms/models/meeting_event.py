# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import datetime, timedelta
import pytz
import base64
import logging
import requests
from requests.auth import HTTPBasicAuth
import urllib.parse
import json

_logger = logging.getLogger(__name__)

# Helper untuk Timezone
_tzs = [(tz, tz) for tz in sorted(pytz.all_timezones, key=lambda tz: tz if not tz.startswith('Etc/') else '_')]
def _tz_get(self):
    return _tzs

class MeetingEvent(models.Model):
    _name = 'meeting.event'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Meeting Event (Master)'
    _rec_name = 'subject'

    # ==========================================================
    # 0. NEW FIELDS: UTC DISPLAY
    # ==========================================================
    start_date_utc_str = fields.Char("Start (UTC)", compute='_compute_utc_display')
    end_date_utc_str = fields.Char("End (UTC)", compute='_compute_utc_display')

    @api.depends('start_date', 'end_date')
    def _compute_utc_display(self):
        for rec in self:
            if rec.start_date:
                rec.start_date_utc_str = rec.start_date.strftime("%Y-%m-%d %H:%M:%S UTC")
            else:
                rec.start_date_utc_str = ""
            
            if rec.end_date:
                rec.end_date_utc_str = rec.end_date.strftime("%Y-%m-%d %H:%M:%S UTC")
            else:
                rec.end_date_utc_str = ""

    # ==========================================================
    # AUTO-ADD HOST TO ATTENDEE
    # ==========================================================
    @api.model
    def create(self, vals):
        res = super(MeetingEvent, self).create(vals)
        if res.create_uid.id not in res.attendee.ids:
            res.write({
                'attendee': [(4, res.create_uid.id)] 
            })
        return res

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

    guest_partner_id = fields.Many2one(
        'res.partner', 
        string="External Guest", 
        help="Guest data from booking portal"
    )

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

    # ==========================================================
    # LOGIC: REGENERATE ACTIVITY
    # ==========================================================
    def _regenerate_all_activities(self):
        self.ensure_one()
        ev = self

        if self.env.context.get('mail_activity_automation_skip'):
            return

        old_activities = self.env['mail.activity'].search([
            ('res_id', '=', ev.id),
            ('res_model', '=', 'meeting.event')
        ])
        old_activities.unlink()

        loc = ev.room_location_ids[0] if ev.room_location_ids else False
        tz_name = loc.tz if loc and loc.tz else "Asia/Singapore"
        loc_name = ", ".join(ev.room_location_ids.mapped('name'))
        
        tz = pytz.timezone(tz_name)
        current_offset = datetime.now(pytz.utc).astimezone(tz).utcoffset()
        offset_hours = current_offset.total_seconds() / 3600

        start_time = ev.start_date + timedelta(hours=offset_hours)
        end_time = ev.end_date + timedelta(hours=offset_hours)

        formatted_start_time = start_time.strftime('%b %d, %Y')
        start_time_hours = start_time.strftime('%H:%M')
        end_time_hours = end_time.strftime('%H:%M')
        
        duration = end_time - start_time
        meeting_hours, remainder = divmod(duration.total_seconds(), 3600)
        meeting_minutes, meeting_seconds = divmod(remainder, 60)
        meeting_hours_str = f"{int(meeting_hours)} hours " if meeting_hours > 0 else ""
        meeting_minutes_str = f"{int(meeting_minutes)} minutes" if meeting_minutes > 0 else ""

        virtual_room_info = ""
        if ev.zoom_link:
                virtual_room_info = f"<br/><br/><b>Online Meeting:</b> <a href='{ev.zoom_link}' target='_blank'>Click to Join</a>"
        elif ev.virtual_room_id:
            virtual_room_info = f"<br/>(Virtual Room: {ev.virtual_room_id.name})"

        for user in ev.attendee:
            ev.activity_schedule(
                'meeting_rooms.mail_act_meeting_rooms_approval',
                user_id=user.id,
                date_deadline=start_time.date(),
                note=f"""
                    Hi <b>{user.name}</b>,<br/><br/>
                    I hope this message finds you well. <b>{ev.create_uid.name}</b> has invited you to the "{ev.subject}" meeting<br/><br/>
                    <table border="0">
                        <tbody>
                            <tr>
                                <td style="width:80px;">Date</td>
                                <td>: {formatted_start_time}</td>
                            </tr>
                            <tr>
                                <td>Time</td>
                                <td>: {start_time_hours} - {end_time_hours} ({tz_name})</td>
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
                    <br/>
                """
            )

    # ==========================
    # OVERRIDE UNLINK (DELETE PERMANEN)
    # ==========================
    def unlink(self):
        """
        Ensure Zoom meeting is deleted from server upon record deletion.
        """
        for rec in self:
            if rec.zoom_id and rec.virtual_room_id and rec.virtual_room_id.provider == 'zoom':
                try:
                    # Pass the current virtual room to ensure credentials are found
                    rec._logic_delete_zoom_meeting(rec.zoom_id, context_room=rec.virtual_room_id)
                except Exception as e:
                    _logger.warning(f"Failed to delete Zoom on Unlink: {str(e)}")
        return super(MeetingEvent, self).unlink()

    # ==========================
    # WRITE / EDIT LOGIC (SAFE TRANSACTION + CONTEXT AWARE DELETE)
    # ==========================
    def write(self, vals):
        reschedule_fields = ['start_date', 'end_date', 'virtual_room_id']
        is_rescheduling = any(f in vals for f in reschedule_fields)

        # 1. STORE OLD DATA (ID & ROOM) BEFORE WRITE
        # We need the OLD Virtual Room to get the correct credentials for deletion
        zoom_data_to_delete = {}
        
        if is_rescheduling:
            for rec in self:
                if rec.zoom_id and rec.virtual_room_id and rec.virtual_room_id.provider == 'zoom':
                    # Store ID and the Record Object of the Virtual Room
                    zoom_data_to_delete[rec.id] = {
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
        res = super(MeetingEvent, self).write(vals)

        # 3. IF SUCCESS, DELETE ZOOM USING OLD CREDENTIALS
        if is_rescheduling:
            for rec in self:
                old_data = zoom_data_to_delete.get(rec.id)
                if old_data:
                    # Pass the OLD room record to the delete logic
                    rec._logic_delete_zoom_meeting(old_data['id'], context_room=old_data['room'])
            
            for ev in self:
                if ev.state == 'confirm':
                    ev.message_post(body="<b>Schedule Changed.</b> Old meeting link has been deleted. Please click 'Generate Meeting Link' again.")

        # 4. Sync Rooms (Updates timestamps, freeing old slots)
        for ev in self:
            if not self.env.context.get('skip_rooms_sync'):
                ev._sync_rooms_from_event()

            if ev.state == 'confirm' and is_update_needed:
                ev._regenerate_all_activities()
                        
        return res

    # ==========================
    # ACTION CONFIRM
    # ==========================
    def action_confirm(self):
        for ev in self:
            ev._regenerate_all_activities()
            ev.write({'state': 'confirm'})
            ev.with_context(skip_booking_check=True)._sync_rooms_from_event()
        return True

    # ==========================================================
    # VIRTUAL ROOM ACTIONS & HELPERS
    # ==========================================================
    
    def _get_zoom_supported_timezone(self):
        user_tz = self.env.user.tz or 'Asia/Singapore'
        mapping = {
            'Asia/Makassar': 'Asia/Singapore', 
            'Asia/Ujung_Pandang': 'Asia/Singapore', 
            'Asia/Jakarta': 'Asia/Bangkok', 
            'Asia/Pontianak': 'Asia/Bangkok', 
            'Asia/Jayapura': 'Asia/Tokyo',
        }
        return mapping.get(user_tz, user_tz)

    def _logic_delete_zoom_meeting(self, meeting_id, context_room=None):
        """
        Deletes meeting from Zoom.
        Args:
            meeting_id: Zoom ID to delete
            context_room: Optional 'virtual.room' record. 
                          If provided, uses this room's creds. 
                          If None, uses self.virtual_room_id (current).
        """
        try:
            if not meeting_id.isdigit(): 
                return 
            
            url = f"https://api.zoom.us/v2/meetings/{meeting_id}"
            # Pass context_room to header generator
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
        self.ensure_one()
        if not self.virtual_room_id:
            raise UserError(_("Please select a Virtual Room first."))
        
        provider = getattr(self.virtual_room_id, 'provider', 'zoom')
        
        if provider == 'zoom':
            self._logic_generate_zoom()
        elif provider == 'google_meet':
            self._logic_generate_google_meet()
        elif provider == 'teams':
            self._logic_generate_teams()
        else:
            self._logic_generate_manual_link()

    # MODIFIED: Accepts optional context_room
    def _get_zoom_credentials(self, context_room=None):
        room = context_room or self.virtual_room_id
        if not room:
             raise UserError(_("Virtual Room configuration missing."))
             
        account_id = room.zoom_account_id
        client_id = room.zoom_client_id
        client_secret = room.zoom_client_secret

        if not account_id or not client_id or not client_secret:
            raise UserError(_("Zoom Credentials (Account/Client/Secret) missing for room %s.") % room.name)    
        return account_id, client_id, client_secret

    # MODIFIED: Accepts optional context_room
    def _get_zoom_access_token(self, context_room=None):
        account_id, client_id, client_secret = self._get_zoom_credentials(context_room)
        url = f"https://zoom.us/oauth/token?grant_type=account_credentials&account_id={account_id}"
        try:
            response = requests.post(url, auth=HTTPBasicAuth(client_id, client_secret), timeout=30)
            response.raise_for_status()
            return response.json()['access_token']
        except Exception as e:
            _logger.error("Zoom Auth Error: %s", e)
            raise UserError(_("Zoom connection failed: %s") % e)

    # MODIFIED: Accepts optional context_room
    def _get_zoom_headers(self, context_room=None):
        token = self._get_zoom_access_token(context_room)
        return {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}

    def _logic_generate_zoom(self):
        if self.zoom_id:
            raise UserError(_("Meeting Link already exists!"))

        duration_seconds = (self.end_date - self.start_date).total_seconds()
        duration_minutes = int(duration_seconds / 60)

        zoom_tz = self._get_zoom_supported_timezone()

        url = "https://api.zoom.us/v2/users/me/meetings"
        headers = self._get_zoom_headers() # Uses current self.virtual_room_id
        
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

    def _logic_generate_google_meet(self):
        static_link = getattr(self.virtual_room_id, 'static_link', False) 
        if not static_link:
            raise UserError(_("No static Google Meet link defined in Virtual Room master."))

        if static_link and not static_link.startswith(('http://', 'https://')):
            static_link = 'https://' + static_link

        self.write({
            'zoom_id': 'Google Meet', 
            'zoom_link': static_link,
            'zoom_start_url': static_link,
        })
        
        self._generate_invitation_text("Google Meet", static_link)
        self.message_post(body=f"Google Meet Link Attached: <a href='{static_link}' target='_blank'>{static_link}</a>")

    def _get_teams_token(self):
        tenant_id = self.virtual_room_id.zoom_account_id
        client_id = self.virtual_room_id.zoom_client_id
        client_secret = self.virtual_room_id.zoom_client_secret

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
        if self.zoom_id:
            raise UserError(_("Meeting Link already exists!"))

        token = self._get_teams_token()
        host_email = self.virtual_room_id.email or self.env.user.email
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
        text = (
            f"Topic: {self.subject}\n"
            f"Time: {self.start_date} (UTC)\n" # Base UTC
        )
        if tz_info:
             text += f"Timezone Reference: {tz_info}\n"

        text += f"\nJoin {provider_name}\n{url}\n\n"
        
        if mid and mid != 'Google Meet' and mid != 'Microsoft Teams':
            text += f"Meeting ID: {mid}\n"
        if pwd:
            text += f"Passcode: {pwd}"
        self.write({'zoom_invitation': text})

    def action_get_ai_summary(self):
        self.ensure_one()
        provider = getattr(self.virtual_room_id, 'provider', 'zoom')
        if provider != 'zoom':
            raise UserError(_("AI Summary only available for Zoom."))

        if not self.zoom_id:
            raise UserError(_("No Meeting ID found."))
        
        new_summary = self._logic_fetch_formatted_summary(self.zoom_id)
        if not new_summary:
            raise UserError(_("Failed to fetch summary. Meeting might not have AI Summary enabled or is not finished yet."))

        header_style = "border-top: 2px solid #00A09D; margin-top: 20px; padding-top: 10px; color: #00A09D;"
        divider = f"<div style='{header_style}'><h3>✨ Meeting AI Summary Result</h3></div>"
        self.write({'ai_summary': divider + new_summary})

    def _logic_fetch_formatted_summary(self, mid):
        content = self._try_fetch_summary(mid)
        if not content:
            uuid = self._find_past_meeting_uuid(mid)
            if uuid:
                encoded_uuid = urllib.parse.quote(urllib.parse.quote(uuid, safe=''), safe='')
                content = self._try_fetch_summary(encoded_uuid)
        return content

    def _try_fetch_summary(self, mid):
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
        url = f"https://api.zoom.us/v2/past_meetings/{mid}/instances"
        try:
            res = requests.get(url, headers=self._get_zoom_headers(), timeout=30)
            if res.status_code == 200 and res.json().get('meetings'):
                return res.json()['meetings'][-1].get('uuid')
        except Exception:
            return False
        return False

    def _get_alarm_id(self):
        self.ensure_one()
        if self.calendar_alarm:
            return self.calendar_alarm.id
        alarm = self.env['calendar.alarm'].search([], limit=1)
        return alarm.id if alarm else False

    def _sync_rooms_from_event(self):
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
                    # Update Existing Booking (Shift Time)
                    by_loc[loc.id].with_context(skip_event_sync=True, skip_booking_check=True, bypass_security_check=True).write(vals)
                    keep_ids.append(by_loc[loc.id].id)
                else:
                    new_b = MeetingRooms.with_context(skip_event_sync=True, skip_booking_check=True, bypass_security_check=True).create(vals)
                    keep_ids.append(new_b.id)

            leftovers = existing.filtered(lambda r: r.id not in keep_ids)
            if leftovers:
                leftovers.with_context(skip_event_sync=True, skip_booking_check=True, bypass_security_check=True).write({'state': 'cancel'})

    # =========================================================
    # CONSTRAINTS (ENGLISH TRANSLATION)
    # =========================================================
    @api.constrains('start_date', 'end_date', 'room_location_ids', 'virtual_room_id', 'attendee', 'state')
    def _check_double_booking(self):
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
                    raise ValidationError(
                        f"LOCATION CLASH!\n"
                        f"Room {', '.join(clashed_rooms)} is already booked for meeting '{conflict_loc.subject}'."
                    )

            if ev.virtual_room_id:
                domain_virtual = base_domain + [('virtual_room_id', '=', ev.virtual_room_id.id)]
                conflict_virtual = self.search(domain_virtual, limit=1)
                if conflict_virtual:
                    raise ValidationError(
                        f"VIRTUAL ROOM CLASH!\n"
                        f"Virtual Account '{ev.virtual_room_id.name}' is already used for meeting '{conflict_virtual.subject}'."
                    )

            if ev.attendee:
                domain_user = base_domain + [('attendee', 'in', ev.attendee.ids)]
                conflict_user = self.search(domain_user, limit=1)
                if conflict_user:
                    busy_people = set(ev.attendee.mapped('name')) & set(conflict_user.attendee.mapped('name'))
                    if busy_people:
                        raise ValidationError(
                            f"ATTENDEE CLASH!\n"
                            f"The following people: {', '.join(busy_people)} "
                            f"already have another meeting ('{conflict_user.subject}')."
                        )

    # ==========================
    # ICS / CALENDAR GENERATION
    # ==========================
    def create_calendar_web(self):
        self.ensure_one()
        rec = self
        
        loc = rec.room_location_ids[0] if rec.room_location_ids else False
        tz_name = loc.tz if loc and loc.tz else "Asia/Singapore"
        loc_name = ", ".join(rec.room_location_ids.mapped('name'))
        
        tz = pytz.timezone(tz_name)
        current_offset = datetime.now(pytz.utc).astimezone(tz).utcoffset()
        offset_hours = current_offset.total_seconds() / 3600

        start_time = rec.start_date + timedelta(hours=offset_hours)
        end_time = rec.end_date + timedelta(hours=offset_hours)
        create_time = rec.create_date + timedelta(hours=offset_hours)
        
        formatted_start_time = start_time.strftime('%b %d, %Y')
        start_time_hours = start_time.strftime('%H:%M')
        end_time_hours = end_time.strftime('%H:%M')
        
        timezone_offset = datetime.now(pytz.utc).astimezone(tz).utcoffset().total_seconds() / 60
        off_h = int(timezone_offset // 60)
        off_m = int(abs(timezone_offset) % 60)
        tz_offset_str = f"{'+' if off_h >= 0 else '-'}{abs(off_h):02d}{abs(off_m):02d}"

        raw_desc = rec.description or ''
        description_text = raw_desc.replace('\n', '\\n')
        
        display_location = loc_name
        if rec.zoom_link:
            display_location += " (Online Meeting Available)"
            description_text += f"\\n\\nJoin Link: {rec.zoom_link}"
            if rec.zoom_id and rec.zoom_id != 'Google Meet' and rec.zoom_id != 'Microsoft Teams':
                description_text += f"\\nMeeting ID: {rec.zoom_id}"
        elif rec.virtual_room_id:
            display_location += f" (Virtual: {rec.virtual_room_id.name})"

        lines = []
        lines.append("BEGIN:VCALENDAR")
        lines.append("VERSION:2.0")
        lines.append("PRODID:-//Odoo Meeting Rooms//EN")
        lines.append("CALSCALE:GREGORIAN")
        lines.append("METHOD:REQUEST")
        
        lines.append("BEGIN:VTIMEZONE")
        lines.append(f"TZID:{tz_name}")
        lines.append(f"X-LIC-LOCATION:{tz_name}")
        lines.append("BEGIN:STANDARD")
        lines.append("DTSTART:19700101T000000")
        lines.append(f"TZOFFSETFROM:{tz_offset_str}")
        lines.append(f"TZOFFSETTO:{tz_offset_str}")
        lines.append(f"TZNAME:{tz_name}")
        lines.append("END:STANDARD")
        lines.append("END:VTIMEZONE")
        
        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:meeting_event_{rec.id}")
        lines.append(f"SEQUENCE:{rec.version}")
        lines.append(f"SUMMARY:{rec.subject}")
        lines.append(f"DTSTAMP:{create_time.strftime('%Y%m%dT%H%M%S')}")
        lines.append(f"DTSTART;TZID={tz_name}:{start_time.strftime('%Y%m%dT%H%M%S')}")
        lines.append(f"DTEND;TZID={tz_name}:{end_time.strftime('%Y%m%dT%H%M%S')}")
        lines.append(f"LOCATION:{display_location}")
        lines.append(f"DESCRIPTION:{description_text}")
        lines.append(f'ORGANIZER;PARTSTAT=ACCEPTED;CN="{rec.create_uid.display_name}":mailto:{rec.create_uid.email}')
        
        for user in rec.attendee:
            if user.email:
                lines.append(f'ATTENDEE;ROLE=REQ-PARTICIPANT;RSVP=TRUE;CN="{user.display_name}":mailto:{user.email}')
        
        if rec.guest_partner_id and rec.guest_partner_id.email:
             lines.append(f'ATTENDEE;ROLE=REQ-PARTICIPANT;RSVP=TRUE;CN="{rec.guest_partner_id.name}":mailto:{rec.guest_partner_id.email}')

        reminder = int(rec.calendar_alarm.duration) if rec.calendar_alarm and rec.calendar_alarm.duration else 15
        lines.append("BEGIN:VALARM")
        lines.append(f"TRIGGER:-PT{reminder}M")
        lines.append("ACTION:DISPLAY")
        lines.append("DESCRIPTION:Reminder")
        lines.append("END:VALARM")
        
        lines.append("END:VEVENT")
        lines.append("END:VCALENDAR")

        ics_content = "\r\n".join(lines)
        
        filename = f"{rec.subject}.ics"
        encoded_ics = base64.b64encode(ics_content.encode('utf-8'))
        
        Attachment = self.env['ir.attachment'].sudo()
        existing_att = Attachment.search([
            ('res_model', '=', 'meeting.event'),
            ('res_field', '=', 'calendar_file'),
            ('res_id', '=', rec.id)
        ])
        if existing_att:
            existing_att.unlink()
            
        attachment = Attachment.create({
            'name': filename,
            'type': 'binary',
            'res_model': 'meeting.event',
            'res_field': 'calendar_file',
            'res_id': rec.id,
            'datas': encoded_ics,
            'public': True
        })

        recipients = [rec.create_uid.email] 
        for user in rec.attendee:
            if user.email:
                recipients.append(user.email)
        
        if rec.guest_partner_id and rec.guest_partner_id.email:
            recipients.append(rec.guest_partner_id.email)

        recipients_email = ",".join(filter(None, list(set(recipients))))

        virtual_room_info = ""
        if rec.zoom_link:
             virtual_room_info = f"<br/><br/><b>Online Meeting:</b> <a href='{rec.zoom_link}' target='_blank'>Click to Join</a>"
        elif rec.virtual_room_id:
            virtual_room_info = f"<br/>(Virtual Room: {rec.virtual_room_id.name})"

        if recipients_email:
            email_body = f"""
            <div style="font-family: sans-serif;">
                Hi Team & Guest,<br/><br/>
                <b>{rec.create_uid.name}</b> has invited you to the "{rec.subject}" meeting<br/><br/>
                <table border="0" style="background-color: #f9f9f9; padding: 10px; border-radius: 5px;">
                    <tbody>
                        <tr><td style="width:80px;"><b>Date</b></td><td>: {formatted_start_time}</td></tr>
                        <tr><td><b>Time</b></td><td>: {start_time_hours} - {end_time_hours} ({tz_name})</td></tr>
                        <tr><td><b>Location</b></td><td>: {loc_name} {virtual_room_info}</td></tr>
                    </tbody>
                </table>
                <br/>
                Please <b>download the attachment</b> to save this to your calendar.<br/><br/>
            </div>
            """
            
            mail_values = {
                'subject': f"Invitation: {rec.subject}",
                'email_from': rec.create_uid.email_formatted,
                'email_to': recipients_email,
                'body_html': email_body,
                'attachment_ids': [(4, attachment.id)]
            }
            mail = self.env['mail.mail'].sudo().create(mail_values)
            mail.send()
            
            rec.message_post(body=f"Email Invitation sent to: {recipients_email}")

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    # ==========================
    # ACTION CANCEL (DELETE ZOOM & RESET FIELDS)
    # ==========================
    def action_cancel(self):
        MeetingRooms = self.env['meeting.rooms']
        for ev in self:
            # 1. Delete Zoom (Use helper with current context room)
            if ev.zoom_id and ev.virtual_room_id and ev.virtual_room_id.provider == 'zoom':
                ev._logic_delete_zoom_meeting(ev.zoom_id, context_room=ev.virtual_room_id)

            # 2. Custom Log
            loc_name = ", ".join(ev.room_location_ids.mapped('name')) or "Virtual"
            msg_body = f"Meeting <b>{ev.subject}</b> from {ev.start_date} to {ev.end_date} in <b>{loc_name}</b> Is Cancelled"
            ev.message_post(body=msg_body)

            # 3. Wipe Activities
            existing_activities = self.env['mail.activity'].search([
                ('res_id', '=', ev.id),
                ('res_model', '=', 'meeting.event')
            ])
            existing_activities.unlink()

            # 4. Cancel Child Rooms
            rooms = MeetingRooms.search([('meeting_event_id', '=', ev.id)])
            if rooms:
                rooms.with_context(skip_event_sync=True, skip_booking_check=True, bypass_security_check=True).write({'state': 'cancel'})
            
            # 5. Cancel Self & Reset
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
        MeetingRooms = self.env['meeting.rooms']
        for ev in self:
            rooms = MeetingRooms.search([('meeting_event_id', '=', ev.id)])
            if rooms:
                rooms.with_context(skip_event_sync=True, skip_booking_check=True, bypass_security_check=True).write({'state': 'draft'})
            ev.write({'state': 'draft'})
        return True

    # ==========================
    # CRON JOB HANDLER
    # ==========================
    @api.model
    def _cron_auto_delete_activities(self):
        activities_event = self.env['mail.activity'].search([
            ('res_model', '=', 'meeting.event'),
            ('date_deadline', '<', fields.Date.today())
        ])

        activities_rooms = self.env['mail.activity'].search([
            ('res_model', '=', 'meeting.rooms'),
            ('date_deadline', '<', fields.Date.today())
        ])

        all_activities = activities_event + activities_rooms
        count = len(all_activities)

        if count > 0:
            all_activities.unlink()
            _logger.info(f"CRON JOB: SUCCESSFULLY DELETED {count} Stale Activities.")
        else:
            _logger.info("CRON JOB: No stale activities found.")

    # ==========================
    # SMART BUTTON ACTION
    # ==========================
    def open_zoom_link(self):
        self.ensure_one()
        # AUTO FIX MISSING HTTPS
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