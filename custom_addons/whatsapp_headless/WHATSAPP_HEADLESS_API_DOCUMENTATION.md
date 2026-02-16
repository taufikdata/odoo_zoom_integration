# WhatsApp Headless API - Complete Documentation

**Last Updated:** February 16, 2026  
**Version:** 1.0  
**Status:** Production Ready

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Installation & Setup](#installation--setup)
4. [API Endpoints](#api-endpoints)
5. [Webhook Configuration](#webhook-configuration)
6. [Request/Response Format](#requestresponse-format)
7. [Integration Guide](#integration-guide)
8. [Error Handling](#error-handling)
9. [Examples](#examples)
10. [Troubleshooting](#troubleshooting)

---

## 🎯 Overview

WhatsApp Headless adalah modul Odoo yang berfungsi sebagai **Backend API untuk mengelola WhatsApp messages** dari Wablas tanpa UI.

**Kegunaan:**
- Receive WhatsApp messages dari Wablas via webhook
- Store messages di database
- Retrieve message history dengan filtering & pagination
- Statistics & analytics
- Integration dengan sistem third-party

**Architecture:**
```
Wablas (Provider) 
    ↓ (HTTP POST Webhook)
Ngrok (Public URL Tunnel)
    ↓
Odoo WhatsApp Headless Module
    ↓ (REST API)
Sistem Pihak Ketiga (Your Application)
```

---

## 🏗️ Architecture

### Components

```
┌─────────────────────────────────────────────────────┐
│              WABLAS PROVIDER                        │
│  - Receive WhatsApp messages                       │
│  - Forward via Webhook                              │
└────────────────┬────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────┐
│         NGROK / PUBLIC TUNNEL                       │
│  - Expose localhost:8077 to internet                │
│  - URL: https://xxx.ngrok.io                       │
└────────────────┬────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────┐
│       ODOO WHATSAPP HEADLESS MODULE                 │
│  ├─ Webhook Receiver (/api/wa/webhook)            │
│  ├─ Message Storage (whatsapp_history table)       │
│  ├─ REST API Endpoints                             │
│  └─ Contact Lookup (res.partner)                   │
└────────────────┬────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────┐
│      YOUR THIRD-PARTY APPLICATION                  │
│  - Query messages via REST API                     │
│  - Process & store locally                         │
│  - Implement custom logic                          │
└─────────────────────────────────────────────────────┘
```

---

## 🚀 Installation & Setup

### Prerequisites

1. **Odoo 13+** dengan custom addons support
2. **Docker & Docker Compose** (untuk deployment)
3. **Wablas Account** (WhatsApp API provider)
4. **Ngrok** (untuk expose localhost ke internet)
5. **PostgreSQL** (database)

### Step 1: Copy Module

```bash
cp -r custom_addons/whatsapp_headless /path/to/odoo/custom_addons/
```

### Step 2: Install Module di Odoo

```bash
# Restart Odoo untuk scan modul baru
docker-compose restart web

# Login ke Odoo → Apps
# Search: "whatsapp_headless"
# Klik Install
```

### Step 3: Verify Installation

```bash
curl http://localhost:8077/api/wa/get_history
# Response: {"status": "success", "data": [], ...}
```

### Step 4: Setup Ngrok (For Wablas Webhook)

```bash
# Install ngrok: https://ngrok.com/download
# Terminal baru, run:
ngrok http 8077

# Output:
# Forwarding    https://abc12345.ngrok.io -> http://localhost:8077
```

### Step 5: Configure Wablas Webhook

1. Login ke **Wablas Dashboard**
2. Go to **Settings → Webhook**
3. Fill webhook URL: `https://abc12345.ngrok.io/api/wa/webhook`
4. Test webhook
5. Turn ON/Enable

---

## 🔌 API Endpoints

### 1. Receive Webhook (Internal - Wablas → Odoo)

```
POST /api/wa/webhook
Auth: public (no token needed)
Content-Type: application/json
```

**Description:** Wablas sends messages here. You don't call this directly.

**Wablas sends:**
```json
{
  "id": "uuid",
  "phone": "6285137033257",
  "sender": "6285920524227",
  "pushName": "6285137033257@s.whatsapp.net",
  "message": "Hello world",
  "isGroup": false,
  "isFromMe": false,
  "messageType": "text",
  "timestamp": "2026-02-16T07:50:42Z",
  ...
}
```

**Odoo responds:**
```json
{
  "status": "success",
  "message": "Message received",
  "record_id": 76
}
```

---

### 2. Get All Messages

```
GET /api/wa/get_history
Auth: public
Query Parameters:
  - phone (optional): Filter by phone number
  - limit (optional): Max results (default 100, max 1000)
  - offset (optional): Pagination offset (default 0)
```

**Example Request:**
```bash
curl "http://localhost:8077/api/wa/get_history?limit=50&offset=0"
```

**Response:**
```json
{
  "status": "success",
  "count": 2,
  "total": 76,
  "limit": 50,
  "offset": 0,
  "data": [
    {
      "id": 82,
      "time": "2026-02-16 07:51:30",
      "sender_number": "6285137033257",
      "sender_name": "Unknown",
      "message": "sudah mi ka",
      "direction": "in"
    },
    {
      "id": 76,
      "time": "2026-02-16 07:50:40",
      "sender_number": "6281527959017",
      "sender_name": "Unknown",
      "message": "lapar banget ee",
      "direction": "out"
    }
  ]
}
```

---

### 3. Get Conversation with Contact

```
GET /api/wa/conversation/<phone>
Auth: public
Path Parameters:
  - phone: WhatsApp phone number (e.g., 6285137033257)
Query Parameters:
  - limit (optional): Max results (default 100)
```

**Example Request:**
```bash
curl "http://localhost:8077/api/wa/conversation/6285137033257?limit=50"
```

**Response:**
```json
{
  "status": "success",
  "phone": "6285137033257",
  "count": 5,
  "messages": [
    {
      "id": 82,
      "time": "2026-02-16 07:51:30",
      "sender_number": "6285137033257",
      "sender_name": "Unknown",
      "message": "sudah mi ka",
      "direction": "in"
    },
    ...
  ]
}
```

---

### 4. Get Statistics

```
GET /api/wa/stats
Auth: public
Query Parameters:
  - days (optional): Time range in days (default 7)
```

**Example Request:**
```bash
curl "http://localhost:8077/api/wa/stats?days=30"
```

**Response:**
```json
{
  "status": "success",
  "total_messages": 82,
  "incoming_messages": 45,
  "outgoing_messages": 37,
  "messages_last_30_days": 82,
  "unique_contacts": 12
}
```

---

### 5. Send Message (Future - Not Yet Implemented)

```
POST /api/wa/send_message
Auth: public
Content-Type: application/json
```

**Request:**
```json
{
  "phone": "6285137033257",
  "message": "Hello from Odoo"
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Message queued for sending",
  "record_id": 83
}
```

**Note:** Currently only stores the message. Actual sending via Wablas API needs to be implemented.

---

## 🔗 Webhook Configuration

### Wablas Webhook Format

Wablas sends **HTTP POST** to your webhook URL with JSON payload:

```json
{
  "id": "uuid-string",
  "pushName": "6285137033257@s.whatsapp.net",
  "isGroup": false,
  "group": {
    "group_id": "",
    "sender": "",
    "subject": "",
    "owner": "",
    "desc": "",
    "participants": null
  },
  "message": "Hello",
  "phone": "6285137033257",
  "messageType": "text",
  "file": "",
  "url": "",
  "mimeType": "",
  "deviceId": "RF0WVV",
  "sender": "6285920524227",
  "isFromMe": false,
  "timestamp": "2026-02-16T07:50:42Z",
  "profileImage": "https://...",
  "ticketId": "uuid",
  "assigned": "uuid"
}
```

### Field Explanation

| Field | Type | Description |
|-------|------|-------------|
| `phone` | string | Contact phone number (sender for incoming, recipient for outgoing) |
| `sender` | string | Device phone number (always the Wablas connected device) |
| `message` | string | Message text content |
| `isFromMe` | boolean | `true` = outgoing, `false` = incoming |
| `isGroup` | boolean | `true` = group message, `false` = direct message |
| `pushName` | string | Contact name/identifier (often just phone format now) |
| `messageType` | string | `text`, `image`, `document`, etc. |
| `timestamp` | string | ISO 8601 timestamp |
| `deviceId` | string | Wablas device identifier |

---

## 📥 Request/Response Format

### Data Storage in Odoo

Messages stored in `whatsapp_history` table:

| Column | Type | Description |
|--------|------|-------------|
| `id` | int | Auto-increment primary key |
| `sender_number` | varchar | Contact phone (person in conversation) |
| `sender_name` | varchar | Contact name (fallback: "Unknown") |
| `message` | text | Message content |
| `direction` | varchar | `in` (received) or `out` (sent) |
| `raw_data` | text | Full JSON from Wablas |
| `create_date` | timestamp | When message was created |
| `write_date` | timestamp | Last update |

### Contact Name Lookup

For **incoming messages**, name is looked up from Odoo Contacts (`res.partner`):

```python
# Search in res.partner by phone or mobile field
partner = env['res.partner'].search([
    '|',
    ('phone', 'like', cleaned_phone),
    ('mobile', 'like', cleaned_phone)
])
```

If found → use `partner.name`  
If not found → use `"Unknown"`

**Important:** Add contacts to Odoo Contacts module with correct phone numbers to see names.

---

## 🔗 Integration Guide

### For Third-Party Applications

#### Option 1: Direct REST API Calls

**Node.js / JavaScript Example:**

```javascript
const axios = require('axios');

const ODOO_API_URL = 'http://localhost:8077';

// Get all messages
async function getMessages() {
  try {
    const response = await axios.get(`${ODOO_API_URL}/api/wa/get_history`, {
      params: {
        limit: 100,
        offset: 0
      }
    });
    console.log(response.data);
  } catch (error) {
    console.error('Error:', error.message);
  }
}

// Get conversation with specific contact
async function getConversation(phone) {
  try {
    const response = await axios.get(
      `${ODOO_API_URL}/api/wa/conversation/${phone}`,
      { params: { limit: 50 } }
    );
    console.log(response.data);
  } catch (error) {
    console.error('Error:', error.message);
  }
}

// Get statistics
async function getStats() {
  try {
    const response = await axios.get(`${ODOO_API_URL}/api/wa/stats`, {
      params: { days: 30 }
    });
    console.log(response.data);
  } catch (error) {
    console.error('Error:', error.message);
  }
}

getMessages();
getConversation('6285137033257');
getStats();
```

**Python Example:**

```python
import requests
import json

ODOO_API_URL = 'http://localhost:8077'

# Get all messages
response = requests.get(f'{ODOO_API_URL}/api/wa/get_history', params={
    'limit': 100,
    'offset': 0
})
print(json.dumps(response.json(), indent=2))

# Get conversation
phone = '6285137033257'
response = requests.get(f'{ODOO_API_URL}/api/wa/conversation/{phone}', params={
    'limit': 50
})
print(json.dumps(response.json(), indent=2))

# Get stats
response = requests.get(f'{ODOO_API_URL}/api/wa/stats', params={
    'days': 30
})
print(json.dumps(response.json(), indent=2))
```

**cURL Examples:**

```bash
# Get messages
curl "http://localhost:8077/api/wa/get_history?limit=100&offset=0"

# Get conversation
curl "http://localhost:8077/api/wa/conversation/6285137033257?limit=50"

# Get stats
curl "http://localhost:8077/api/wa/stats?days=30"
```

---

#### Option 2: Polling (Periodic Sync)

Implement polling in your application to regularly fetch messages:

```python
import requests
import time
import json

ODOO_API_URL = 'http://localhost:8077'
POLL_INTERVAL = 60  # 1 minute

def sync_messages():
    """Periodically sync messages from Odoo"""
    while True:
        try:
            response = requests.get(
                f'{ODOO_API_URL}/api/wa/get_history',
                params={'limit': 1000}
            )
            
            if response.status_code == 200:
                data = response.json()
                messages = data.get('data', [])
                
                # Process messages
                for msg in messages:
                    process_message(msg)
                
                print(f"Synced {len(messages)} messages")
            else:
                print(f"Error: {response.status_code}")
                
        except Exception as e:
            print(f"Sync error: {str(e)}")
        
        # Wait before next sync
        time.sleep(POLL_INTERVAL)

def process_message(msg):
    """Your custom logic"""
    print(f"From: {msg['sender_number']}")
    print(f"Name: {msg['sender_name']}")
    print(f"Message: {msg['message']}")
    print(f"Direction: {msg['direction']}")
    print("---")

# Start polling
sync_messages()
```

---

#### Option 3: Webhook Forward (Push to Your System)

Setup reverse webhook - when Wablas sends to Odoo, Odoo forwards to your system:

**Modify Odoo Controller** (`/custom_addons/whatsapp_headless/controllers/main.py`):

```python
def receive_webhook(self):
    """... existing code ..."""
    
    # Save to database
    msg_record = request.env['whatsapp.history'].sudo().create({...})
    
    # NEW: Forward to your system
    try:
        your_system_url = 'https://your-app.com/webhook/whatsapp'
        webhook_data = {
            'id': msg_record.id,
            'sender_number': sender,
            'sender_name': name,
            'message': message,
            'direction': direction,
            'timestamp': datetime.now().isoformat()
        }
        requests.post(your_system_url, json=webhook_data, timeout=5)
    except Exception as e:
        _logger.warning(f"Failed to forward webhook: {str(e)}")
    
    return {'status': 'success', 'record_id': msg_record.id}
```

---

### Data Flow Diagram

```
Wablas
  ↓ (webhook with phone, message, etc.)
Odoo Headless
  ├─ Parse data
  ├─ Lookup contact name
  ├─ Store in DB
  └─ Respond 200 OK
    
Your App (pulls data)
  ├─ GET /api/wa/get_history
  ├─ Parse response
  ├─ Process locally
  └─ Store in your DB

Real-Time Processing:
Wablas → Odoo → (Your App via webhook forward)
```

---

## ❌ Error Handling

### API Error Responses

**Missing Parameters:**
```json
{
  "status": "error",
  "message": "Missing required parameter: phone"
}
```

**Invalid Phone:**
```json
{
  "status": "error",
  "message": "Phone number format invalid"
}
```

**Database Error:**
```json
{
  "status": "error",
  "message": "Database error: ..."
}
```

**Server Error (500):**
```json
{
  "status": "error",
  "message": "Internal server error"
}
```

### HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Bad request / Invalid params |
| 401 | Unauthorized (if auth required) |
| 404 | Not found |
| 500 | Server error |

### Error Handling in Client

```python
import requests

try:
    response = requests.get('http://localhost:8077/api/wa/get_history')
    response.raise_for_status()  # Raise exception for bad status
    
    data = response.json()
    
    if data.get('status') == 'error':
        print(f"API Error: {data.get('message')}")
    else:
        messages = data.get('data', [])
        # Process messages
        
except requests.exceptions.ConnectionError:
    print("Cannot connect to Odoo")
except requests.exceptions.Timeout:
    print("Request timeout")
except requests.exceptions.RequestException as e:
    print(f"Request error: {e}")
except json.JSONDecodeError:
    print("Invalid JSON response")
```

---

## 📝 Examples

### Complete Integration Example (Python)

```python
import requests
import json
from datetime import datetime
from typing import List, Dict, Optional

class OdooWhatsAppClient:
    """WhatsApp Headless API Client"""
    
    def __init__(self, base_url: str = 'http://localhost:8077'):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.timeout = 10
    
    def get_history(self, phone: Optional[str] = None, 
                   limit: int = 100, offset: int = 0) -> Dict:
        """Get message history"""
        try:
            params = {'limit': limit, 'offset': offset}
            if phone:
                params['phone'] = phone
            
            response = self.session.get(
                f'{self.base_url}/api/wa/get_history',
                params=params
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def get_conversation(self, phone: str, limit: int = 100) -> Dict:
        """Get full conversation with a contact"""
        try:
            response = self.session.get(
                f'{self.base_url}/api/wa/conversation/{phone}',
                params={'limit': limit}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def get_stats(self, days: int = 7) -> Dict:
        """Get statistics"""
        try:
            response = self.session.get(
                f'{self.base_url}/api/wa/stats',
                params={'days': days}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def process_and_store(self, messages: List[Dict]):
        """
        Example: Process messages and store in your system
        """
        for msg in messages:
            record = {
                'odoo_id': msg['id'],
                'phone': msg['sender_number'],
                'contact_name': msg['sender_name'],
                'text': msg['message'],
                'type': msg['direction'],
                'received_at': msg['time'],
                'stored_at': datetime.now().isoformat()
            }
            
            # Save to your database
            self.save_to_db(record)
    
    def save_to_db(self, record: Dict):
        """Your custom database save logic"""
        print(f"Saving: {record}")
        # TODO: Implement your database save

# Usage
if __name__ == '__main__':
    client = OdooWhatsAppClient()
    
    # Get all messages
    print("Fetching messages...")
    result = client.get_history(limit=50)
    
    if result['status'] == 'success':
        print(f"Total messages: {result['total']}")
        print(f"Retrieved: {result['count']}")
        
        messages = result['data']
        client.process_and_store(messages)
    else:
        print(f"Error: {result['message']}")
    
    # Get conversation with specific contact
    print("\nFetching conversation...")
    conv = client.get_conversation('6285137033257')
    print(json.dumps(conv, indent=2))
    
    # Get statistics
    print("\nFetching statistics...")
    stats = client.get_stats(days=30)
    print(json.dumps(stats, indent=2))
```

---

### Setup for Heroku/Cloud Deployment

```bash
# 1. Keep ngrok running or use ngrok authtoken for permanent URL
export NGROK_AUTHTOKEN=your_token_here

# 2. Update Wablas Webhook URL to your production URL
# Settings → Webhook → URL: https://your-production-domain.com/api/wa/webhook

# 3. Setup API authentication (recommended for production)
# Edit controller to require API token in headers

# 4. Setup CORS if needed
# Allow third-party requests to `/api/wa/` endpoints

# 5. Setup rate limiting
# Prevent abuse of API endpoints
```

---

## 🔧 Troubleshooting

### Webhook tidak receive messages

**Problem:** Wablas tidak mengirim ke webhook

**Solutions:**
1. Verify ngrok is running: `ngrok http 8077`
2. Check Wablas webhook URL correct: `https://xxx.ngrok.io/api/wa/webhook`
3. Test webhook di Wablas dashboard → "Send Test"
4. Check Odoo logs: `docker-compose logs web | grep "WA Webhook"`

**Debug:** 
```bash
# Check if webhook is callable
curl -X POST http://localhost:8077/api/wa/webhook \
  -H "Content-Type: application/json" \
  -d '{"phone":"6285137033257","message":"test","isFromMe":false,"sender":"6285920524227"}'
```

### Messages tidak terlihat di API

**Problem:** GET /api/wa/get_history returns empty

**Solutions:**
1. Verify webhook was processed: check logs
2. Check database: `SELECT COUNT(*) FROM whatsapp_history;`
3. Verify Odoo module installed: Apps → search "whatsapp_headless" → see if green checkmark

### Contact names showing "Unknown"

**Problem:** sender_name always "Unknown"

**Solutions:**
1. Add contacts to Odoo: Contacts → Create
2. Fill phone/mobile with WhatsApp number
3. New messages will lookup from Contacts
4. For old messages: query will return "Unknown" (expected)

### Timeout when querying large datasets

**Problem:** API returns 504 timeout

**Solutions:**
1. Use pagination: `?limit=100&offset=0`
2. Add database index: `CREATE INDEX idx_wh_create_date ON whatsapp_history(create_date);`
3. Archive old messages to separate table

---

## 🔐 Security Recommendations

### For Production:

1. **Enable API Authentication**
   ```python
   def receive_webhook(self):
       api_key = request.headers.get('Authorization', '')
       if api_key != 'Bearer your-secret-key':
           return {'status': 'error', 'message': 'Unauthorized'}, 401
   ```

2. **Setup CORS**
   ```python
   response.headers['Access-Control-Allow-Origin'] = 'https://your-app.com'
   response.headers['Access-Control-Allow-Methods'] = 'GET, POST'
   ```

3. **Rate Limiting**
   - Limit API calls per IP
   - Prevent webhook spam

4. **HTTPS**
   - Always use HTTPS in production
   - Update webhook URL to https://

5. **Database Backup**
   - Regular backup of `whatsapp_history` table
   - Test restore procedure

---

## 📞 Support & Contact

- **Wablas Support:** support@wablas.com
- **Odoo Community:** forum.odoo.com
- **Issue Tracking:** Check GitHub/GitLab

---

**End of Documentation**
