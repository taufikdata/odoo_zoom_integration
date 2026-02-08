# Timezone Logic - Final Clean Implementation

## Problem Statement
User books meeting at 10:00 Brussels time, but Odoo shows 17:00 (7-hour difference).

## Solution: UTC-Only Storage with Context Control

### Flow Diagram

```
CALENDAR GENERATION (booking_calendar)
├─ Generate slots 09:00-17:00 in Europe/Brussels timezone
├─ For each slot, e.g., 10:00 Brussels:
│  ├─ Create aware datetime: 10:00 Europe/Brussels
│  ├─ Convert to UTC: 09:00 UTC
│  ├─ Strip tzinfo: 09:00 (naive)
│  └─ Send as 'val': "2026-02-08 09:00:00"
└─ Send to template: val="2026-02-08 09:00:00"

FORM DISPLAY (booking_details_form)
├─ Receive: time_str="2026-02-08 09:00:00" (UTC)
├─ Parse as UTC aware: 2026-02-08 09:00:00+00:00
├─ Convert to host tz: 2026-02-08 10:00:00+01:00 (Brussels)
├─ Display to user: "Monday, 08 Feb 2026 - 10:00 (Europe/Brussels)"
└─ Hidden field: time_str="2026-02-08 09:00:00"

FORM SUBMIT (booking_submit)
├─ Receive: time_str="2026-02-08 09:00:00"
├─ Parse as naive datetime: datetime(2026, 2, 8, 9, 0, 0)
├─ Create aware UTC: 2026-02-08 09:00:00+00:00 UTC
├─ Strip tzinfo for Odoo: 2026-02-08 09:00:00 (naive)
├─ Set context: tz='UTC' (tells Odoo to interpret naive as UTC)
└─ Create record with:
   ├─ start_date: 2026-02-08 09:00:00 (naive)
   ├─ context: tz='UTC'
   └─ Result: Odoo stores as 09:00 UTC

ODOO STORAGE & DISPLAY
├─ Database stores: 2026-02-08 09:00:00 UTC
├─ When host views (tz=Europe/Brussels):
│  ├─ Read from DB: 2026-02-08 09:00:00 UTC
│  ├─ Convert to host tz: 2026-02-08 10:00:00+01:00
│  └─ Display: 10:00 Brussels ✓ CORRECT
└─ Summary: What user booked = What they see
```

## Key Points

1. **Calendar → Form**: Always convert to host tz for DISPLAY, but pass UTC to form
2. **Form → Submit**: Keep UTC string, don't convert back
3. **Submit → Odoo**: Pass naive UTC with `.with_context(tz='UTC')`
   - This tells Odoo: "Don't apply user's timezone, this IS UTC"
   - Prevents Odoo from interpreting naive datetime as user's timezone
4. **Odoo → Display**: Let Odoo's automatic conversion handle it

## Critical Code Section

```python
# booking_submit() parsing
utc_naive = datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')  # 09:00
utc_aware = pytz.utc.localize(utc_naive)  # 09:00+00:00 UTC (for verification)
start_dt = utc_naive  # 09:00 (naive, for Odoo)

# Create with context
request.env['meeting.event'].with_context(tz='UTC').sudo().create({
    'start_date': start_dt,  # Naive 09:00
    # context tells Odoo: this naive datetime is UTC
})
```

## Expected Results

| Action | Input | Expected Storage | Expected Display (Brussels) |
|--------|-------|------------------|---------------------------|
| Book 10:00 | "09:00:00" (UTC) | 09:00 UTC | 10:00 Brussels |
| Book 14:00 | "13:00:00" (UTC) | 13:00 UTC | 14:00 Brussels |
| Book 17:00 | "16:00:00" (UTC) | 16:00 UTC | 17:00 Brussels |

## If Still Showing Wrong Time

- Check: `SELECT start_date FROM meeting_event WHERE id=X;` in DB
- Should be: UTC time (what was booked - 1 hour)
- If showing correct in DB but wrong in Odoo display, problem is read-side (Odoo's display layer)
- If showing wrong in DB, problem is write-side (this code)
