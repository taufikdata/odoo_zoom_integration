#!/usr/bin/env python3
"""
Test script to verify timezone handling in booking portal.

Tests that:
1. Calendar generates slots in host timezone (Europe/Brussels)
2. Slots are converted to UTC for storage  
3. Form displays time correctly in host timezone
4. Submit preserves UTC datetime through to Odoo storage
"""

from datetime import datetime, timedelta
import pytz

# Simulate the flow
print("=" * 60)
print("TIMEZONE CONVERSION TEST")
print("=" * 60)

# Host timezone
host_tz_name = 'Europe/Brussels'
host_tz = pytz.timezone(host_tz_name)

# Test date & time: Feb 8, 2026 at 11:00 Brussels time
test_date = 2026, 2, 8
test_hour = 11

# Step 1: Generate slot in calendar (host timezone)
print("\n[1] CALENDAR GENERATION")
print(f"    Host timezone: {host_tz_name}")
start_dt_host = host_tz.localize(datetime(test_date[0], test_date[1], test_date[2], test_hour, 0, 0))
print(f"    Slot start (host tz): {start_dt_host}")

# Step 2: Convert to UTC for database query
print("\n[2] UTC CONVERSION FOR DB QUERY")
start_dt_utc = start_dt_host.astimezone(pytz.utc).replace(tzinfo=None)
print(f"    Slot start (UTC, naive): {start_dt_utc}")
time_str = start_dt_utc.strftime('%Y-%m-%d %H:%M:%S')
print(f"    time_str passed to form: '{time_str}'")

# Step 3: Display form (convert back to host tz for display)
print("\n[3] FORM DISPLAY")
dt_utc = datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
dt_utc_aware = pytz.utc.localize(dt_utc)
dt_host = dt_utc_aware.astimezone(host_tz)
print(f"    time_str input: '{time_str}'")
print(f"    Parsed as UTC (aware): {dt_utc_aware}")
print(f"    Converted to host tz: {dt_host}")
display_time = dt_host.strftime('%A, %d %b %Y - %H:%M') + f' ({host_tz_name})'
print(f"    Display time: {display_time}")

# Step 4: Submit (parse UTC and store)
print("\n[4] SUBMIT TO ODOO")
start_dt_naive = datetime.strptime(time_str.strip(), '%Y-%m-%d %H:%M:%S')
end_dt_naive = start_dt_naive + timedelta(hours=1)

# Make timezone-aware as UTC
start_dt_utc_aware = pytz.utc.localize(start_dt_naive)
end_dt_utc_aware = pytz.utc.localize(end_dt_naive)

print(f"    time_str received: '{time_str}'")
print(f"    Parsed as naive: {start_dt_naive}")
print(f"    Made UTC-aware: {start_dt_utc_aware}")
print(f"    For storage: {start_dt_utc_aware}")

# Step 5: What Odoo displays
print("\n[5] ODOO DISPLAY (simulating)")
# Odoo reads the UTC datetime and converts to host user timezone for display
odoo_displayed = start_dt_utc_aware.astimezone(host_tz)
print(f"    Stored in DB (UTC): {start_dt_utc_aware}")
print(f"    Displayed by Odoo (host tz): {odoo_displayed}")

# Verification
print("\n[6] VERIFICATION")
print(f"    Original slot: {start_dt_host.strftime('%Y-%m-%d %H:%M')} {host_tz_name}")
print(f"    Displayed in form: {dt_host.strftime('%Y-%m-%d %H:%M')} {host_tz_name}")
print(f"    Odoo display: {odoo_displayed.strftime('%Y-%m-%d %H:%M')} {host_tz_name}")
print(f"    Match: {start_dt_host.replace(tzinfo=None) == odoo_displayed.replace(tzinfo=None)}")

print("\n" + "=" * 60)
