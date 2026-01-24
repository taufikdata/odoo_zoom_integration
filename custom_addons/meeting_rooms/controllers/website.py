# -*- coding: utf-8 -*-
from datetime import datetime,date,timedelta
import json
from werkzeug.utils import redirect
from odoo import http
from odoo.http import request
import pytz
import base64


class MeetingRoomsWebsite(http.Controller):
    @http.route('/create-icalendar', auth='user', website=True)
    def create_icalendar(self, **kw):
        meeting_id = kw.get('id')
        meeting = request.env['meeting.rooms'].sudo().browse(int(meeting_id))
        attendee = []
        tz = pytz.timezone(meeting.room_location.tz or "Asia/Singapore")
        current_offset = datetime.now(pytz.utc).astimezone(tz).utcoffset()
        offset_hours = current_offset.total_seconds() / 3600
        start_time = meeting.start_date + timedelta(hours=offset_hours)
        end_time = meeting.end_date + timedelta(hours=offset_hours)
        create_time = meeting.create_date + timedelta(hours=offset_hours)
        write_time = meeting.write_date + timedelta(hours=offset_hours)
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
            'write_date' : write_time

        }
        return request.render("meeting_rooms.meeting_rooms_html", vals)

    @http.route('/add-icalendar-file', type='http', auth='user', website=True, csrf=False)
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
        tz = pytz.timezone(record.room_location.tz or "Asia/Singapore")
        current_offset = datetime.now(pytz.utc).astimezone(tz).utcoffset()
        offset_hours = current_offset.total_seconds() / 3600
        start_time = record.start_date + timedelta(hours=offset_hours)
        end_time = record.end_date + timedelta(hours=offset_hours)
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
        recipients = []
        recipients.append(record.create_uid.email)
        for user in record.attendee:
            recipients.append(user.email)
        recipients_email = ",".join(recipients)
        email_body = f"""
            Hi <b>Team</b>,<br/><br/>
            I hope this message finds you well. <b>{record.create_uid.name}</b> has invited you to the "{record.name}" meeting<br/><br/>
            <table border="0">
                <tbody>
                    <tr>
                        <td style="width:80px;">Date</td>
                        <td>: {formatted_start_time}</td>
                    </tr>
                    <tr>
                        <td>Time</td>
                        <td>: {start_time_hours} - {end_time_hours} ({record.room_location.tz}'s Time)</td>
                    </tr>
                    <tr>
                        <td>Duration</td>
                        <td>: {meeting_hours_str}{meeting_minutes_str}</td>
                    </tr>
                    <tr>
                        <td>Location</td>
                        <td>: {record.room_location.name}</td>
                    </tr>
                </tbody>
            </table>
            <br/>
            To accept or decline this invitation, click the attachment below.<br/><br/>
            """
        email = request.env['mail.mail'].sudo().create({
            'subject': record.subject,
            'email_from': 'odoo-erp@tripper.com',
            'email_to': recipients_email,
            'body_html': email_body

        })
        email.attachment_ids = attachment
        email.send()
        log = None
        if email.state == "sent":
            log = f"""
                    <b>Email Sent</b> <br/>
                    id : {email.id} <br/>
                    subject : {email.subject} <br/>
                    email to : {recipients_email} <br/>
                    body : {email.body_html} 

                """
        elif email.state == "exception":
            log = f"Email {email.id} Delivery Failed"
        else:
            log = f"Email Delivery {email.state}"
        record.message_post(body=log)
        data = {'url': attachment.local_url}
        return json.dumps(data)
