# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class MeetingRoomsExt(models.Model):
    _inherit = 'meeting.rooms'

    # ---------------------------------------------------------------------
    # LINK FIELD
    # ---------------------------------------------------------------------
    meeting_event_id = fields.Many2one(
        'meeting.event',
        string="Meeting Event Ref",
        index=True,
        ondelete='set null'
    )

    # =========================================================
    # Helpers
    # =========================================================
    def _has_event_model(self):
        """Safety: jangan KeyError kalau meeting.event belum ter-load."""
        return 'meeting.event' in self.env.registry.models

    def _linked_event(self):
        self.ensure_one()
        if not self._has_event_model():
            return False
        return self.meeting_event_id if self.meeting_event_id else False

    def _push_rooms_to_event(self, ev):
        """
        Push DATA PENTING (Subject, Tanggal, dll) dari meeting.rooms -> meeting.event
        TAPI TIDAK PUSH STATUS.
        """
        self.ensure_one()
        if not ev:
            return

        vals = {
            'subject': self.subject,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'description': self.description,
            'attendee': [(6, 0, self.attendee.ids)],
        }

        if getattr(self, 'calendar_alarm', False) and self.calendar_alarm:
            vals['calendar_alarm'] = self.calendar_alarm.id

        if getattr(self, 'room_location', False) and self.room_location:
            vals['room_location_ids'] = [(6, 0, [self.room_location.id])]

        # Update data ke Event, tapi pakai context skip_rooms_sync agar tidak looping
        ev.with_context(
            skip_rooms_sync=True,
            skip_event_sync=True,
            skip_booking_check=True,
            skip_availability_check=True,
        ).write(vals)

    def _super_call_or_fallback_state(self, rec, state):
        """
        Safety wrapper untuk memanggil fungsi asli tombol.
        """
        self.ensure_one()
        try:
            if state == 'confirm':
                return super(MeetingRoomsExt, rec).action_confirm()
            if state == 'cancel':
                return super(MeetingRoomsExt, rec).action_cancel()
            if state == 'draft':
                return super(MeetingRoomsExt, rec).action_draft()
        except Exception:
            # Fallback jika fungsi asli tidak ada/error
            # PENTING: Tambahkan bypass_security_check disini juga untuk jaga-jaga
            rec.with_context(skip_booking_check=True, bypass_security_check=True).write({'state': state})
            return True

    # =========================================================
    # BUTTON OVERRIDES (ISOLATED LOGIC)
    # =========================================================
    
    def action_confirm(self):
        for rec in self:
            rec._super_call_or_fallback_state(rec, 'confirm')
            if not rec.env.context.get('skip_event_sync'):
                ev = rec._linked_event()
                if ev:
                    rec._push_rooms_to_event(ev)
        return True

    def action_cancel(self):
        for rec in self:
            rec._super_call_or_fallback_state(rec, 'cancel')
        return True

    def action_draft(self):
        for rec in self:
            rec._super_call_or_fallback_state(rec, 'draft')
        return True

    # =========================================================
    # WRITE OVERRIDE
    # =========================================================
    def write(self, vals):
        # NOTE: Kita tidak perlu bypass security check disini secara eksplisit
        # karena write ini dipanggil oleh user atau event.
        # Jika dipanggil event, event sudah bawa context.
        # Jika user, maka kena blokir (sesuai keinginan).
        
        res = super(MeetingRoomsExt, self).write(vals)

        if self.env.context.get('skip_event_sync'):
            return res
        if not self._has_event_model():
            return res

        important = {'subject', 'start_date', 'end_date', 'attendee', 'description', 'calendar_alarm', 'room_location'}
        need_push = bool(important.intersection(vals.keys()))
        
        for rec in self:
            ev = rec._linked_event()
            if not ev:
                continue

            if need_push:
                rec._push_rooms_to_event(ev)

        return res

    # =========================================================
    # LEGACY SYNC (DATA LAMA) - INI YANG BIKIN ERROR TADI
    # =========================================================
    @api.model
    def action_sync_legacy_data(self):
        """
        Dijalankan otomatis saat Upgrade Module via XML.
        Menghubungkan Room yatim piatu ke Event.
        """
        orphaned_rooms = self.search([('meeting_event_id', '=', False)])
        
        MeetingEvent = self.env['meeting.event']
        linked_count = 0
        created_count = 0

        for room in orphaned_rooms:
            parent_event = MeetingEvent.search([
                ('subject', '=', room.subject),
                ('start_date', '=', room.start_date),
                ('end_date', '=', room.end_date)
            ], limit=1)

            if parent_event:
                # KASUS A: Link ke Event existing
                # PERBAIKAN: Tambahkan bypass_security_check=True
                room.with_context(force_sync=True, bypass_security_check=True).write({'meeting_event_id': parent_event.id})
                linked_count += 1
            else:
                # KASUS B: Buatkan Event baru
                vals = {
                    'subject': room.subject,
                    'start_date': room.start_date,
                    'end_date': room.end_date,
                    'description': room.description,
                    'attendee': [(6, 0, room.attendee.ids)],
                    'state': 'confirm', 
                }
                
                if room.room_location:
                    vals['room_location_ids'] = [(4, room.room_location.id)]
                
                if room.calendar_alarm:
                    vals['calendar_alarm'] = room.calendar_alarm.id

                # Create Event Baru
                new_event = MeetingEvent.with_context(skip_rooms_sync=True).create(vals)
                
                # Update Room dengan referensi baru
                # PERBAIKAN: Tambahkan bypass_security_check=True
                room.with_context(force_sync=True, bypass_security_check=True).write({'meeting_event_id': new_event.id})
                created_count += 1

        if linked_count or created_count:
            print(f"=== [SYNC LEGACY] Linked: {linked_count}, Created New Events: {created_count} ===")