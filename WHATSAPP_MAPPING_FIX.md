# WhatsApp Headless Mapping Fix - February 20, 2026

## Masalah yang Diperbaiki

**Issue**: Untuk pesan outgoing (direction: "out"), field `sender_number` menunjukkan nomor customer, padahal seharusnya menunjukkan nomor device/perangkat kita yang mengirim.

**Contoh Error Sebelumnya**:
```json
{
  "id": 114,
  "time": "2026-02-20 02:22:06",
  "sender_number": "6281805314808",  // ❌ Ini adalah customer/recipient, bukan pengirim
  "sender_name": "Unknown",
  "message": "selamat pagi pak...",
  "direction": "out"  // ✓ Arah benar, tapi sender_number salah
}
```

---

## Solusi: Correct Mapping dari Wablas API

### Wablas Webhook Fields
```python
{
  "isFromMe": true/false,      # Adalah pesan dari device kita?
  "sender": "6285920524227",   # Nomor device/gateway Wablas (ALWAYS our device)
  "phone": "6281805314808",    # Nomor lawan chat (the other person/group)
  "isGroup": true/false,       # Apakah group message?
  ...
}
```

### Mapping Logic (CORRECT)

#### 1. INCOMING MESSAGE (`isFromMe: false`)
```
Scenario: Customer mengirim pesan ke kita

Wablas Fields:
  - sender: "6285920524227"  (device kita)
  - phone: "6281805314808"   (customer)
  - isFromMe: false

Mapping:
  ✅ sender_number = phone (6281805314808)  → Customer adalah yang MENGIRIM
  ✅ recipient_number = sender (6285920524227)  → Kita adalah yang MENERIMA
  ✅ device_number = sender (6285920524227)
  ✅ direction = "in"
```

#### 2. OUTGOING MESSAGE (`isFromMe: true`)
```
Scenario: Kita mengirim pesan ke customer

Wablas Fields:
  - sender: "6285920524227"  (device kita)
  - phone: "6281805314808"   (customer)
  - isFromMe: true

Mapping:
  ✅ sender_number = sender (6285920524227)  → KITA/Device adalah yang MENGIRIM
  ✅ recipient_number = phone (6281805314808)  → Customer adalah yang MENERIMA
  ✅ device_number = sender (6285920524227)
  ✅ direction = "out"
```

---

## Hasil Setelah Fix

### Incoming Message
```json
{
  "id": 115,
  "time": "2026-02-20 02:22:13",
  "sender_number": "6281805314808",     // ✅ Customer (pengirim)
  "recipient_number": "6285920524227",  // ✅ Device kita (penerima)
  "device_number": "6285920524227",     // ✅ Device kita
  "sender_name": "Customer Name",
  "message": "bisa",
  "direction": "in"                     // ✅ Masuk dari customer
}
```

### Outgoing Message
```json
{
  "id": 114,
  "time": "2026-02-20 02:22:06",
  "sender_number": "6285920524227",     // ✅ Device kita (pengirim)
  "recipient_number": "6281805314808",  // ✅ Customer (penerima)
  "device_number": "6285920524227",     // ✅ Device kita
  "sender_name": "Odoo System",
  "message": "selamat pagi pak...",
  "direction": "out"                    // ✅ Keluar dari kita ke customer
}
```

---

## Database Schema Changes

### Field Baru di `whatsapp.history` Model:

```python
recipient_number = fields.Char(
    string='Nomor Penerima',
    index=True
)

device_number = fields.Char(
    string='Nomor Device/Gateway',
    index=True
)

is_group = fields.Boolean(
    string='Pesan Group?',
    default=False
)
```

### Migration SQL (jika diperlukan):
```sql
ALTER TABLE whatsapp_history ADD COLUMN recipient_number VARCHAR(20);
ALTER TABLE whatsapp_history ADD COLUMN device_number VARCHAR(20);
ALTER TABLE whatsapp_history ADD COLUMN is_group BOOLEAN DEFAULT FALSE;

CREATE INDEX idx_recipient_number ON whatsapp_history(recipient_number);
CREATE INDEX idx_device_number ON whatsapp_history(device_number);
```

---

## Code Changes

### File: `whatsapp_headless/models/wa_history.py`
- ✅ Tambah 3 field baru: `recipient_number`, `device_number`, `is_group`

### File: `whatsapp_headless/controllers/main.py`

#### 1. `_extract_sender_info()` method
- **Before**: Return 3 values → `(sender_number, sender_name, direction)`
- **After**: Return 6 values → `(sender_number, recipient_number, device_number, sender_name, direction, is_group)`
- **Logic**: Fix mapping untuk incoming/outgoing

#### 2. `receive_webhook()` method
- ✅ Update untuk menyimpan 3 field nomor (sender, recipient, device)
- ✅ Update log message untuk menunjukkan flow yang benar

#### 3. `send_message()` method
- ✅ Fix: `sender_number` = device_number (bukan phone)
- ✅ Tambah parameter optional `device_number` di request body

---

## API Usage Examples

### Receiving Webhook (Wablas)
```bash
POST /api/wa/webhook
Content-Type: application/json

# Incoming message dari customer
{
  "isFromMe": false,
  "sender": "6285920524227",
  "phone": "6281805314808",
  "message": "Pak, apakah bisa jam 2 siang?",
  "isGroup": false
}

# Response akan menyimpan:
{
  "direction": "in",
  "sender_number": "6281805314808",      // Customer
  "recipient_number": "6285920524227",   // Device kita
  "device_number": "6285920524227"
}
```

### Sending Message via API
```bash
POST /api/wa/send_message
Content-Type: application/json

{
  "phone": "6281805314808",
  "message": "Baik Pak, jam 2 OK",
  "device_number": "6285920524227"  // Optional, bisa auto-detect
}

# Disimpan sebagai:
{
  "direction": "out",
  "sender_number": "6285920524227",      // Device kita
  "recipient_number": "6281805314808",   // Customer
  "device_number": "6285920524227"
}
```

---

## Testing

Sebelum deploy ke production:

1. **Check Database**: Pastikan migration sudah berjalan
   ```sql
   SELECT * FROM whatsapp_history LIMIT 5;
   ```

2. **Test Webhook**: Kirim test message via Wablas
   ```bash
   curl -X POST http://localhost:8069/api/wa/webhook \
     -H "Content-Type: application/json" \
     -d '{
       "isFromMe": false,
       "sender": "6285920524227",
       "phone": "6281805314808",
       "message": "test incoming",
       "isGroup": false
     }'
   ```

3. **Check Results**: Verify di API
   ```bash
   curl http://localhost:8069/api/wa/get_history?phone=6281805314808
   ```

4. **Validate**:
   - ✅ Incoming messages: `direction=in`, `sender_number=customer`
   - ✅ Outgoing messages: `direction=out`, `sender_number=device`
   - ✅ `recipient_number` selalu berlawanan dengan `sender_number`
   - ✅ `device_number` selalu sama untuk semua pesan (nomor device kita)

---

## Notes

- **Backward Compatibility**: Old data tetap ada tapi field `recipient_number` dan `device_number` akan kosong
- **Future Enhancement**: Bisa tambah `partner_id` field untuk automatic matching dengan res.partner
- **Multi Device**: Jika ada multiple devices, `device_number` akan berbeda-beda per device
