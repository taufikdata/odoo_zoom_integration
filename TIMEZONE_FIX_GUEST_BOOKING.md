# Timezone Fix untuk Email Invitation ke Guest (External User)

## Masalah
Ketika external/guest user melakukan booking melalui booking link:
- Mereka memilih timezone saat booking (contoh: Europe/Brussels, menampilkan 10:00)
- Tapi email undangan yang mereka terima menampilkan waktu dalam timezone YANG SALAH (contoh: Asia/Makassar 17:00)

**Diharapkan:** Email harus menampilkan waktu dalam timezone yang sama dengan yang dipilih guest saat booking.

---

## Solusi yang Diterapkan

### 1. **Tambah Field `guest_tz` di Model `meeting.event`**
   - **File:** `/custom_addons/meeting_rooms/models/meeting_event.py` (lines 88-92)
   - **Tujuan:** Menyimpan timezone yang dipilih guest saat booking
   - **Default:** 'UTC' (untuk backward compatibility, jika meeting dibuat manually)

```python
guest_tz = fields.Char(
    string="Guest Timezone",
    help="Timezone selected by guest when booking through booking link",
    default='UTC'
)
```

### 2. **Update Booking Link Event Creation**
   - **File:** `/custom_addons/meeting_rooms/controllers/booking_portal.py` (line 274)
   - **Tujuan:** Ketika guest booking, simpan timezone yang dipilih ke field `guest_tz`
   - **Implementasi:** Saat create event, tambahkan `'guest_tz': target_tz_name,`

```python
new_event = request.env['meeting.event'].sudo().with_user(host_user).with_context(tz='UTC').create({
    # ... existing fields ...
    'guest_tz': target_tz_name,  # Timezone dari booking link
})
```

### 3. **Update Email Sending Logic**
   - **File:** `/custom_addons/meeting_rooms/models/meeting_event.py` (lines 1700-1724)
   - **Method:** `create_calendar_web()`
   - **Tujuan:** Gunakan `guest_tz` saat kirim email ke guest, bukan `host_tz`

**Perubahan:**
- Tambahkan `guest_tz = rec.guest_tz or host_tz` (line 1701)
- Update "Guest Partner" targets untuk gunakan `guest_tz` (line 1705)
- Update "Extra Emails" targets untuk gunakan `guest_tz` (line 1712)

```python
# B. Guest Partner
host_tz = rec.host_user_id.tz or rec.create_uid.tz or 'UTC'
guest_tz = rec.guest_tz or host_tz  # Gunakan guest_tz jika ada

if rec.guest_partner_id and rec.guest_partner_id.email:
    targets.append({
        'email': rec.guest_partner_id.email,
        'name': rec.guest_partner_id.name,
        'tz': guest_tz,  # ✅ Gunakan guest_tz, bukan host_tz
        'type': 'partner'
    })

# C. Extra Emails (Raw strings) - Use same timezone as guest booking
if rec.guest_emails:
    extras = [e.strip() for e in re.split(r'[;\n,]+', rec.guest_emails) if e.strip()]
    for e in extras:
        targets.append({
            'email': e,
            'name': 'Guest',
            'tz': guest_tz,  # ✅ Gunakan guest_tz, bukan host_tz
            'type': 'guest'
        })
```

---

## Flow Timezone Setelah Fix

### ✅ **Internal Odoo User** (Tetap sama)
```
1. Booking page menampilkan timezone booking link
2. Internal user terundang ditambah ke attendee
3. Email ke internal user gunakan timezone OCX user mereka sendiri
```

### ✅ **External/Guest User via Booking Link** (SUDAH DIPERBAIKI)
```
1. Guest memilih slot dan timezone ditampilkan (contoh: Europe/Brussels, 10:00)
2. Event dibuat dengan guest_tz = 'Europe/Brussels' (simpan timezone yang dipilih)
3. Email ke guest menampilkan waktu dalam Europe/Brussels (10:00) ✅ BENAR!
4. ICS file juga convert ke timezone yang sama (Europe/Brussels)
```

---

## Testing

### Scenario 1: Guest Booking dengan Timezone Europe/Brussels
```
1. Host buat booking link dengan timezone = Europe/Brussels
2. Guest book slot untuk 14 Feb 2026, 10:00 (Europe/Brussels)
3. Confirmation page tampil: "Saturday, 14 Feb 2026 — 10:00 (Europe/Brussels) / 09:00 UTC"
4. Email ke guest harus tampil: "Time: 10:00 - 11:00 (Europe/Brussels)" ✅
```

### Scenario 2: Guest Booking dengan Timezone Asia/Makassar
```
1. Host buat booking link dengan timezone = Asia/Makassar
2. Guest book slot untuk 14 Feb 2026, 17:00 (Asia/Makassar)
3. Email ke guest harus tampil: "Time: 17:00 - 18:00 (Asia/Makassar)" ✅
```

---

## Backward Compatibility
- ✅ Field `guest_tz` memiliki default 'UTC'
- ✅ Meetings yang dibuat manual (tidak via booking link) akan gunakan `host_tz`
- ✅ Tidak ada breaking changes pada logic existing

---

## Files Modified
1. `/custom_addons/meeting_rooms/models/meeting_event.py`
   - Tambah field `guest_tz` (lines 88-92)
   - Update `create_calendar_web()` method (lines 1700-1724)

2. `/custom_addons/meeting_rooms/controllers/booking_portal.py`
   - Update event creation (line 274)
   - Simpan `guest_tz` dari booking link

---

## Note
- Internal users tetap dapat timezone mereka sendiri dari Odoo user setting
- Guest users akan dapat timezone yang mereka pilih saat booking link
- Host dapat setup multiple booking links dengan timezone berbeda-beda
