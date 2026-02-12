# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from .constants import ContextKey

class MeetingRoomsExt(models.Model):
    _inherit = 'meeting.rooms'

    # Link field
    # =========================================================================
    # NOTE: Updated to use 'cascade' ondelete to ensure child records deleted
    meeting_event_id = fields.Many2one(
        'meeting.event',
        string="Meeting Event Ref",
        index=True,
        ondelete='cascade' 
    )

    # =========================================================
    # Helper methods
    # =========================================================
    def _has_event_model(self):
        """Safety: prevent KeyError if meeting.event model not yet loaded."""
        return 'meeting.event' in self.env.registry.models

    def _linked_event(self):
        self.ensure_one()
        if not self._has_event_model():
            return False
        return self.meeting_event_id if self.meeting_event_id else False

    def _push_rooms_to_event(self, ev):
        """
        Push important data (subject, dates, etc) from meeting.rooms → meeting.event.
        Do NOT push status (state).
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

        # Update event with context flag to prevent infinite loop
        ev.with_context(**{
            ContextKey.SKIP_ROOMS_SYNC: True,
            ContextKey.SKIP_EVENT_SYNC: True,
            ContextKey.SKIP_BOOKING_CHECK: True,
            ContextKey.SKIP_AVAILABILITY_CHECK: True,
        }).write(vals)

    def _super_call_or_fallback_state(self, rec, state):
        """
        Safety wrapper to call original button functions.
        Fallback: if function not found, directly update state.
        """
        from .constants import ContextKey
        self.ensure_one()
        try:
            if state == 'confirm':
                return super(MeetingRoomsExt, rec).action_confirm()
            if state == 'cancel':
                return super(MeetingRoomsExt, rec).action_cancel()
            if state == 'draft':
                return super(MeetingRoomsExt, rec).action_draft()
        except AttributeError as e:
            # Original function not found - fallback to state write
            import logging
            _logger = logging.getLogger(__name__)
            _logger.warning(f"State transition fallback for state={state}: {str(e)}")
            rec.with_context(**{
                ContextKey.SKIP_BOOKING_CHECK: True,
                ContextKey.SKIP_READONLY_CHECK: True
            }).write({'state': state})
            return True
        except Exception as e:
            # Other unexpected errors - log and re-raise
            import logging
            _logger = logging.getLogger(__name__)
            _logger.error(f"Unexpected error in state transition for state={state}: {str(e)}")
            raise

    # =========================================================
    # BUTTON OVERRIDES (ISOLATED LOGIC)
    # =========================================================
    
    def action_confirm(self):
        for rec in self:
            rec._super_call_or_fallback_state(rec, 'confirm')
            if not rec.env.context.get(ContextKey.SKIP_EVENT_SYNC):
                ev = rec._linked_event()
                if ev:
                    rec._push_rooms_to_event(ev)
        return True

    def action_cancel(self):
        """Cancel meeting room with security check."""
        # === SECURITY CHECK: Allow host, creator (via event), or manager only ===
        from .constants import GroupNames
        is_manager = self.env.user.has_group(GroupNames.MEETING_MANAGER)
        current_user_id = self.env.user.id
        
        for rec in self:
            # Quick allow: manager can cancel anything
            if is_manager:
                continue
            
            # Primary check: Is current user the HOST (direct field in meeting.rooms)?
            if rec.host_user_id and rec.host_user_id.id == current_user_id:
                continue
            
            # Fallback check: Is current user the HOST (from linked event)?
            linked_event = rec._linked_event()
            if linked_event and linked_event.host_user_id and linked_event.host_user_id.id == current_user_id:
                continue
            
            # Secondary check: Is current user the CREATOR of the event (not meeting.rooms)?
            # For bookings, the host is the creator. For direct meetings, whoever created is the creator.
            if linked_event and linked_event.create_uid and linked_event.create_uid.id == current_user_id:
                continue
            
            # DENY: User has no permission
            host_name = (rec.host_user_id.name if rec.host_user_id else 
                        (linked_event.host_user_id.name if linked_event and linked_event.host_user_id else "Unknown"))
            event_creator = (linked_event.create_uid.name if linked_event and linked_event.create_uid else "Unknown")
            
            raise ValidationError(
                f"Access Denied!\n\n"
                f"You cannot cancel this booking.\n"
                f"Only the host ({host_name}), meeting creator ({event_creator}), or a Meeting Administrator can cancel bookings."
            )
        
        # Proceed with cancellation
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
        # NOTE: We don't need to explicitly bypass security check here
        # because this write is called by user or event.
        # If called from event, event already brings context.
        # If called from user, it gets blocked (as intended).
        
        res = super(MeetingRoomsExt, self).write(vals)

        if self.env.context.get(ContextKey.SKIP_EVENT_SYNC):
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
    # Legacy data migration (module upgrade)
    # =========================================================
    @api.model
    def action_sync_legacy_data(self):
        """
        Automatically called when module is upgraded via XML.
        Handles old data overlap to prevent errors during installation.
        """
        # Find meeting.rooms records not linked to any event yet
        orphaned_rooms = self.search([('meeting_event_id', '=', False)])
        
        MeetingEvent = self.env['meeting.event']
        linked_count = 0
        created_count = 0
        skipped_count = 0

        for room in orphaned_rooms:
            # 1. Check if corresponding event already exists?
            parent_event = MeetingEvent.search([
                ('subject', '=', room.subject),
                ('start_date', '=', room.start_date),
                ('end_date', '=', room.end_date)
            ], limit=1)

            # Context flags to prevent automation and errors during sync
            # - mail_activity_automation_skip: Disable Odoo's auto activity
            # - skip_double_booking_check: Bypass constraint during legacy sync
            ctx_sync = {
                'force_sync': True, 
                'skip_readonly_check': True,
                'mail_activity_automation_skip': True, 
                'mail_create_nosubscribe': True,
                'skip_double_booking_check': True # Bypass constraint
            }

            if parent_event:
                # CASE A: Link room to existing event
                room.with_context(ctx_sync).write({'meeting_event_id': parent_event.id})
                linked_count += 1
            else:
                # CASE B: Create new parent event
                # NOTE: Manual check for overlap with other events
                # If severe overlap detected, create event in draft state for safety
                
                # Simple overlap detection logic
                overlap = MeetingEvent.search_count([
                    ('start_date', '<', room.end_date),
                    ('end_date', '>', room.start_date),
                    ('state', '=', 'confirm') # Assume only confirmed events are valid
                ])
                
                state_to_set = 'confirm'
                if overlap > 0:
                    state_to_set = 'draft' # Downgrade to draft if conflict
                
                vals = {
                    'subject': room.subject,
                    'start_date': room.start_date,
                    'end_date': room.end_date,
                    'description': room.description,
                    'attendee': [(6, 0, room.attendee.ids)],
                    'state': state_to_set, 
                }
                
                if room.room_location:
                    vals['room_location_ids'] = [(4, room.room_location.id)]
                
                if getattr(room, 'calendar_alarm', False):
                    vals['calendar_alarm'] = room.calendar_alarm.id

                # Create new event with safe context
                new_event = MeetingEvent.with_context(ctx_sync).create(vals)
                
                # Update room with new reference
                room.with_context(ctx_sync).write({'meeting_event_id': new_event.id})
                
                if state_to_set == 'draft':
                    skipped_count += 1
                else:
                    created_count += 1

        if linked_count or created_count or skipped_count:
            print(f"=== [SYNC LEGACY] Linked: {linked_count}, Created: {created_count}, Overlap(Draft): {skipped_count} ===")