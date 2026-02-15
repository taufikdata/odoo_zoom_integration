# 🚀 QUICK DEPLOYMENT GUIDE
## Meeting Rooms Module - Production Checklist

**Last Updated:** January 2025  
**Approved For:** Production Deployment ✅

---

## PHASE 1: PRE-DEPLOYMENT (Do This 1 Week Before)

### Step 1: Database Backup
```bash
# Full Odoo database backup
pg_dump -h localhost -U odoo odoo_db > /backup/odoo_db_$(date +%Y%m%d).sql

# Verify backup
pg_restore --list /backup/odoo_db_$(date +%Y%m%d).sql | head -20
```

### Step 2: Create Database Indexes
Connect to PostgreSQL as odoo user:

```sql
-- Connect to Odoo database
psql -U odoo -d odoo_db

-- Create indexes for meeting.event queries
CREATE INDEX IF NOT EXISTS meeting_event_start_date_idx 
    ON meeting_event(start_date);

CREATE INDEX IF NOT EXISTS meeting_event_end_date_idx 
    ON meeting_event(end_date);

CREATE INDEX IF NOT EXISTS meeting_event_state_idx 
    ON meeting_event(state);

CREATE INDEX IF NOT EXISTS meeting_event_dates_state_idx 
    ON meeting_event(start_date, end_date, state);

-- Create indexes for booking operations
CREATE INDEX IF NOT EXISTS booking_link_token_idx 
    ON meeting_booking_link(token);

CREATE INDEX IF NOT EXISTS meeting_rooms_location_idx 
    ON meeting_rooms(room_location);

-- Verify indexes created
\di meeting_event*
```

### Step 3: Install Python Dependencies
```bash
# Check if packages installed
pip list | grep -E 'pytz|requests|cryptography'

# If missing, install
pip install pytz>=2021.1 requests>=2.25.0 cryptography>=3.0
```

### Step 4: Configure API Credentials (SECURE METHOD)

**Option A: Using Environment Variables (Recommended)**

```bash
# .env file (keep secret, never commit to git)
ZOOM_ACCOUNT_ID=your_zoom_account_id
ZOOM_CLIENT_ID=your_zoom_client_id
ZOOM_CLIENT_SECRET=your_zoom_client_secret_key_here

GOOGLE_PROJECT_ID=your_google_project_id
GOOGLE_CLIENT_EMAIL=your_service_account@project.iam.gserviceaccount.com
GOOGLE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n..."

TEAMS_TENANT_ID=your_microsoft_tenant_id
TEAMS_CLIENT_ID=your_client_id
TEAMS_CLIENT_SECRET=your_client_secret
```

Then in code:
```python
import os

zoom_secret = os.environ.get('ZOOM_CLIENT_SECRET', '')
google_key = os.environ.get('GOOGLE_PRIVATE_KEY', '')
```

**Option B: Using Odoo Fields (If encryption available)**

In virtual_room.py:
```python
zoom_client_secret = fields.Char(
    string="Secret",
    groups="meeting_rooms.group_meeting_manager",
)
# Odoo 13+ automatically encrypts this field
```

**Option C: Using Odoo Secrets Module** (Most Secure)
```python
from odoo.addons.base.models.ir_config_parameter import _logger
from odoo.tools import config

zoom_secret = self.env['ir.config_parameter'].sudo().get_param(
    'meeting_rooms.zoom_client_secret'
)
```

### Step 5: Test Zoom API Connection

Navigate to Meeting > Settings > Virtual Rooms
- Fill in Zoom credentials
- Click "Test Connection" button (if exists)
- Verify success message

### Step 6: Configure Cron Jobs

In Odoo backend:
1. Go to **Settings > Technical > Automation > Scheduled Actions**
2. Search for these cron jobs:
   - `meeting_rooms.mail_cron_auto_delete_activities` 
   - `meeting_rooms.mail_cron_delete_old_ics_files`
3. Verify they are **Active: True**
4. Check run times (Should be during low-traffic hours)

```xml
<!-- data/cron_job.xml - Already configured, verify exists: -->
<record id="mail_cron_auto_delete_activities" model="ir.cron">
    <field name="name">Meeting Rooms: Delete Stale Activities</field>
    <field name="model_id" ref="meeting_event_model"/>
    <field name="state">code</field>
    <field name="code">model._cron_auto_delete_activities()</field>
    <field name="interval_number">1</field>
    <field name="interval_type">days</field>
    <field name="nextcall">2025-01-15 02:00:00</field>
    <field name="active" eval="True"/>
</record>
```

