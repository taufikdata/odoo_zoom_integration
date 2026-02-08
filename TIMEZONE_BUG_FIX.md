# 🐛 Timezone Bug Fix - Booking Portal

## 📋 Problem Description

**Symptom:** Ketika external user booking meeting melalui booking portal, waktu yang terinput salah.
- User booking jam **09:00** (WIB)
- Yang tersimpan di Odoo: **17:00** (selisih +8 jam)

## 🔍 Root Cause Analysis

### Penyebab Utama:
1. **Naive Datetime** - Portal mengirim datetime tanpa informasi timezone
2. **Odoo Interpretation** - Database Odoo membaca datetime sebagai UTC
3. **Wrong Conversion** - Jam 09:00 tanpa timezone → dibaca sebagai 09:00 UTC → ditampilkan sebagai 17:00 WIB

### Technical Details:
```python
# ❌ SEBELUM (SALAH):
start_dt = datetime.strptime('2026-02-06 09:00:00', '%Y-%m-%d %H:%M:%S')
# Ini menghasilkan "naive datetime" (tanpa timezone info)
# Odoo database menganggapnya UTC
# 09:00 UTC = 16:00 WIB (UTC+7) atau 17:00 WITA (UTC+8)

# ✅ SESUDAH (BENAR):
start_dt_host = host_tz.localize(datetime(2026, 2, 6, 9, 0, 0))
# Ini "timezone-aware" → Asia/Jakarta 09:00
start_dt_utc = start_dt_host.astimezone(pytz.UTC)
# Konversi ke UTC: 09:00 WIB = 02:00 UTC
# Simpan di database sebagai 02:00 UTC
# Saat ditampilkan: 02:00 UTC → 09:00 WIB ✅
```

## 🛠️ Solutions Implemented

### File Modified: `controllers/booking_portal.py`

#### 1. **Import dateutil parser** (Line 5)
```python
from dateutil import parser as dateutil_parser
```

#### 2. **Generate Time Slots with Timezone** (Line 73-95)
```python
# Generate slots dalam timezone host
start_dt_host = host_tz.localize(datetime.combine(current_date, time(hour, 0, 0)))

# Konversi ke UTC untuk query database
start_dt_utc = start_dt_host.astimezone(pytz.UTC)
end_dt_utc = end_dt_host.astimezone(pytz.UTC)

# Check availability dengan UTC times
domain = [
    ('start_date', '<', end_dt_utc),
    ('end_date', '>', start_dt_utc),
    ...
]

# Simpan slot dalam format ISO (includes timezone)
day_slots.append({
    'time_str': f"{hour:02d}:00", 
    'val': start_dt_host.isoformat()  # ISO format: 2026-02-06T09:00:00+07:00
})
```

#### 3. **Parse Timezone-Aware Datetime** (Line 143-148)
```python
# Parse ISO format (includes timezone)
dt = dateutil_parser.isoparse(time_str.strip())  # Aware datetime
dt_host = dt.astimezone(host_zone)  # Convert to host timezone for display
pretty_time_str = dt_host.strftime('%A, %d %b %Y - %H:%M') + f' ({host_tz_name})'
```

#### 4. **Submit Booking with UTC Conversion** (Line 213-223)
```python
# Parse timezone-aware datetime dari form
start_dt_aware = dateutil_parser.isoparse(time_str.strip())
end_dt_aware = start_dt_aware + timedelta(hours=1)

# Konversi ke UTC (standard Odoo database)
start_dt_utc = start_dt_aware.astimezone(pytz.UTC).replace(tzinfo=None)
end_dt_utc = end_dt_aware.astimezone(pytz.UTC).replace(tzinfo=None)

# Simpan ke database dengan UTC times
new_event = request.env['meeting.event'].sudo().create({
    'subject': final_subject,
    'start_date': start_dt_utc,  # UTC time
    'end_date': end_dt_utc,      # UTC time
    ...
})
```

## ✅ Testing Steps

### Test Case 1: Basic Booking
1. Buka booking link: `http://localhost:8069/book/<token>`
2. Pilih slot jam **09:00** 
3. Isi form dan submit
4. **Verify**: Di Odoo, meeting tersimpan jam **09:00** (bukan 17:00) ✅

### Test Case 2: Cross Timezone
1. Set user host timezone: **Asia/Jakarta (WIB, UTC+7)**
2. Booking jam **14:00**
3. **Verify**: 
   - Database: `2026-02-06 07:00:00` (UTC)
   - Display: `2026-02-06 14:00:00` (WIB) ✅

### Test Case 3: Conflict Detection
1. User A booking jam **10:00-11:00**
2. User B coba booking jam **10:30-11:30**
3. **Verify**: System mendeteksi conflict ✅

## 📊 Before vs After Comparison

| Scenario | Before (Bug) | After (Fixed) |
|----------|--------------|---------------|
| User booking jam 09:00 | Tersimpan 17:00 ❌ | Tersimpan 09:00 ✅ |
| Database storage | Naive datetime | UTC datetime ✅ |
| Timezone handling | None | Proper conversion ✅ |
| Conflict detection | Wrong time range ❌ | Correct time range ✅ |

## 🎯 Key Improvements

1. ✅ **Timezone-Aware Datetime** - Semua datetime sekarang include timezone info
2. ✅ **UTC Standardization** - Database menyimpan dalam UTC (Odoo standard)
3. ✅ **ISO Format** - Menggunakan ISO 8601 format untuk transfer data
4. ✅ **Proper Conversion** - Konversi timezone dilakukan dengan benar
5. ✅ **Conflict Detection** - Check availability menggunakan UTC times

## 🔒 Dependencies

- **python-dateutil** - Already included in Odoo standard dependencies
- **pytz** - Already used in the project

## 📝 Notes

- Odoo database **SELALU** menyimpan datetime dalam **UTC**
- Display ke user menggunakan timezone user/host
- Portal booking menggunakan timezone host untuk consistency
- ISO 8601 format: `2026-02-06T09:00:00+07:00` (includes timezone offset)

---

**Fixed By:** GitHub Copilot  
**Date:** February 6, 2026  
**Status:** ✅ Ready for Testing
