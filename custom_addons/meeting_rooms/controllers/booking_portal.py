# -*- coding: utf-8 -*-
from odoo import http, fields, _
from odoo.http import request
from datetime import datetime, timedelta, time
import pytz
import base64
import re
from werkzeug.utils import redirect
import logging

_logger = logging.getLogger(__name__)

class BookingPortal(http.Controller):

    # =========================================================================
    # 0. Host avatar endpoint
    # =========================================================================
    @http.route('/book/avatar/<string:token>', type='http', auth='public')
    def booking_avatar(self, token):
        link_obj = request.env['meeting.booking.link'].sudo().search([('token', '=', token)], limit=1)
        if not link_obj:
            return request.not_found()
        
        partner = link_obj.user_id.partner_id
        if not partner.image_128:
            return redirect('/web/static/img/placeholder.png')
            
        image_data = base64.b64decode(partner.image_128)
        headers = [
            ('Content-Type', 'image/png'), 
            ('Content-Length', str(len(image_data))),
            ('Cache-Control', 'max-age=3600, public')
        ]
        return request.make_response(image_data, headers)

    # =========================================================================
    # 1. Calendar page (OPTIMIZED: 1 QUERY ONLY - SCALABILITY FIX)
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
        
        # === POIN 3 FIX: USE LINK TIMEZONE, NOT USER TIMEZONE ===
        # This allows one host to have multiple booking links with different timezones
        target_tz_name = link_obj.tz or host_user.tz or 'UTC'
        
        if not target_tz_name:
            return "ERROR: Booking link does not have timezone configured."
        
        try:
            host_tz = pytz.timezone(target_tz_name)
        except:
            return f"ERROR: Invalid timezone '{target_tz_name}'."

        # Setup Time
        now_utc = datetime.now(pytz.utc)
        now_host = now_utc.astimezone(host_tz)
        
        # === QUERY OPTIMIZATION (SCALABILITY FIX) ===
        # Instead of querying search_count in loop (48x per page),
        # we query once upfront and cache results in RAM.
        # Fetch all confirmed meetings for host in 7-day window.
        
        window_start_utc = now_utc.replace(tzinfo=None)
        window_end_utc = (now_utc + timedelta(days=7)).replace(tzinfo=None)
        
        MeetingEvent = request.env['meeting.event'].sudo()
        
        # SINGLE QUERY: Fetch all events in the 7-day window
        existing_events = MeetingEvent.search([
            ('start_date', '<', window_end_utc),
            ('end_date', '>', window_start_utc),
            ('state', '=', 'confirm'),
            ('attendee', 'in', [host_user.id])
        ])
        
        # Cache busy slots in RAM as list of tuples
        # Format: [(start_utc, end_utc), (start_utc, end_utc), ...]
        busy_slots_cache = []
        for ev in existing_events:
            busy_slots_cache.append((ev.start_date, ev.end_date))
        
        # === END OPTIMASI ===
        
        dates = []
        
        # Generate next 6 days
        for i in range(6): 
            current_date_host = now_host.date() + timedelta(days=i)
            day_slots = []
            
            for hour in range(9, 17): 
                # 1. Create Timestamp in LINK TIMEZONE
                slot_naive = datetime.combine(current_date_host, time(hour, 0, 0))
                slot_aware_host = host_tz.localize(slot_naive)
                
                # Skip past times
                if slot_aware_host < now_host:
                    continue

                # 2. Convert to UTC (Naive) for Comparison
                slot_aware_utc = slot_aware_host.astimezone(pytz.utc)
                end_aware_utc = slot_aware_utc + timedelta(hours=1)

                db_start = slot_aware_utc.replace(tzinfo=None)
                db_end = end_aware_utc.replace(tzinfo=None)

                # 3. CHECK FOR CONFLICT IN RAM (Fast & CPU-efficient - No DB query)
                is_busy = False
                for b_start, b_end in busy_slots_cache:
                    # Overlap logic: (StartA < EndB) and (EndA > StartB)
                    if db_start < b_end and db_end > b_start:
                        is_busy = True
                        break
                
                if not is_busy:
                    local_val = slot_naive.strftime('%Y-%m-%d %H:%M:%S')
                    day_slots.append({
                        'time_str': f"{hour:02d}:00", 
                        'val': local_val
                    })

            if day_slots:
                dates.append({
                    'date_str': current_date_host.strftime('%A, %d %b'),
                    'slots': day_slots
                })

        return request.render('meeting_rooms.portal_booking_template', {
            'host': host_user,
            'dates': dates,
            'token': token,
            'tz_name': target_tz_name,
        })

    # =========================================================================
    # 2. Details form 
    # =========================================================================
    @http.route('/booking/details', type='http', auth='public', website=True)
    def booking_details_form(self, token, time_str, **kw):
        link_obj = request.env['meeting.booking.link'].sudo().search([('token', '=', token)], limit=1)
        if not link_obj: return "Token Invalid"
        
        host_user = link_obj.user_id
        
        # === POIN 3 FIX: USE LINK TIMEZONE ===
        target_tz_name = link_obj.tz or host_user.tz or 'UTC'
        
        try:
            # Parse LOCAL string (Link timezone)
            dt_naive = datetime.strptime(time_str.strip(), '%Y-%m-%d %H:%M:%S')
            
            target_tz = pytz.timezone(target_tz_name)
            
            # Make timezone-aware (Local Link Time)
            local_aware = target_tz.localize(dt_naive)
            # Convert to UTC
            utc_aware = local_aware.astimezone(pytz.utc)

            time_link_str = local_aware.strftime('%H:%M')
            time_utc_str = utc_aware.strftime('%H:%M')
            date_str = local_aware.strftime('%A, %d %b %Y')
            
            display_str = f"{date_str} — {time_link_str} ({target_tz_name}) / {time_utc_str} UTC"
            
            return request.render('meeting_rooms.portal_booking_form_template', {
                'host': host_user,
                'token': token,
                'time_str': time_str, 
                'display_time': display_str,
                'default_name': request.env.user.name if not request.env.user._is_public() else '',
                'default_email': request.env.user.email if not request.env.user._is_public() else '',
            })
        except Exception as e:
            return f"Error parsing schedule: {str(e)}"

    # =========================================================================
    # 3. Submit booking (SECURITY: Honeypot + Rate Limiting)
    # =========================================================================
    @http.route('/booking/submit', type='http', auth='public', website=True, csrf=True)
    def booking_submit(self, token, time_str, **kw):
        # --- SECURITY LAYER 1: HONEYPOT (Anti-Bot Detection) ---
        if kw.get('website_url'):
            client_ip = request.httprequest.remote_addr
            _logger.warning(f"SECURITY: Bot detected (Honeypot triggered) from IP {client_ip}")
            return "Error: Invalid Request (Bot Detected)"

        # --- SECURITY LAYER 2: RATE LIMITING (Anti-Spam) ---
        last_submit = request.session.get('last_booking_submit')
        if last_submit:
            last_time = datetime.fromtimestamp(last_submit)
            time_since_last = (datetime.now() - last_time).total_seconds()
            if time_since_last < 60:
                _logger.warning(f"SECURITY: Rate limit exceeded. {60 - int(time_since_last)}s remaining")
                return f"Too many requests. Please wait {60 - int(time_since_last)} seconds before booking again."
        
        request.session['last_booking_submit'] = datetime.now().timestamp()

        # --- MAIN LOGIC ---
        link_obj = request.env['meeting.booking.link'].sudo().search([
            ('token', '=', token),
            ('active', '=', True)
        ], limit=1)
        
        if not link_obj: return "Link Not Found"

        host_user = link_obj.user_id
        
        # === TIMEZONE RETRIEVAL ALREADY CORRECT ===
        target_tz_name = link_obj.tz or host_user.tz or 'UTC'

        # TIMEZONE CONVERSION LOGIC
        try:
            local_dt_naive = datetime.strptime(time_str.strip(), '%Y-%m-%d %H:%M:%S')
            target_tz = pytz.timezone(target_tz_name)
            local_dt_aware = target_tz.localize(local_dt_naive)
            utc_dt_aware = local_dt_aware.astimezone(pytz.utc)
            
            start_dt_db = utc_dt_aware.replace(tzinfo=None)
            end_dt_db = start_dt_db + timedelta(hours=1)
            
            client_ip = request.httprequest.remote_addr
            _logger.info(f"BOOKING SECURED: User '{kw.get('name')}' | IP {client_ip} | Time {start_dt_db} UTC")
            
        except ValueError as e:
            return f"Invalid time format: {e}"

        # Validate Email
        name = kw.get('name', 'Guest')
        email_input = (kw.get('email') or '').strip()
        email_list = [e.strip() for e in re.split(r'[;\n,]+', email_input) if e.strip()]
        if not email_list: return "Email required"

        final_subject = kw.get('subject') or f"Meeting with {name}"

        # Create/Find Partner
        Partner = request.env['res.partner'].sudo()
        guest_partner = Partner.search([('email', '=', email_list[0])], limit=1)
        if not guest_partner:
            guest_partner = Partner.create({
                'name': name, 
                'email': email_list[0], 
                'type': 'contact'
            })

        # Check for Conflict
        domain = [
            ('start_date', '<', end_dt_db),
            ('end_date', '>', start_dt_db),
            ('attendee', 'in', [host_user.id]),
            ('state', '=', 'confirm')
        ]
        if request.env['meeting.event'].sudo().search_count(domain) > 0:
            return "Sorry, this time slot has just been booked."

        # Create Event as HOST user (so host_user is the creator, not public user)
        # This ensures permissions are correct: host = creator of the meeting
        new_event = request.env['meeting.event'].sudo().with_user(host_user).with_context(tz='UTC').create({
            'subject': final_subject,
            'start_date': start_dt_db, 
            'end_date': end_dt_db,     
            'attendee': [(4, host_user.id)],
            'state': 'draft',
            'host_user_id': host_user.id,
            'guest_partner_id': guest_partner.id,
            'guest_emails': ", ".join(email_list),
            'guest_tz': target_tz_name,
        })

        # ===============================================================
        # Note: Using target_tz_name (from booking link), not host_user.tz
        # ===============================================================
        time_host_str = local_dt_aware.strftime('%H:%M')
        time_utc_str = utc_dt_aware.strftime('%H:%M')
        date_str = local_dt_aware.strftime('%A, %d %b %Y')
        
        display_time = f"{date_str} — {time_host_str} ({target_tz_name}) / {time_utc_str} UTC"

        return f"""
            <div style='display:flex; justify-content:center; align-items:center; height:100vh; background-color:#f3f4f6; font-family:sans-serif;'>
                <div style='text-align:center; padding:40px; background:white; border-radius:10px; box-shadow:0 4px 15px rgba(0,0,0,0.1); max-width:550px;'>
                    <div style='color:#00A09D; font-size:60px; margin-bottom:20px;'>✔</div>
                    <h1 style='color:#2c3e50; margin-bottom:15px;'>Thank You for Your Booking!</h1>
                    <p style='color:#555; margin-bottom:25px;'>We have successfully received your meeting request and will send you a confirmation email shortly with all the details.</p>
                    <p style='color:#777; font-size:14px; margin-bottom:20px;'><strong>Meeting scheduled for:</strong><br/>{display_time}</p>
                    <a href='/book/{token}' style='display:inline-block; padding:12px 25px; background-color:#00A09D; color:white; text-decoration:none; border-radius:5px;'>Back to Calendar</a>
                </div>
            </div>
        """