---

## PHASE 2: DEPLOYMENT TESTING (Do This on Staging)

### Test 1: Permission System (Most Critical)
```
Test User: testhost@example.com (Host)
Test User: testguest@example.com (Email Attendee)

Scenario A: Host Creates + Confirms Meeting
✓ Host can confirm → Zoom link should be generated
✓ Host can cancel → Attendees should get cancellation email

Scenario B: Non-Host Tries to Cancel
✗ Should get: "Access Denied: Only creator/host can cancel"

Scenario C: Admin Override
✓ Admin should be able to cancel anyone's meeting
```

### Test 2: Timezone Conversion
```
Test Case: Meeting at 13:00 Singapore time

Attendee 1: Timezone = Jakarta
  Expected: Activity shows 12:00 (Jakarta)
  
Attendee 2: Timezone = Tokyo
  Expected: Activity shows 14:00 (Tokyo)
  
Attendee 3: Timezone = London
  Expected: Activity shows 05:00 (London)

✓ All times should match local timezone
```

### Test 3: Booking Portal
```
1. Access /book/<token>
2. Select a time slot
3. Fill details:
   - Name: "Test Guest"
   - Email: "guest@example.com"
   - Subject: "Test Meeting"
4. Submit booking

Expected:
✓ Confirmation page shown
✓ Email sent to guest
✓ Meeting.event created in Draft state
✓ Host receives activity notification
```

### Test 4: Concurrent Booking (Rate Limit)
```
1. Open booking portal in 2 browser tabs
2. Both click same time slot
3. First one submits → Success
4. Second one submits within 60 seconds → Should get:
   "Too many requests. Wait X seconds before booking again."

✓ Rate limiter working
```

### Test 5: Email & ICS Files
```
1. Host sends invitations to 5 attendees
2. Check each email received:
   ✓ Subject shows attendee's timezone (e.g. "Meeting @ 14:00 (JST)")
   ✓ Time breakdown table shows their local time
   ✓ Timezone Details table shows all rooms/providers
   ✓ ICS attachment included
   
3. Open .ics in Outlook/Google Calendar
   ✓ All times show correctly in attendee's timezone
```

### Test 6: Zoom Meeting Creation
```
1. Host creates meeting with Zoom provider
2. Click "Generate Meeting Link"

Expected:
✓ Zoom meeting created (check zoom.com account)
✓ Join URL shown in meeting form
✓ Meeting ID displayed
✓ Email sent with join link
```

### Test 7: Large Attendee List
```
1. Create meeting with 100 attendees
2. Send invitations

Expected:
✓ Completes within 30 seconds (not timeout)
✓ All 100 emails sent
✓ Server logs show no errors
✓ Database has 100 activities created
```

### Test 8: Cron Job Execution
```
1. Create 50 old activities (backdated to 61 days ago)
2. Run cron manually:
   - Go to Settings > Scheduled Actions
   - Click "Execute Now" on delete activities cron

Expected:
✓ Old activities deleted
✓ Recent activities remain
✓ Log shows: "CRON JOB: Deleted X Stale Activities"
```

## PHASE 3: PRODUCTION DEPLOYMENT

### Step 1: Schedule Maintenance Window
- Announce 30 minutes downtime to users
- Backup database (required)
- Update Odoo code from git

```bash
cd /opt/odoo

# Backup database
pg_dump odoo_db > /backup/pre_deploy_$(date +%Y%m%d_%H%M%S).sql

# Pull latest code
git pull origin main

# Install dependencies
pip install -r requirements.txt

# Restart Odoo
systemctl restart odoo
```

### Step 2: Verify Module Loaded
```
1. Login to Odoo as admin
2. Go to Apps > Search "Meeting Rooms"
3. Verify status shows "Installed" ✓
4. Check for database migration messages (should show none if fresh install)
```

### Step 3: Create Admin Group
```
1. Settings > Users & Companies > Groups
2. Create group "Meeting Managers"
3. Add portal managers to group
4. These users can:
   - Cancel anyone's meeting
   - View all meeting reports
   - Manage virtual room credentials
```

