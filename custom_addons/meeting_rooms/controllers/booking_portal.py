# -*- coding: utf-8 -*-
from odoo import http, fields, _
from odoo.http import request
from datetime import datetime, timedelta, time
import pytz

class BookingPortal(http.Controller):

    # =========================================================================
    # 1. HALAMAN KALENDER (PEMILIHAN SLOT)
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
        sg_tz = pytz.timezone('Asia/Singapore') 
        
        # Waktu sekarang di Singapore untuk pembatasan slot
        now_sg = datetime.now(sg_tz)
        dates = []
        
        MeetingEvent = request.env['meeting.event'].sudo()

        # Loop 6 hari ke depan
        for i in range(6): 
            current_date = now_sg.date() + timedelta(days=i)
            day_slots = []
            
            # Loop jam kerja: 09:00 - 17:00 (Waktu Singapore)
            for hour in range(9, 17): 
                # Pastikan menit dan detik di-set ke 0 (Mencegah kelebihan menit)
                start_dt_sg = sg_tz.localize(datetime.combine(current_date, time(hour, 0, 0)))
                
                # Jangan tampilkan jam yang sudah lewat di hari yang sama
                if start_dt_sg < now_sg:
                    continue

                end_dt_sg = start_dt_sg + timedelta(hours=1)
                
                # Konversi ke UTC untuk pengecekan database dan Value URL
                start_dt_utc = start_dt_sg.astimezone(pytz.utc).replace(tzinfo=None)
                end_dt_utc = end_dt_sg.astimezone(pytz.utc).replace(tzinfo=None)

                # Cek apakah host sibuk di jam tersebut
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
        })


    # =========================================================================
    # 2. HALAMAN FORM DETAILS (KONFIRMASI WAKTU)
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
        
        try:
            # 1. Parsing UTC dari Link (Gunakan strip() untuk membersihkan karakter aneh)
            dt_utc = datetime.strptime(time_str.strip(), '%Y-%m-%d %H:%M:%S')
            
            # 2. Konversi Balik ke Singapore buat Ditampilin secara akurat
            utc_zone = pytz.utc
            sg_zone = pytz.timezone('Asia/Singapore')
            
            dt_aware_utc = utc_zone.localize(dt_utc)
            dt_sg = dt_aware_utc.astimezone(sg_zone)
            
            # Formatting untuk tampilan user
            pretty_time_str = dt_sg.strftime('%A, %d %b %Y - %H:%M (Asia/Singapore)')
            
            return request.render('meeting_rooms.portal_booking_form_template', {
                'host': host_user,
                'token': token,
                'time_str': time_str,             # Tetap kirim UTC Murni ke Hidden Input
                'display_time': pretty_time_str,  # Ditampilkan ke Guest
                'default_name': request.env.user.name if not request.env.user._is_public() else '',
                'default_email': request.env.user.email if not request.env.user._is_public() else '',
            })
        except Exception as e:
            return f"Error parsing schedule: {str(e)}"


    # =========================================================================
    # 3. PROSES SUBMIT (DATABASE STORAGE)
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
            # Parsing waktu UTC dari hidden input
            start_dt = datetime.strptime(time_str.strip(), '%Y-%m-%d %H:%M:%S')
            end_dt = start_dt + timedelta(hours=1) # Durasi default 1 jam
        except ValueError:
            return "Format waktu tidak valid."

        host_user = booking_link.user_id

        # Handler Guest Partner
        Partner = request.env['res.partner'].sudo()
        guest_partner = Partner.search([('email', '=', email)], limit=1)
        if not guest_partner:
            guest_partner = Partner.create({'name': name, 'email': email, 'type': 'contact'})
        else:
            guest_partner.write({'name': name})

        # Cek ketersediaan terakhir (Double check jika ada 2 orang submit bersamaan)
        domain = [
            ('start_date', '<', end_dt),
            ('end_date', '>', start_dt),
            ('attendee', 'in', [host_user.id]),
            ('state', '!=', 'cancel')
        ]
        conflict = request.env['meeting.event'].sudo().search(domain, limit=1)
        if conflict:
             return "Maaf, slot waktu ini baru saja dipesan oleh orang lain."

        # Create Event (Status Draft agar Host bisa konfirmasi manual/otomatis)
        new_event = request.env['meeting.event'].sudo().create({
            'subject': final_subject,
            'start_date': start_dt,
            'end_date': end_dt,
            'attendee': [(4, host_user.id)],
            'state': 'draft',
            'guest_partner_id': guest_partner.id,
        })

        # Kirim email ke Guest & Host (Opsional sesuai logic model Anda)
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
                        Thank you, <b>{name}</b>. Your meeting invitation has been sent to <b>{email}</b>.
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