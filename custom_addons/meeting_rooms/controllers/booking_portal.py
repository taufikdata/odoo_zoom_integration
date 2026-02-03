# -*- coding: utf-8 -*-
from odoo import http, fields, _
from odoo.http import request
from datetime import datetime, timedelta, time
import pytz
import base64  

class BookingPortal(http.Controller):

    # =========================================================================
    # 0. AVATAR HOST (BYPASS SECURITY)
    # =========================================================================
    @http.route('/book/avatar/<string:token>', type='http', auth='public')
    def booking_avatar(self, token):
        # 1. Check Token
        link_obj = request.env['meeting.booking.link'].sudo().search([('token', '=', token)], limit=1)
        
        if not link_obj:
            return request.not_found()
            
        # 2. Get Image
        partner = link_obj.user_id.partner_id
        if not partner.image_128:
            return request.redirect('/web/static/img/placeholder.png')
            
        # 3. Decode & Return
        image_data = base64.b64decode(partner.image_128)
        headers = [
            ('Content-Type', 'image/png'), 
            ('Content-Length', len(image_data)),
            ('Cache-Control', 'max-age=3600, public')
        ]
        return request.make_response(image_data, headers)

    # =========================================================================
    # 1. CALENDAR PAGE (SLOT SELECTION)
    # =========================================================================
    @http.route('/book/<string:token>', type='http', auth='public', website=True)
    def booking_calendar(self, token, **kw):
        link_obj = request.env['meeting.booking.link'].sudo().search([
            ('token', '=', token),
            ('active', '=', True)
        ], limit=1)

        if not link_obj:
            return request.render('http_routing.404') 

        host_user = link_obj.user_id
        
        # REVISION: Use Host Timezone, not hardcoded Singapore
        host_tz_name = host_user.tz or 'UTC'
        try:
            host_tz = pytz.timezone(host_tz_name)
        except:
            host_tz = pytz.utc # Fallback

        now_host = datetime.now(host_tz)
        dates = []
        
        MeetingEvent = request.env['meeting.event'].sudo()

        # Generate slots for next 6 days
        for i in range(6): 
            current_date = now_host.date() + timedelta(days=i)
            day_slots = []
            
            # Slot: 9 AM to 5 PM (Host Time)
            for hour in range(9, 17): 
                start_dt_host = host_tz.localize(datetime.combine(current_date, time(hour, 0, 0)))
                
                # Skip past time
                if start_dt_host < now_host:
                    continue

                end_dt_host = start_dt_host + timedelta(hours=1)
                
                # Convert to UTC for Database Query
                start_dt_utc = start_dt_host.astimezone(pytz.utc).replace(tzinfo=None)
                end_dt_utc = end_dt_host.astimezone(pytz.utc).replace(tzinfo=None)

                # Check Availability
                domain = [
                    ('start_date', '<', end_dt_utc),
                    ('end_date', '>', start_dt_utc),
                    ('state', '=', 'confirm'),
                    ('attendee', 'in', [host_user.id])
                ]
                count_busy = MeetingEvent.search_count(domain)

                if count_busy == 0:
                    day_slots.append({
                        'time_str': f"{hour:02d}:00", 
                        'val': start_dt_utc.strftime('%Y-%m-%d %H:%M:%S') 
                    })

            if day_slots:
                dates.append({
                    'date_str': current_date.strftime('%A, %d %b'),
                    'slots': day_slots
                })

        return request.render('meeting_rooms.portal_booking_template', {
            'host': host_user,
            'dates': dates,
            'token': token,
            'tz_name': host_tz_name, # Pass timezone for UI header
        })

    # =========================================================================
    # 2. DETAILS FORM (CONFIRM TIME)
    # =========================================================================
    @http.route('/booking/details', type='http', auth='public', website=True)
    def booking_details_form(self, token, time_str, **kw):
        link_obj = request.env['meeting.booking.link'].sudo().search([
            ('token', '=', token),
            ('active', '=', True)
        ], limit=1)

        if not link_obj:
            return "Token Invalid or Expired"
        
        host_user = link_obj.user_id
        host_tz_name = host_user.tz or 'UTC'
        
        try:
            # Parse UTC time from URL
            dt_utc = datetime.strptime(time_str.strip(), '%Y-%m-%d %H:%M:%S')
            
            utc_zone = pytz.utc
            host_zone = pytz.timezone(host_tz_name)
            
            # Convert to Host Timezone for Display
            dt_aware_utc = utc_zone.localize(dt_utc)
            dt_host = dt_aware_utc.astimezone(host_zone)
            
            pretty_time_str = dt_host.strftime(f'%A, %d %b %Y - %H:%M ({host_tz_name})')
            
            return request.render('meeting_rooms.portal_booking_form_template', {
                'host': host_user,
                'token': token,
                'time_str': time_str,
                'display_time': pretty_time_str,
                'default_name': request.env.user.name if not request.env.user._is_public() else '',
                'default_email': request.env.user.email if not request.env.user._is_public() else '',
            })
        except Exception as e:
            return f"Error parsing schedule: {str(e)}"

    # =========================================================================
    # 3. SUBMIT (CREATE EVENT)
    # =========================================================================
    @http.route('/booking/submit', type='http', auth='public', website=True, csrf=True)
    def booking_submit(self, token, time_str, **kw):
        booking_link = request.env['meeting.booking.link'].sudo().search([
            ('token', '=', token),
            ('active', '=', True)
        ], limit=1)
        
        if not booking_link:
            return "Link Not Found"

        name = kw.get('name', 'Guest')
        email = kw.get('email')
        subject_input = kw.get('subject')

        final_subject = subject_input if (subject_input and subject_input.strip()) else f"Meeting with {name}"

        try:
            start_dt = datetime.strptime(time_str.strip(), '%Y-%m-%d %H:%M:%S')
            end_dt = start_dt + timedelta(hours=1) 
        except ValueError:
            return "Invalid time format."

        host_user = booking_link.user_id

        # Handle Guest Partner
        Partner = request.env['res.partner'].sudo()
        guest_partner = Partner.search([('email', '=', email)], limit=1)
        if not guest_partner:
            guest_partner = Partner.create({'name': name, 'email': email, 'type': 'contact'})
        else:
            # Update name if existing
            guest_partner.write({'name': name})

        # Double Check Conflict
        domain = [
            ('start_date', '<', end_dt),
            ('end_date', '>', start_dt),
            ('attendee', 'in', [host_user.id]),
            ('state', '!=', 'cancel')
        ]
        conflict = request.env['meeting.event'].sudo().search(domain, limit=1)
        if conflict:
             return "Sorry, this time slot has just been booked by someone else."

        # Create Event
        new_event = request.env['meeting.event'].sudo().create({
            'subject': final_subject,
            'start_date': start_dt,
            'end_date': end_dt,
            'attendee': [(4, host_user.id)],
            'state': 'draft',
            'guest_partner_id': guest_partner.id,
        })

        # Trigger Optional Invite Logic
        try:
            if hasattr(new_event, 'action_send_invite_to_guest'):
                new_event.action_send_invite_to_guest(email)
        except:
            pass

        return f"""
            <div style='display:flex; justify-content:center; align-items:center; height:100vh; background-color:#f3f4f6; font-family:sans-serif;'>
                <div style='text-align:center; padding:40px; background:white; border-radius:10px; box-shadow:0 4px 15px rgba(0,0,0,0.1); max-width:550px;'>
                    <div style='color:#00A09D; font-size:60px; margin-bottom:20px;'>✔</div>
                    <h1 style='color:#2c3e50; margin-bottom:15px;'>Booking Confirmed!</h1>
                    
                    <p style='color:#555; font-size:16px; line-height:1.5;'>
                        Thank you, <b>{name}</b>. A meeting invitation has been sent to <b>{email}</b>. 
                        <br/>Please check your inbox or spam folder.
                    </p>
                    
                    <div style='background-color:#e3f2fd; padding:15px; border-radius:5px; margin:25px 0; color:#0d47a1;'>
                        Host: <b>{host_user.name}</b>
                    </div>
                    <a href='/book/{token}' style='display:inline-block; padding:12px 25px; background-color:#00A09D; color:white; text-decoration:none; border-radius:5px; font-weight:bold;'>
                        Close / Book Another Slot
                    </a>
                </div>
            </div>
        """