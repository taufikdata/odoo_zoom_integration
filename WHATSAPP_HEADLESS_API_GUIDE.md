# WhatsApp Headless MVP - API Documentation & Testing Guide

## 📋 Overview

WhatsApp Headless adalah sistem backend di Odoo yang digunakan untuk:
- **Menerima pesan** dari WhatsApp (via Webhook)
- **Menyimpan log chat** di database Odoo
- **Menyediakan REST API** untuk client apps untuk query data
- **Integrasi CRM** - menghubungkan chat dengan contacts dan leads

**Status**: MVP Ready untuk Testing dengan Postman

---

## 🏗️ Architecture

```
WhatsApp Provider (Fonnte/etc)
        ↓
  Webhook POST /api/wa/webhook
        ↓
   Parse & Save to Database
        ↓
  whatsapp.history model
        ↓
REST API GET endpoints ← Client Apps
```

---

## 📡 API Endpoints

### 1. **POST** - Receive Webhook Message
```
POST /api/wa/webhook
Content-Type: application/json

Body:
{
    "sender": "+62812345678",
    "pushName": "John Doe",
    "message": "Halo, apa kabar?",
    "provider": "fonnte",
    "id": "msg_12345"
}
```

**Response (200 OK):**
```json
{
    "status": "success",
    "message": "Message received",
    "record_id": 42
}
```

**Response (400 Bad Request):**
```json
{
    "status": "error",
    "message": "Missing sender or message"
}
```

---

### 2. **GET** - Get Chat History (dengan filter)
```
GET /api/wa/get_history?phone=+62812345678&limit=50&offset=0
```

**Parameters:**
| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `phone` | string | Phone number for filtering | `+62812345678` |
| `limit` | integer | Max records (default: 100, max: 1000) | `50` |
| `offset` | integer | Pagination offset (default: 0) | `0` |
| `partner_id` | integer | Filter by contact ID | `5` |
| `lead_id` | integer | Filter by CRM lead ID | `10` |
| `direction` | string | Filter: `in` or `out` | `in` |
| `start_date` | string | From date (YYYY-MM-DD) | `2026-02-01` |
| `end_date` | string | To date (YYYY-MM-DD) | `2026-02-09` |

**Response (200 OK):**
```json
{
    "status": "success",
    "count": 3,
    "total": 150,
    "limit": 50,
    "offset": 0,
    "data": [
        {
            "id": 45,
            "time": "2026-02-09 13:34:21",
            "sender_number": "+62812345678",
            "sender_name": "John Doe",
            "message": "Halo, mau booking meeting room",
            "direction": "in",
            "provider": "fonnte",
            "partner_id": 5,
            "partner_name": "John Doe",
            "lead_id": 10,
            "is_processed": false
        }
    ]
}
```

---

### 3. **GET** - Get Full Conversation Thread
```
GET /api/wa/conversation/+62812345678?limit=100
```

Get semua chat messages dengan satu nomor telepon, dalam urutan chronological (oldest first).

**Response:**
```json
{
    "status": "success",
    "phone": "+62812345678",
    "count": 5,
    "messages": [
        {
            "id": 40,
            "time": "2026-02-09 10:15:00",
            "sender_number": "+62812345678",
            "sender_name": "John Doe",
            "message": "Halo Pak",
            "direction": "in",
            "provider": "fonnte"
        }
    ]
}
```

---

### 4. **POST** - Send Message (Queued for sending)
```
POST /api/wa/send_message
Content-Type: application/json

Body:
{
    "phone": "+62812345678",
    "message": "Terima kasih, booking Anda sudah dikonfirmasi"
}
```

**Response:**
```json
{
    "status": "success",
    "message": "Message queued for sending",
    "record_id": 50
}
```

---

### 5. **GET** - Get Statistics
```
GET /api/wa/stats?days=7
```

Get overview statistics dari WhatsApp activity.

**Response:**
```json
{
    "status": "success",
    "total_messages": 245,
    "incoming_messages": 180,
    "outgoing_messages": 65,
    "messages_last_7_days": 42,
    "unique_contacts": 28
}
```

