# Visual Comparison: Before vs After Fix

## BEFORE (❌ SALAH)

### Incoming Message (Customer → Device Kita)
```json
{
  "id": 115,
  "time": "2026-02-20 02:22:13",
  "sender_number": "6281805314808",     // ✓ Benar (customer)
  "sender_name": "Unknown",
  "message": "bisa",
  "direction": "in"                      // ✓ Benar (incoming)
}
```

### Outgoing Message (Device Kita → Customer)
```json
{
  "id": 114,
  "time": "2026-02-20 02:22:06",
  "sender_number": "6281805314808",     // ❌ SALAH! Ini adalah customer, bukan pengirim!
  "sender_name": "Unknown",
  "message": "selamat pagi pak...",
  "direction": "out"                     // ✓ Benar (outgoing)
  // ❌ MASALAH: sender_number harusnya adalah device kita (6285920524227), bukan customer
}
```

**Masalah**: Untuk outgoing message, `sender_number` menunjukkan nomor customer padahal field bernama "Nomor Pengirim" seharusnya menunjukkan siapa yang benar-benar mengirim (device kita).

---

## AFTER (✅ BENAR)

### Incoming Message (Customer → Device Kita)
```json
{
  "id": 115,
  "time": "2026-02-20 02:22:13",
  "sender_number": "6281805314808",       // ✅ BENAR (customer yang ngirim ke kita)
  "recipient_number": "6285920524227",    // ✅ BARU (kita yang nerima)
  "device_number": "6285920524227",       // ✅ BARU (device kita)
  "sender_name": "Unknown",
  "message": "bisa",
  "direction": "in"                       // ✅ BENAR (masuk)
}
```

**Penjelasan Incoming**:
- 🔹 **Customer** (6281805314808) = **Pengirim** → `sender_number`
- 🔹 **Device Kita** (6285920524227) = **Penerima** → `recipient_number`
- 🔹 `direction = "in"` = Pesan masuk

---

### Outgoing Message (Device Kita → Customer)
```json
{
  "id": 114,
  "time": "2026-02-20 02:22:06",
  "sender_number": "6285920524227",       // ✅ DIPERBAIKI (device kita yang ngirim)
  "recipient_number": "6281805314808",    // ✅ BARU (customer yang nerima)
  "device_number": "6285920524227",       // ✅ BARU (device kita)
  "sender_name": "Odoo System",
  "message": "selamat pagi pak...",
  "direction": "out"                      // ✅ BENAR (keluar)
}
```

**Penjelasan Outgoing**:
- 🔹 **Device Kita** (6285920524227) = **Pengirim** → `sender_number` ✅ FIXED
- 🔹 **Customer** (6281805314808) = **Penerima** → `recipient_number`
- 🔹 `direction = "out"` = Pesan keluar

---

## Perbandingan Field

| Status | Incoming | Outgoing |
|--------|----------|----------|
| **sender_number** | `6281805314808` (customer) | `6285920524227` (device kita) |
| **recipient_number** | `6285920524227` (device kita) | `6281805314808` (customer) |
| **device_number** | `6285920524227` (sama untuk semua) | `6285920524227` (sama untuk semua) |
| **direction** | `in` | `out` |

---

## API Response - GET History

### Before Fix ❌
```bash
GET /api/wa/get_history?phone=6281805314808
```

```json
{
  "status": "success",
  "count": 2,
  "data": [
    {
      "id": 114,
      "sender_number": "6281805314808",  // ❌ SALAH untuk outgoing
      "direction": "out"
    },
    {
      "id": 115,
      "sender_number": "6281805314808",  // ✓ BENAR untuk incoming
      "direction": "in"
    }
  ]
}
```

### After Fix ✅
```bash
GET /api/wa/get_history?phone=6281805314808
```