### Step 4: Test Live Environment
Run all tests from PHASE 2 again in production environment

### Step 5: Monitor First 24 Hours
```
Checklist:
☐ No 500 errors in Odoo logs
☐ Cron jobs executed successfully
☐ Users can access booking portal
☐ Host can confirm meetings
☐ Emails sent without delay
☐ Database size normal (no bloat)
☐ Response times <200ms for calendar view
```

---

## PHASE 4: POST-DEPLOYMENT (Ongoing)

### Weekly Tasks
```
Monday:
☐ Check Zoom API error logs
☐ Verify cron jobs ran
☐ Review failed emails
☐ Monitor database size growth
  SELECT pg_size_pretty(pg_total_relation_size('ir_attachment'));

Friday:
☐ Generate weekly report:
  - Total meetings created
  - Total bookings via portal
  - API errors count
  - Performance metrics (avg query time)
```

### Monthly Tasks
```
☐ Run database maintenance:
  VACUUM ANALYZE meeting_event;
  REINDEX TABLE meeting_event;

☐ Review database indexes:
  SELECT * FROM pg_stat_user_indexes WHERE schemaname='public';

☐ Archive old ICS files (cron should do this, but verify):
  SELECT COUNT(*) FROM ir_attachment 
  WHERE create_date < NOW() - INTERVAL '90 days';

☐ Check for orphaned activities:
  SELECT COUNT(*) FROM mail_activity 
  WHERE res_id NOT IN (SELECT id FROM meeting_event);

☐ Security audit:
  - Check logs for failed access attempts
  - Verify API credentials not in logs
  - Review user permissions
```

### Quarterly Tasks (Every 3 Months)
```
☐ Performance optimization:
  - Check slow query logs
  - Review index usage
  - Consider query rewrites if needed

☐ Disaster recovery test:
  - Restore from backup to test environment
  - Verify data integrity
  - Check all features work

☐ API limit monitoring:
  - Zoom: Current usage % of monthly quota
  - Google: Current usage % of daily quota  
  - Teams: Current usage % of limits

☐ Capacity planning:
  - Extrapolate growth (meetings per month)
  - Plan for next year's needs
  - Consider database expansion if >80% full
```

### Annually (Every Year)
```
☐ Full security audit
☐ Disaster recovery drill
☐ Infrastructure capacity planning
☐ API renewal (before expiry)
☐ Update all dependencies
☐ Review and update encryption keys
```

---

## TROUBLESHOOTING GUIDE

### Issue 1: Booking Portal Shows "Token Invalid"
**Symptom:** Users can't access /book/<token>

**Debug:**
```python
# Check if link exists
meeting_link = self.env['meeting.booking.link'].search([
    ('token', '=', token)
])
print(f"Links found: {len(meeting_link)}")
print(f"Active: {meeting_link.active if meeting_link else 'N/A'}")
```

**Fixes:**
- [ ] Verify token is correct (no typos)
- [ ] Check if booking link is marked active
- [ ] Check if host user still exists
- [ ] Regenerate token if needed

### Issue 2: Emails Not Sending
**Symptom:** No confirmation emails to guests

**Debug:**
```bash
# Check mail queue
SELECT * FROM mail_mail WHERE state='exception' LIMIT 10;

# Check SMTP configuration
Settings > Technical > Email Configuration > Outgoing Mail Servers
```

**Fixes:**
- [ ] Verify SMTP server connection
- [ ] Check SMTP credentials (not API key!)
- [ ] Verify sender email is correct
- [ ] Check mail logs for exceptions
- [ ] Test with manual email to admin first

### Issue 3: Cron Job Not Running
**Symptom:** Old activities not deleted after 3 days

**Debug:**
```
Settings > Technical > Automation > Scheduled Actions
Search: "Delete Stale Activities"
Check:
  - Active? (Should be True)
  - Next execution time? (Should be recent)
  - Execution logs? (Expand to see history)
```

**Fixes:**
- [ ] Mark cron as Active
- [ ] Restart Odoo service
- [ ] Check if cron daemon running:
  ```bash
  ps aux | grep cron
  ps aux | grep odoo
  ```

### Issue 4: Zoom Meeting Link Not Generated
**Symptom:** Click "Generate Meeting Link" shows spinning wheel for 30s, then fails