---

## 🧪 Testing with Postman

### Setup Postman Collection

#### 1. **Create New Collection**
- Name: `WhatsApp Headless MVP`
- Base URL: `http://localhost:8069` (sesuaikan dengan server Anda)

---

### Test 1: Send Webhook (Simulate WhatsApp message)

**Request Details:**
```
Method: POST
URL: {{base_url}}/api/wa/webhook
Headers:
  Content-Type: application/json

Body (raw JSON):
{
    "sender": "+62812345678",
    "pushName": "Budi Santoso",
    "message": "Halo, saya mau booking meeting room untuk rapat tim",
    "provider": "fonnte",
    "id": "WAM.{{$randomInt}}"
}
```

**Expected Response (200):**
```json
{
    "status": "success",
    "message": "Message received",
    "record_id": XX
}
```

⚠️ **Perhatian:** Setiap kali webhook dipanggil, akan membuat record baru di database.

---

### Test 2: Get History dengan Filter Phone

**Request Details:**
```
Method: GET
URL: {{base_url}}/api/wa/get_history?phone=%2B62812345678&limit=20
```

(URL-encoded: `+` menjadi `%2B`)

**Expected Response (200):**
```json
{
    "status": "success",
    "count": 3,
    "total": 3,
    "limit": 20,
    "offset": 0,
    "data": [ ... ]
}
```

---

### Test 3: Get Conversation Thread

**Request Details:**
```
Method: GET
URL: {{base_url}}/api/wa/conversation/%2B62812345678
Parameters:
  limit=100
```

**Expected Response:**
Semua messages dengan contact tersebut, urut dari oldest to newest for reading full thread.

---

### Test 4: Get Statistics

**Request Details:**
```
Method: GET
URL: {{base_url}}/api/wa/stats?days=7
```

**Expected Response (200):**
```json
{
    "status": "success",
    "total_messages": 42,
    "incoming_messages": 30,
    "outgoing_messages": 12,
    "messages_last_7_days": 42,
    "unique_contacts": 15
}
```

---

### Test 5: Multiple Webhooks (Batch Test)

Kirim 3-5 webhook messages untuk test batch processing:

**Webhook 1:**
```json
{
    "sender": "+62812345678",
    "pushName": "John Doe",
    "message": "Booking untuk Rabu jam 10 pagi",
    "provider": "fonnte"
}
```

**Webhook 2:**
```json
{
    "sender": "+62887654321",
    "pushName": "Jane Smith",
    "message": "Apakah meeting room tersedia hari ini?",
    "provider": "fonnte"
}
```

Kemudian GET `/api/wa/stats?days=1` untuk lihat update statistics.

---

## 🔒 Security & Access Control

### Current Access Configuration:
```csv
access_whatsapp_history,whatsapp.history,model_whatsapp_history,base.group_user,1,1,1,1
access_whatsapp_history_public,whatsapp.history,model_whatsapp_history,,1,1,1,0
```

- **Authenticated Users**: Read/Write/Create/Delete
- **Public (API)**: Read only (via auth='public')

### Best Practices:
1. **Webhook** - Ganti `auth='public'` dengan API token authentication untuk production
2. **GET endpoints** - Implementasikan API key validation
3. **Database** - Sensitive data di raw_data field, implement encryption jika perlu

---

## 🔌 Integration dengan Fonnte (atau WhatsApp Provider lain)

### Setup Fonnte Webhook

1. Login ke Fonnte Dashboard
2. Pergi ke **Webhook/Integration Settings**
3. Set webhook URL:
   ```
   https://your-odoo-domain.com/api/wa/webhook
   ```
4. Method: `POST`
5. Format: JSON
6. Test dengan sample message

### Expected Fonnte Webhook Payload:
```json
{
    "sender": "62812345678",
    "pushName": "Customer Name",
    "message": "Message text here",
    "id": "WAM.x-xxxxx-xxxxx",
    "timestamp": 1644404061
}
```

**Our API akan handle** berbagai format dengan fallback keys.

---

## 📊 Database Schema

### `whatsapp.history` Model Fields:

| Field | Type | Description |
|-------|------|-------------|
| `sender_number` | Char | Phone number pengirim |
| `sender_name` | Char | Nama pengirim |
| `message` | Text | Isi pesan |
| `direction` | Selection | `in` (incoming) atau `out` (outgoing) |
| `partner_id` | Many2one | Link ke Contact/Partner di Odoo |
| `lead_id` | Many2one | Link ke Sales Lead untuk CRM tracking |
| `provider` | Selection | Source: `fonnte`, `webhook`, `odoo`, `other` |
| `message_id` | Char | Unique ID dari provider |
| `raw_data` | Text | Raw JSON payload (untuk debug) |
| `is_processed` | Boolean | Flag untuk tracking business logic |
| `processed_date` | Datetime | Timestamp saat diproses |
| `create_date` | Datetime | Timestamp penerimaan pesan |

---

## 🚀 Deployment Steps

### 1. Restart Odoo Service
```bash
# Stop container
docker-compose down

# Start container
docker-compose up -d

# Check module installation
docker-compose logs -f web_1 | grep -i whatsapp
```

### 2. Verify API Endpoints
```bash
# Test webhook
curl -X POST http://localhost:8069/api/wa/webhook \
  -H "Content-Type: application/json" \
  -d '{"sender":"+62812345678","message":"Test"}'

# Test get history
curl http://localhost:8069/api/wa/get_history
```

### 3. Check Database
Via Odoo UI:
1. Go to **WhatsApp Headless → Chat History**
2. Should see incoming messages

---

## 🐛 Troubleshooting

### Issue: Webhook returns 500 error
**Solution:**
1. Check Odoo logs: `docker-compose logs -f web_1`
2. Verify model access permissions
3. Check if field names match expected payload

### Issue: GET returns empty data
**Solution:**
1. Ensure webhook was successfully saved (check logs)
2. Verify phone number format consistency
3. Check date filters jika menggunakan date range

### Issue: Partner not auto-created
**Solution:**
1. Check `contacts` module is installed
2. Verify phone number format (must be string, not integer)
3. Check access permissions on res.partner model

---

## 📝 Sample Postman Import (JSON)

```json
{
  "info": {
    "name": "WhatsApp Headless MVP",
    "description": "API Collection for testing WhatsApp integration"
  },
  "item": [
    {
      "name": "Send Webhook",
      "request": {
        "method": "POST",
        "header": [{"key": "Content-Type", "value": "application/json"}],
        "body": {"mode": "raw", "raw": "{...}"},
        "url": {"raw": "{{base_url}}/api/wa/webhook", "host": ["{{base_url}}"], "path": ["api", "wa", "webhook"]}
      }
    },
    {
      "name": "Get History",
      "request": {
        "method": "GET",
        "url": {"raw": "{{base_url}}/api/wa/get_history?phone=%2B62812345678", "host": ["{{base_url}}"], "path": ["api", "wa", "get_history"]}
      }
    }
  ],
  "variable": [
    {"key": "base_url", "value": "http://localhost:8069"}
  ]
}
```

---

## ✅ MVP Acceptance Criteria

- [x] Webhook endpoint receives WhatsApp messages
- [x] Messages saved to database with full metadata
- [x] GET API returns chat history with filters
- [x] Conversation thread retrieval (chronological)
- [x] Auto-link to contacts/partners
- [x] CRM lead tracking support
- [x] Statistics endpoint for monitoring
- [x] Proper error handling & logging
- [x] API documentation complete

---

## 📞 Support & Next Steps

### For Demo (Rabu/Kamis):
1. Setup Fonnte account + connect webhook
2. Send test messages from WhatsApp
3. Demo GET API via Postman showing real messages
4. Demo CRM integration showing linked leads

### For Production:
1. Implement API token authentication
2. Add database encryption for sensitive data
3. Setup message queue for bulk sends
4. Implement WhatsApp provider API for outgoing messages
5. Add audit logging & compliance features

---

**Last Updated**: 9 Feb 2026  
**Status**: MVP - Ready for Testing  
**Next Phase**: Production Hardening & WhatsApp Provider Integration