```json
{
  "status": "success",
  "count": 2,
  "data": [
    {
      "id": 114,
      "sender_number": "6285920524227",        // ✅ BENAR (device kita)
      "recipient_number": "6281805314808",    // ✅ BARU (customer)
      "device_number": "6285920524227",       // ✅ BARU
      "direction": "out"
    },
    {
      "id": 115,
      "sender_number": "6281805314808",        // ✅ BENAR (customer)
      "recipient_number": "6285920524227",    // ✅ BARU (device kita)
      "device_number": "6285920524227",       // ✅ BARU
      "direction": "in"
    }
  ]
}
```

---

## Wablas Webhook Flow

```
INCOMING MESSAGE dari Customer ke Device Kita:
┌──────────────────────────────┐
│ Customer (6281805314808)     │
│ Mengirim: "selamat pagi pak" │
└──────────────────────────────┘
                 │
                 │ Wablas API Webhook
                 │
┌──────────────────────────────────────────────┐
│ POST /api/wa/webhook                         │
│ {                                            │
│   "isFromMe": false,                         │
│   "sender": "6285920524227",   ← Device kita │
│   "phone": "6281805314808",    ← Customer    │
│   "message": "selamat pagi pak"              │
│ }                                            │
└──────────────────────────────────────────────┘
                 │
                 │ Extract & Map (AFTER FIX)
                 │
┌──────────────────────────────────────────────┐
│ Saved to Database:                           │
│ {                                            │
│   "direction": "in",                         │
│   "sender_number": "6281805314808", ✅       │
│   "recipient_number": "6285920524227", ✅    │
│   "device_number": "6285920524227" ✅        │
│ }                                            │
└──────────────────────────────────────────────┘
                 │
                 ▼
         Database Updated
```

```
OUTGOING MESSAGE dari Device Kita ke Customer:
┌──────────────────────────────┐
│ Device Kita (6285920524227)  │
│ Mengirim: "baik pak, jam 2 OK│
└──────────────────────────────┘
                 │
                 │ Wablas API Webhook (atau POST send)
                 │
┌──────────────────────────────────────────────┐
│ POST /api/wa/webhook (atau /send_message)    │
│ {                                            │
│   "isFromMe": true,                          │
│   "sender": "6285920524227",   ← Device kita │
│   "phone": "6281805314808",    ← Customer    │
│   "message": "baik pak, jam 2 OK"            │
│ }                                            │
└──────────────────────────────────────────────┘
                 │
                 │ Extract & Map (AFTER FIX)
                 │
┌──────────────────────────────────────────────┐
│ Saved to Database:                           │
│ {                                            │
│   "direction": "out",                        │
│   "sender_number": "6285920524227", ✅ FIXED │
│   "recipient_number": "6281805314808", ✅    │
│   "device_number": "6285920524227" ✅        │
│ }                                            │
└──────────────────────────────────────────────┘
                 │
                 ▼
         Database Updated
```

---

## Key Takeaways

✅ **FIXED**: `sender_number` sekarang selalu menunjukkan "siapa yang benar-benar mengirim"
- Incoming: customer (6281805314808)
- Outgoing: device kita (6285920524227)

✅ **NEW**: Field `recipient_number` menunjukkan "siapa yang menerima"
- Incoming: device kita (6285920524227)
- Outgoing: customer (6281805314808)

✅ **NEW**: Field `device_number` selalu nomor device/gateway kita
- Berguna untuk tracking di multi-device setup

---

## Next Steps

1. **Run Migration** (jika database sudah ada):
   ```bash
   python manage.py migrate whatsapp_headless
   # atau Odoo equivalent
   ```

2. **Restart Odoo Service**:
   ```bash
   # Stop & start Odoo
   ```

3. **Test dengan Webhook Baru**:
   ```bash
   curl -X POST http://localhost:8069/api/wa/webhook \
     -H "Content-Type: application/json" \
     -d '{
       "isFromMe": false,
       "sender": "6285920524227",
       "phone": "6281805314808",
       "message": "test",
       "isGroup": false
     }'
   ```

4. **Verify Database**:
   ```bash
   SELECT sender_number, recipient_number, device_number, direction 
   FROM whatsapp_history 
   ORDER BY create_date DESC LIMIT 5;
   ```

✅ **Done!**
