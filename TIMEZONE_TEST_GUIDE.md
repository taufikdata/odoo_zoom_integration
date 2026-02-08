# Testing Guide for Timezone Fix

## Quick Test

1. **Go to booking link** (using guest browser or incognito):
   ```
   http://localhost:8069/book/<token>
   ```
   Replace `<token>` with actual booking link token

2. **Select a time slot**:
   - Look at the calendar showing times like "09:00", "10:00", "11:00", etc.
   - These are in Europe/Brussels timezone (shown in header)
   - Click on 11:00 or another time

3. **Check form display**:
   - Form should show: "Monday, 08 Feb 2026 - 11:00 (Europe/Brussels)"
   - This confirms the time was converted correctly from UTC

4. **Submit booking**:
   - Fill in: Name, Email, Subject (optional)
   - Click "Confirm Booking"
   - Should see success message

5. **Check in Odoo**:
   - Login as host user (with Europe/Brussels timezone)
   - Go to "Meetings" or calendar
   - Find the meeting just created
   - **VERIFY**: Meeting shows at 11:00 Brussels, NOT 18:00

## How to Get Booking Link Token

If you don't have a token:

1. In Odoo, go to: Meetings > Booking Links
2. Click on a booking link record
3. Copy the "Token" field
4. Use in URL: `/book/<token>`

## Expected Results (AFTER FIX)

| Step | Expected | Previous (Broken) |
|------|----------|---|
| Calendar display | "11:00" | "11:00" (same) |
| Form display | "11:00 (Europe/Brussels)" | "11:00 (Europe/Brussels)" (same) |
| Odoo meeting time | **11:00 Brussels** ✓ | **18:00 Brussels** ✗ |
| Database (UTC) | 10:00 UTC | 10:00 UTC (same, but interpreted wrong) |

## Technical Verification (Advanced)

If you want to verify at database level:

```sql
-- Connect to Docker database
psql -h localhost -U odoo -d zoom_bersih -c "SELECT id, subject, start_date, end_date FROM meeting_event ORDER BY create_date DESC LIMIT 1;"

-- Expected output should show start_date as UTC time
-- For 11:00 Brussels slot, should be around 10:00 UTC (Feb in Brussels is UTC+1)
```

## Files Changed

Only one file modified:
- [custom_addons/meeting_rooms/controllers/booking_portal.py](custom_addons/meeting_rooms/controllers/booking_portal.py)
  - Lines 207-215: Changed from naive to timezone-aware UTC datetime
  - Line 254: Removed unnecessary context parameter
  - Line 266: Removed unnecessary context parameter

## What Was Fixed

### The Bug
When passing datetimes to Odoo:
```python
# BEFORE (WRONG):
start_dt = start_dt_utc_aware.replace(tzinfo=None)  # Naive datetime
create({'start_date': start_dt})  # Odoo interprets as user's timezone!
```

When Odoo received a naive datetime and the creating user had Europe/Brussels timezone:
- Naive `10:00` was interpreted as `10:00 Brussels` 
- Converted to UTC: `09:00 UTC`
- Displayed back to user: `10:00 Brussels` 

But something was adding 7-8 more hours, suggesting a secondary timezone context somewhere.

### The Solution
```python
# AFTER (CORRECT):
start_dt_utc = pytz.utc.localize(start_dt_naive)  # Make it UTC-aware!
create({'start_date': start_dt_utc})  # Odoo sees explicit UTC, no ambiguity
```

Now Odoo receives timezone-aware datetime, so it knows exactly what timezone the datetime is in and can convert to UTC correctly for storage.

## Rollback (If Needed)

If this fix doesn't work, revert to previous:

```bash
git checkout HEAD -- custom_addons/meeting_rooms/controllers/booking_portal.py
```

Then try alternative approaches if needed.
