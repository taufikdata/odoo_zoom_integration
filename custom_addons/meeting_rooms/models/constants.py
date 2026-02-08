# -*- coding: utf-8 -*-
"""
Context Constants - Centralized magic strings
Avoid hardcoding context keys throughout codebase
"""

class ContextKey:
    """Context flag keys used in write operations"""
    SKIP_DOUBLE_BOOKING_CHECK = 'skip_double_booking_check'
    SKIP_BOOKING_CHECK = 'skip_booking_check'
    SKIP_READONLY_CHECK = 'skip_readonly_check'
    FORCE_SYNC = 'force_sync'
    SKIP_EVENT_SYNC = 'skip_event_sync'
    SKIP_ROOMS_SYNC = 'skip_rooms_sync'
    SKIP_AVAILABILITY_CHECK = 'skip_availability_check'


class GroupNames:
    """Security group identifiers"""
    MEETING_MANAGER = 'meeting_rooms.group_meeting_manager'
    MEETING_USER = 'meeting_rooms.group_meeting_user'
