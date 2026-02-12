# -*- coding: utf-8 -*-
from datetime import datetime,date,timedelta
import json
from werkzeug.utils import redirect
from odoo import http
from odoo.http import request
import pytz
import base64


class MeetingRoomsWebsite(http.Controller):
    def _get_host_tz_name(self, meeting):
        event = getattr(meeting, 'meeting_event_id', False)
        if event and event.host_user_id and event.host_user_id.tz:
            return event.host_user_id.tz
        if meeting.create_uid and meeting.create_uid.tz:
            return meeting.create_uid.tz
        return 'UTC'

    def _convert_utc_to_tz(self, dt, tz_name):
        if not dt:
            return dt
        tz = pytz.timezone(tz_name or 'UTC')
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        return dt.astimezone(tz)

    @http.route('/create-icalendar', auth='user', website=True)
    def create_icalendar(self, **kw):
        meeting_id = kw.get('id')
        meeting = request.env['meeting.rooms'].sudo().browse(int(meeting_id))
        attendee = []
        host_tz_name = self._get_host_tz_name(meeting)
        start_time = self._convert_utc_to_tz(meeting.start_date, host_tz_name)
        end_time = self._convert_utc_to_tz(meeting.end_date, host_tz_name)
        create_time = self._convert_utc_to_tz(meeting.create_date, host_tz_name)
        write_time = self._convert_utc_to_tz(meeting.write_date, host_tz_name)
        for user in meeting.attendee :
            if user.display_name and user.email :
                attendee.append({
                    "name" : user.display_name,"email" : user.email
                })
        vals = {
            'docs' : meeting,
            'attendee' : attendee,
            'start_date' : start_time,
            'end_date' : end_time,
            'create_date' : create_time,
            'write_date' : write_time,
            'host_tz_name': host_tz_name,

        }
        return request.render("meeting_rooms.meeting_rooms_html", vals)

    @http.route('/add-icalendar-file', type='http', auth='user', website=True, csrf=True)
    def add_calendar_file(self, **kw):
        file = kw.get("calendar")
        file_name = kw.get("calendar_name")
        meeting_id = int(kw.get("meeting_id"))
        files = base64.b64encode(file.read())
        attachment = None
        attachment_calendar = request.env['ir.attachment'].sudo().search(
            [('res_model', '=', 'meeting.rooms'), ('type', '=', 'binary'), ('res_field', '=', 'calendar_file'),
             ('res_id', '=', meeting_id)])
        if attachment_calendar:
            attachment_calendar.unlink()
            attachment = request.env['ir.attachment'].sudo().create({
                'name': file_name,
                'type': 'binary',
                'res_model': 'meeting.rooms',
                'res_field': 'calendar_file',
                'res_id': meeting_id,
                'res_name': file_name,
                'datas': files,
                'public': True
            })
        else:
            attachment = request.env['ir.attachment'].sudo().create({
                'name': file_name,
                'type': 'binary',
                'res_model': 'meeting.rooms',
                'res_field': 'calendar_file',
                'res_id': meeting_id,
                'res_name': file_name,
                'datas': files,
                'public': True
            })
        record = request.env['meeting.rooms'].sudo().browse(meeting_id)
        host_tz_name = self._get_host_tz_name(record)
        start_time = self._convert_utc_to_tz(record.start_date, host_tz_name)
        end_time = self._convert_utc_to_tz(record.end_date, host_tz_name)
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
        company_email = (record.company_id.email or request.env.company.email or request.env.user.email or '').strip()
        email_from = company_email if company_email else request.env.user.email
        
        # Get all recipients
        all_recipients = [record.create_uid] + list(record.attendee)
        
        # Send personalized email to each attendee
        for recipient in all_recipients:
            # Get recipient's timezone
            recipient_tz = recipient.tz if recipient.tz else 'UTC'
            recipient_start = self._convert_utc_to_tz(record.start_date, recipient_tz)
            recipient_end = self._convert_utc_to_tz(record.end_date, recipient_tz)
            recipient_start_date = recipient_start.strftime('%b %d, %Y')
            recipient_start_time = recipient_start.strftime('%H:%M')
            recipient_end_time = recipient_end.strftime('%H:%M')
            
            # UTC times (absolute reference)
            utc_tz = pytz.utc
            utc_start = pytz.utc.localize(record.start_date) if record.start_date.tzinfo is None else record.start_date.astimezone(utc_tz)
            utc_end = pytz.utc.localize(record.end_date) if record.end_date.tzinfo is None else record.end_date.astimezone(utc_tz)
            utc_start_str = utc_start.strftime('%Y-%m-%d %H:%M:%S')
            utc_end_str = utc_end.strftime('%Y-%m-%d %H:%M:%S')
            
            # Build timezone breakdown table
            tz_breakdown = "<table style=\"width:100%; font-size:13px; color:#444; border:1px solid #ddd; background-color:#f9f9f9; margin-top:15px;\">"
            tz_breakdown += "<tr style=\"background-color:#e8e8e8;\"><th style=\"padding:8px; text-align:left;\">Location</th><th style=\"padding:8px; text-align:left;\">Local Time</th></tr>"
            
            # Add room locations
            if record.room_location:
                room_tz = record.room_location.tz if hasattr(record.room_location, 'tz') and record.room_location.tz else host_tz_name
                room_start = self._convert_utc_to_tz(record.start_date, room_tz)
                room_end = self._convert_utc_to_tz(record.end_date, room_tz)
                room_start_time = room_start.strftime('%H:%M')
                room_end_time = room_end.strftime('%H:%M')
                tz_breakdown += f"<tr><td style=\"padding:8px; border-bottom:1px solid #ddd;\">🏢 {record.room_location.name}</td><td style=\"padding:8px; border-bottom:1px solid #ddd;\"><b>{room_start_time} - {room_end_time}</b> <span style=\"color:#888; font-size:11px;\">({room_tz})</span></td></tr>"
            
            # Add virtual room if exists
            event = getattr(record, 'meeting_event_id', False)
            if event and (event.zoom_link or event.virtual_room_id):
                virtual_tz = event.host_user_id.tz if event.host_user_id and event.host_user_id.tz else host_tz_name
                virtual_start = self._convert_utc_to_tz(record.start_date, virtual_tz)
                virtual_end = self._convert_utc_to_tz(record.end_date, virtual_tz)
                virtual_start_time = virtual_start.strftime('%H:%M')
                virtual_end_time = virtual_end.strftime('%H:%M')
                provider_name = "Virtual Room"
                if event.virtual_room_id:
                    provider_name = event.virtual_room_id.provider.replace('_', ' ').title() if event.virtual_room_id.provider else "Virtual Room"
                tz_breakdown += f"<tr><td style=\"padding:8px; border-bottom:1px solid #ddd;\">🎥 {provider_name} (Host)</td><td style=\"padding:8px; border-bottom:1px solid #ddd;\"><b>{virtual_start_time} - {virtual_end_time}</b> <span style=\"color:#888; font-size:11px;\">({virtual_tz})</span></td></tr>"
            
            tz_breakdown += "</table>"
            
            # Build email body with personalized greeting
            email_body = f"""
            <div style="font-family: Arial, sans-serif; color: #333;">
                <p>Hi <b>{recipient.name}</b>,<br/><br/>
                I hope this message finds you well. <b>{record.create_uid.name}</b> has invited you to the <b>"{record.name}"</b> meeting.</p>
                
                <h3 style="color: #2c3e50; margin-top: 20px; margin-bottom: 10px;">Schedule Details (in your timezone <b>{recipient_tz}</b>):</h3>
                <table border="0" style="margin-bottom: 15px;">
                    <tbody>
                        <tr>
                            <td style="width:100px; font-weight: bold;">Date</td>
                            <td>: {recipient_start_date}</td>
                        </tr>
                        <tr>
                            <td style="font-weight: bold;">Time</td>
                            <td>: {recipient_start_time} - {recipient_end_time} ({recipient_tz})</td>
                        </tr>
                        <tr>
                            <td style="font-weight: bold;">Time (UTC)</td>
                            <td>: {utc_start_str} - {utc_end_str}</td>
                        </tr>
                        <tr>
                            <td style="font-weight: bold;">Duration</td>
                            <td>: {meeting_hours_str}{meeting_minutes_str}</td>
                        </tr>
                        <tr>
                            <td style="font-weight: bold;">Location</td>
                            <td>: {record.room_location.name if record.room_location else 'Virtual Meeting'}</td>
                        </tr>
                        {f'<tr><td style="font-weight: bold;"></td><td>(Virtual Room: {event.virtual_room_id.name})</td></tr>' if event and event.virtual_room_id else ''}
                    </tbody>
                </table>
                
                <h3 style="color: #2c3e50; margin-top: 20px; margin-bottom: 10px;">Timezone Breakdown:</h3>
                {tz_breakdown}
                
                <p style="margin-top: 20px; color: #666;">
                To accept or decline this invitation, please use the calendar file attachment below.<br/><br/>
                Best regards,<br/>
                Meeting Rooms System
                </p>
            </div>
            """
            
            email = request.env['mail.mail'].sudo().create({
                'subject': record.subject,
                'email_from': email_from,
                'email_to': recipient.email,
                'body_html': email_body
            })
            email.attachment_ids = attachment
            email.send()
            
            # Log email sending result
            if email.state == "sent":
                log = f"<b>Email Sent to {recipient.name} ({recipient.email})</b>"
            elif email.state == "exception":
                log = f"Email to {recipient.name} ({recipient.email}) - Delivery Failed"
            else:
                log = f"Email to {recipient.name} ({recipient.email}) - {email.state}"
            record.message_post(body=log)
        data = {'url': attachment.local_url}
        return json.dumps(data)
