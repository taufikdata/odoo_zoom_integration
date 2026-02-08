# -*- coding: utf-8 -*-
from odoo import http, fields, _
from odoo.http import request
from datetime import datetime, timedelta, time
import pytz
import base64
import re
from werkzeug.utils import redirect
import logging

# Logger khusus untuk debugging
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
            ('Content-Length', len(image_data)),
            ('Cache-Control', 'max-age=3600, public')
        ]
        return request.make_response(image_data, headers)

    # =========================================================================
    # 1. Calendar page 
    # =========================================================================
    @http.route('/book/<string:token>', type='http', auth='public', website=True)
    def booking_calendar(self, token, **kw):
        _logger.info(f"\n\n=== [DEBUG START] OPENING CALENDAR PAGE ({token}) ===")
        
        link_obj = request.env['meeting.booking.link'].sudo().search([
            ('token', '=', token),
            ('active', '=', True)
        ], limit=1)

        if not link_obj:
            _logger.error("Token not found or inactive")
            return request.render('http_routing.404') 

        host_user = link_obj.user_id
        host_tz_name = host_user.tz
        
        _logger.info(f"HOST FOUND: {host_user.name} | TIMEZONE: {host_tz_name}")

        if not host_tz_name:
            return "ERROR: Host user does not have a timezone set."
        
        try:
            host_tz = pytz.timezone(host_tz_name)
        except:
            _logger.error(f"Invalid Timezone: {host_tz_name}")
            return f"ERROR: Invalid timezone '{host_tz_name}'."

        # Current time reference
        now_utc = datetime.now(pytz.utc)
        now_host = now_utc.astimezone(host_tz)
        
        _logger.info(f"NOW (UTC): {now_utc}")
        _logger.info(f"NOW (HOST): {now_host}")
        
        dates = []
        MeetingEvent = request.env['meeting.event'].sudo()

        # Generate next 6 days
        for i in range(6): 
            current_date_host = now_host.date() + timedelta(days=i)
            day_slots = []
            
            for hour in range(9, 17): 
                # 1. Create Timestamp in HOST TIMEZONE (e.g. 09:00 Europe/Brussels)
                slot_naive = datetime.combine(current_date_host, time(hour, 0, 0))
                slot_aware_host = host_tz.localize(slot_naive)
                
                # Skip past times
                if slot_aware_host < now_host:
                    continue

                # 2. Calculate UTC equivalent for DB check
                slot_aware_utc = slot_aware_host.astimezone(pytz.utc)
                end_aware_utc = slot_aware_utc + timedelta(hours=1)

                db_start = slot_aware_utc.replace(tzinfo=None)
                db_end = end_aware_utc.replace(tzinfo=None)

                # Check Availability
                domain = [
                    ('start_date', '<', db_end),
                    ('end_date', '>', db_start),
                    ('state', '=', 'confirm'),
                    ('attendee', 'in', [host_user.id])
                ]
                count_busy = MeetingEvent.search_count(domain)

                if count_busy == 0:
                # SEND LOCAL (HOST) TIME TO URL
                # Later in submit, we'll convert back based on Host TZ
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

        _logger.info("=== [DEBUG END] CALENDAR RENDERED ===\n")
        return request.render('meeting_rooms_2.portal_booking_template', {
            'host': host_user,
            'dates': dates,
            'token': token,
            'tz_name': host_tz_name,
        })

    # =========================================================================
    # 2. Details form 
    # =========================================================================
    @http.route('/booking/details', type='http', auth='public', website=True)
    def booking_details_form(self, token, time_str, **kw):
        link_obj = request.env['meeting.booking.link'].sudo().search([('token', '=', token)], limit=1)
        if not link_obj: return "Token Invalid"
        
        host_user = link_obj.user_id
        
        try:
            # Display logic only
            dt_naive = datetime.strptime(time_str.strip(), '%Y-%m-%d %H:%M:%S')
            host_tz_name = host_user.tz or 'UTC'
            pretty_time_str = f"{dt_naive.strftime('%A, %d %b %Y - %H:%M')} ({host_tz_name})"
            
            return request.render('meeting_rooms_2.portal_booking_form_template', {
                'host': host_user,
                'token': token,
                'time_str': time_str, 
                'display_time': pretty_time_str,
                'default_name': request.env.user.name if not request.env.user._is_public() else '',
                'default_email': request.env.user.email if not request.env.user._is_public() else '',
            })
        except Exception as e:
            return f"Error: {str(e)}"

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

        _logger.info(f"\n\n=== [DEBUG START] SUBMITTING BOOKING (SECURITY ENABLED) ===")
        _logger.info(f"RECEIVED TIME STRING: {time_str}")

        link_obj = request.env['meeting.booking.link'].sudo().search([
            ('token', '=', token),
            ('active', '=', True)
        ], limit=1)
        
        if not link_obj: return "Link Not Found"

        host_user = link_obj.user_id
        _logger.info(f"HOST: {host_user.name} | TZ: {host_user.tz}")

        if not host_user.tz:
            return "Host Timezone missing."

        # === TIMEZONE DIAGNOSIS ===
        try:
            # 1. Parse time string (Assumed to be HOST LOCAL TIME)
            # Example: "2026-02-06 09:00:00"
            local_naive = datetime.strptime(time_str.strip(), '%Y-%m-%d %H:%M:%S')
            _logger.info(f"STEP 1 - PARSED RAW: {local_naive}")
            
            # 2. Add Host Timezone
            host_tz = pytz.timezone(host_user.tz)
            local_aware = host_tz.localize(local_naive)
            _logger.info(f"STEP 2 - HOST AWARE: {local_aware}")
            
            # 3. Convert to UTC (This is what goes to DB)
            utc_aware = local_aware.astimezone(pytz.utc)
            _logger.info(f"STEP 3 - CONVERTED TO UTC: {utc_aware}")
            
            # 4. Remove timezone info so Odoo accepts it (Naive UTC)
            start_dt_db = utc_aware.replace(tzinfo=None)
            end_dt_db = start_dt_db + timedelta(hours=1)
            _logger.info(f"STEP 4 - FINAL DB VALUE (NAIVE UTC): {start_dt_db}")
            
        except ValueError as e:
            _logger.error(f"TIME PARSING ERROR: {e}")
            return f"Invalid time format: {e}"

        # Validasi Email dll
        name = kw.get('name', 'Guest')
        email_input = (kw.get('email') or '').strip()
        email_list = [e.strip() for e in re.split(r'[;\n,]+', email_input) if e.strip()]
        if not email_list: return "Email required"

        final_subject = kw.get('subject') or f"Meeting with {name}"

        # Create/Find Partner
        Partner = request.env['res.partner'].sudo()
        guest_partner = Partner.search([('email', '=', email_list[0])], limit=1)
        if not guest_partner:
            guest_partner = Partner.create({'name': name, 'email': email_list[0], 'type': 'contact'})

        # Check Conflict
        domain = [
            ('start_date', '<', end_dt_db),
            ('end_date', '>', start_dt_db),
            ('attendee', 'in', [host_user.id]),
            ('state', '=', 'confirm')
        ]
        if request.env['meeting.event'].sudo().search_count(domain) > 0:
             _logger.warning("CONFLICT DETECTED")
             return "Slot already booked."

        # === CREATE EVENT ===
        _logger.info("CREATING RECORD IN ODOO...")
        # Important: with_context(tz='UTC') prevents Odoo from shifting time again
        new_event = request.env['meeting.event'].sudo().with_context(tz='UTC').create({
            'subject': final_subject,
            'start_date': start_dt_db, 
            'end_date': end_dt_db,     
            'attendee': [(4, host_user.id)],
            'state': 'draft',
            'host_user_id': host_user.id,
            'guest_partner_id': guest_partner.id,
            'guest_emails': ", ".join(email_list),
        })
        _logger.info(f"RECORD CREATED ID: {new_event.id}")
        _logger.info("=== [DEBUG END] SUBMIT COMPLETE (SECURITY PASSED) ===\n")

        # Success Page
        display_time = local_naive.strftime('%A, %d %b %H:%M') + f" ({host_user.tz})"

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