**Debug:**
```python
# Check Zoom credentials
room = self.env['virtual.room'].search([('provider', '=', 'zoom')], limit=1)
print(f"Account ID: {room.zoom_account_id}")
print(f"Client ID: {room.zoom_client_id}")
print(f"Secret: {room.zoom_client_secret[:10]}...")  # First 10 chars only

# Test Zoom token generation
token = meeting._get_zoom_access_token()
print(f"Token obtained: {token[:20]}...")
```

**Fixes:**
- [ ] Verify Zoom credentials in virtual.room
- [ ] Test Zoom API manually:
  ```bash
  curl -X GET https://api.zoom.us/v2/users/me \
    -H "Authorization: Bearer YOUR_TOKEN"
  ```
- [ ] Check network connectivity to api.zoom.us
- [ ] Verify Zoom account not rate-limited

### Issue 5: Timezone Shows Wrong Time
**Symptom:** Activity shows 12:00 but should show 14:00

**Debug:**
```python
# Check user timezone
host = self.env['res.users'].browse(host_id)
print(f"Host timezone: {host.tz}")

attendee = self.env['res.users'].browse(attendee_id)
print(f"Attendee timezone: {attendee.tz}")

# Check booking link timezone
link = self.env['meeting.booking.link'].search([('token', '=', token)])
print(f"Link timezone: {link.tz}")

# Manual conversion test
from datetime import datetime
import pytz
dt = datetime(2025, 1, 15, 12, 0, 0)
utc_dt = pytz.utc.localize(dt)
local_dt = utc_dt.astimezone(pytz.timezone('Asia/Jakarta'))
print(f"UTC 12:00 → Jakarta: {local_dt}")
```

**Fixes:**
- [ ] Check user timezone in Settings > Users
- [ ] Check booking link timezone (may override user tz)
- [ ] Verify PyTZ database updated: `pip install --upgrade pytz`
- [ ] Check if DST (daylight saving) affects time

### Issue 6: Database Running Slow
**Symptom:** Booking calendar takes 5+ seconds to load

**Debug:**
```bash
# Check indexes
psql -U odoo -d odoo_db -c "\di+ meeting_event*"

# Check table size
psql -U odoo -d odoo_db -c "SELECT pg_size_pretty(pg_total_relation_size('meeting_event'));"

# Enable query logging
SET log_min_duration_statement = 1000;  # Log queries >1 second
```

**Fixes:**
- [ ] Create missing indexes (see Phase 1)
- [ ] Run VACUUM and REINDEX:
  ```sql
  VACUUM ANALYZE meeting_event;
  REINDEX TABLE meeting_event;
  ```
- [ ] Check if enough disk space
- [ ] Monitor for long-running queries

---

## ROLLBACK PROCEDURE (If Something Goes Wrong)

### Immediate Rollback (First Hour)
```bash
# 1. Backup current corrupted database
pg_dump odoo_db > /backup/corrupted_$(date +%Y%m%d_%H%M%S).sql

# 2. Restore from pre-deployment backup
pg_restore -d odoo_db /backup/pre_deploy_20250115_100000.sql

# 3. Restart Odoo with previous code
git checkout HEAD~1
systemctl restart odoo

# 4. Verify system working
# - Login
# - Check booking portal
# - Send test email
```

### After Verification
```
1. Identify what went wrong (check logs)
2. Fix in code
3. Test on staging environment
4. Re-deploy during next maintenance window
```

---

## SUCCESS CRITERIA (Go/No-Go Decision)

### ✅ GO LIVE if:
- [ ] All tests in PHASE 2 pass
- [ ] Database indexes created
- [ ] API credentials configured securely
- [ ] Cron jobs run successfully
- [ ] Backup verified restorable
- [ ] Load testing: <200ms response time
- [ ] Error logs clean (no exceptions)
- [ ] Admin team trained

### 🛑 DO NOT GO LIVE if:
- [ ] Any permission test failed
- [ ] Zoom API not responding
- [ ] Email sending fails
- [ ] Database backup can't restore
- [ ] Response time >1s consistently
- [ ] Concurrent booking race condition observed
- [ ] Critical bugs in logs

---

**Document Version:** 1.0  
**Last Reviewed:** January 2025  
**Next Review:** When module is deployed to production
