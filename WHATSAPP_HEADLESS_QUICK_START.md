# WhatsApp Headless MVP - Quick Start Guide

**Untuk Demo Rabu/Kamis**

---

## ⚠️ PENTING: Kenapa Chat Teman Gak Muncul di Odoo?

**Jawab singkat:** Sistem backend Odoo sudah siap, **TAPI belum terhubung ke WhatsApp provider** (Fonnte).

### Analogi Mudah Dipahami:

```
Bayangkan Odoo seperti RUMAH KOSONG dengan:
✅ Pintu sudah ada (webhook endpoint siap terima pesan)
✅ Kamar tidur sudah ada (database ready simpan pesan)
✅ Ruang tamu sudah ada (REST API siap query)
❌ TAPI BELUM ADA JEMBATAN DARI JALAN KE RUMAH ← INI YANG KURANG!

Fonnte = JEMBATAN yang menghubungkan WhatsApp ke Odoo!

Alur Nyata Seharusnya:
1. Teman kirim chat di WhatsApp
2. WhatsApp server → kirim ke Fonnte
3. Fonnte → kirim ke Odoo webhook
4. Odoo → simpan ke database
5. Chat muncul di Odoo ✅
```

### Status Sekarang (MVP Testing):
- ✅ Odoo siap menerima pesan (webhook working)
- ✅ Database siap simpan (tested dengan curl)
- ✅ API siap query (tested dengan Postman)
- ❌ **Belum connect ke Fonnte** ← Ini yang perlu dilakukan!

---

## 🔗 Setup Fonnte (WAJIB BUAT REAL MESSAGES)

### Step 1: Buat Akun Fonnte (5 menit)

1. Buka https://fonnte.com
2. Klik "Sign Up" atau "Daftar"
3. Isi data:
   - Email: gunakan email valid
   - Password: buat password 
   - Pilih Indonesia (untuk currency)
4. Klik "Register"
5. **PENTING**: Verify email Anda (check inbox)

### Step 2: Connect WhatsApp ke Fonnte (10 menit)

Setelah login ke Fonnte dashboard:

```
1. Di sidebar cari "Device" atau "WhatsApp Account"
2. Klik "Add Device" atau "Connect WhatsApp"
3. Ada 2 pilihan:
   a) Scan QR Code (paling mudah untuk testing)
   b) Link Akun WhatsApp Business (jika punya)
4. Gunakan Scan QR Code - ambil scan dengan WhatsApp Anda
5. Tunggu ~30 detik sampai status jadi "Connected"
```

### Step 3: Setup Webhook ke Odoo (10 menit)

Di Fonnte Dashboard:

```
1. Cari menu "Webhook" atau "Settings" → "Webhook"
2. Klik "Add Webhook" atau "Create New Webhook"
3. Isi form:

   URLs: http://localhost:8077/api/wa/webhook
   
   ⚠️ PENTING: 
   - Jika Odoo pake domain/IP external: gunakan domain itu
   - Jika localhost: TIDAK BISA! Gunakan IP router/VPS
   
   Webhook Events: Pilih "incoming_message"
   
4. Save/Submit
5. Fonnte akan show "Webhook Status: Active" atau "Connected"

Test Webhook:
   - Klik "Send Test" atau tombol test
   - Lihat di Odoo apakah ada pesan masuk
```

**CATATAN PENTING UNTUK LOCALHOST:**
Jika Anda development di laptop dengan localhost:8077:
- Fonnte (server eksternal) TIDAK bisa reach localhost Anda
- Solusi: Gunakan `ngrok` atau `localtunnel` untuk expose Odoo ke internet
  
  ```bash
  # Install ngrok: https://ngrok.com/download
  # Terminal baru:
  ngrok http 8077
  
  # Akan dapat URL seperti: https://xxx-xxx.ngrok.io
  # Gunakan URL itu di Fonnte webhook!
  ```

### Step 4: Test Koneksi (5 menit)

**Test 1: Manual Send via Fonnte Dashboard**
```
1. Di Fonnte, cari "Send Message" atau "Test Message"
2. Kirim pesan test
3. Buka Odoo → WhatsApp Headless → Chat History
4. Lihat apakah pesan muncul di list
```

**Test 2: Chat dari WhatsApp Mobile**
```
1. Buka WhatsApp di HP Anda
2. Chat ke nomor yang terdaftar di Fonnte
3. Tunggu ~5 detik
4. Buka Odoo dashboard
5. Refresh page (F5)
6. Lihat apakah chat muncul di Chat History
```

---

## 🚀 Quick Setup (5 Menit)

### 1. Start Odoo
```bash
cd /home/taufik/odoo_clean_project
docker-compose up -d
sleep 30  # Wait for Odoo to load
```

### 2. Login ke Odoo UI
```
URL: http://localhost:8077
User: admin
Pass: admin
DB: zoom_bersih
```

### 3. Navigate ke WhatsApp Module
```
Menu → WhatsApp Headless → Chat History
```

---

## 📱 Testing dengan Postman

### Setup Postman (1x saja)

1. **Create Collection**: "WhatsApp Headless MVP"
2. **Set Variable**: `{{base_url}}` = `http://localhost:8077`

### Test Case 1: Send Message via Webhook
```
Method: POST
URL: {{base_url}}/api/wa/webhook
Header: Content-Type: application/json

Body:
{
  "sender": "+6281234567890",
  "pushName": "Pak Punian",
  "message": "Apakah ruang meeting sudah tersedia?"
}
```

**Expected Response**:
```json
{
  "status": "success",
  "message": "Message received",
  "record_id": 99
}
```

---

### Test Case 2: Get All Messages
```
Method: GET
URL: {{base_url}}/api/wa/get_history

Headers: None needed
```

**Expected Response**:
```json
{
  "status": "success",
  "count": 5,
  "total": 5,
  "data": [
    {
      "id": 99,
      "time": "2026-02-09 14:30:00",
      "sender_number": "+6281234567890",
      "sender_name": "Pak Punian",
      "message": "Apakah ruang meeting sudah tersedia?",
      "direction": "in"
    }
  ]
}
```

---

### Test Case 3: Get Conversation History (Single Contact)
```
Method: GET
URL: {{base_url}}/api/wa/get_history?phone=%2B6281234567890
```

(Note: `%2B` adalah URL-encoded `+`)

---

### Test Case 4: Get Statistics
```
Method: GET
URL: {{base_url}}/api/wa/stats?days=7
```

**Response**:
```json
{
  "status": "success",
  "total_messages": 25,
  "incoming_messages": 20,
  "outgoing_messages": 5,
  "messages_last_7_days": 15,
  "unique_contacts": 8
}
```

---

## 📊 Live Demo Scenario

**Waktu: 15-20 Menit**

### Phase 1: Kirim Messages via Webhook (3 Min)
1. Buka Postman
2. Kirim 2-3 test messages dengan berbagai nomor WhatsApp
3. Show di UI: Messages muncul di WhatsApp History

### Phase 2: Query Data via REST API (5 Min)
1. GET `/api/wa/get_history` → Show semua messages
2. GET `/api/wa/get_history?phone=...` → Filter specific contact
3. GET `/api/wa/stats` → Show statistics

### Phase 3: Jelaskan Use Case (5-10 Min)
- Sales team bisa integrate WhatsApp ke sistem mereka
- Chat history otomatis tersimpan di Odoo
- Bisa query data via REST API untuk aplikasi custom
- Persiapan untuk CRM integration di fase production

---

## ⚡ Command Reference

### Check Odoo Status
```bash
docker-compose ps
```

### View Logs
```bash
docker-compose logs -f web_1 | grep -i whatsapp
```

### Restart Service
```bash
docker-compose restart web_1
```

### Access Database Directly
```bash
docker-compose exec db psql -U odoo -d zoom_bersih \
  -c "SELECT id, sender_number, sender_name, message FROM whatsapp_history ORDER BY create_date DESC LIMIT 5;"
```

---

## ✅ Cara Memastikan Sistem Sudah Berhasil

### Checklist Verification:

```
STEP 1: Cek Backend Runtime
□ Docker containers running?
  → Run: docker-compose ps
  → Harus ada 2 container: web dan db (Status: Up)

□ Odoo module installed?
  → Buka: http://localhost:8077
  → Login dengan admin/admin
  → Pergi ke: Settings → Modules → search "whatsapp"
  → Harus show "whatsapp_headless" dengan status "Installed"

□ Database table ada?
  → Run command di bawah, harus return 5 columns
  → docker-compose exec db psql -U odoo -d zoom_bersih \
    -c "\d whatsapp_history"

STEP 2: Tes Feature Manual (Tanpa Fonnte)
□ Webhook working?
  → Run command ini di terminal:
    curl -X POST http://localhost:8077/api/wa/webhook \
      -H "Content-Type: application/json" \
      -d '{"sender":"+6281234567","pushName":"Test","message":"Hello"}'
  → Harus return: {"status": "success", ...}

□ API Query working?
  → Run: curl http://localhost:8077/api/wa/get_history
  → Harus return JSON dengan message

□ UI showing messages?
  → Login Odoo → Goto: WhatsApp Headless → Chat History
  → Lihat apakah pesan dari step di atas ada di list

STEP 3: Tes Feature Real (Dengan Fonnte - Wajib Buat Real Messages)
□ Fonnte account created?
  → Buka: https://fonnte.com
  → Check: Device/WhatsApp status "Connected"

□ Webhook registered?
  → Di Fonnte: Settings → Webhook
  → URL: http://your-domain/api/wa/webhook
  → Status: Active/Connected

□ Chat dari HP muncul?
  → Chat dari WhatsApp HP ke nomor Fonnte
  → Tunggu 5 detik
  → Refresh Odoo
  → Lihat apakah chat muncul di Chat History

□ Semua feature working?
  → Filter by phone: GET /api/wa/get_history?phone=+XXX
  → Get stats: GET /api/wa/stats
  → Semua return data correct
```

---

## 🆘 Troubleshooting untuk Pemula

### Problem 1: "Module tidak ada di Odoo"

**Gejala:**
```
Saat buka menu, WhatsApp Headless tidak muncul
```

**Solusi:**

```bash
# Step 1: Cek folder module ada?
ls -la /home/taufik/odoo_clean_project/custom_addons/whatsapp_headless/

# Seharusnya ada file:
# - __manifest__.py
# - models/wa_history.py
# - controllers/main.py

# Step 2: Restart Odoo
docker-compose down
docker-compose up -d
sleep 30

# Step 3: Cek di Odoo
# Buka: Settings → Modules → Update Modules List
# Search "whatsapp"
# Klik "Install"
```

---

### Problem 2: "Chat dari teman tidak muncul di Odoo"

**Gejala:**
```
Sudah chat dari WhatsApp tapi gak ada di Odoo
```

**Penyebab & Solusi:**

```
PENYEBAB 1: Belum connect Fonnte
✓ SOLUSI: Selesaikan Setup Fonnte step-by-step
          (Fonnte adalah "jembatan" WhatsApp ke Odoo!)

PENYEBAB 2: Fonnte webhook tidak benar
✓ SOLUSI: 
  - Di Lokaltunnel/Ngrok, URL berubah setiap 8 jam
  - Update webhook URL di Fonnte
  - Test dengan "Send Test" button di Fonnte

PENYEBAB 3: Odoo URL tidak bisa diakses dari internet
✓ SOLUSI: 
  - Gunakan ngrok atau localtunnel
  - Atau pake VPS dengan IP publik
  - Localhost TIDAK bisa diakses Fonnte!

PENYEBAB 4: Firewall/Networking issue
✓ SOLUSI:
  - Check di Fonnte logs apakah webhook terkirim
  - Check di Odoo logs: docker-compose logs web | grep ERR
  - Jika networking blok, minta help ke IT
```

---

### Problem 3: "API return error"

**Gejala:**
```
curl request return error atau blank response
```

**Debug Steps:**

```bash
# 1. Cek Odoo running
docker-compose ps
# Harus show "web_1" dan "db_1" dengan Status "Up"

# 2. Cek logs
docker-compose logs web_1 | tail -50
# Cari "error" atau "traceback"

# 3. Cek database
docker-compose exec db psql -U odoo -d zoom_bersih -c "\\dt whatsapp_history"
# Harus show table exists

# 4. Tes endpoint direct
curl -v http://localhost:8077/api/wa/get_history
# Lihat response headers dan body

# 5. Restart semua
docker-compose down
docker-compose up -d
sleep 30
```

---

### Problem 4: "Postman request tidak bekerja"

**Gejala:**
```
Di Postman, GET/POST request return timeout atau error
```

**Checklist:**

```
□ URL benar? (http://localhost:8077/api/wa/...)
□ Method benar? (GET untuk query, POST untuk webhook)
□ Headers ada? (POST perlu Content-Type: application/json)
□ Body valid JSON? (gunakan JSON validator)
□ Odoo running? (docker-compose ps)
□ Tidak pakai VPN? (VPN bisa block localhost)
```

---

## 📚 Penjelasan untuk Pemula - istilah2 penting

| Istilah | Arti Simple | Contoh |
|---------|------------|---------|
| **Webhook** | Pintu rumah untuk terima kiriman otomatis | Fonnte kirim chat ke Odoo via webhook |
| **API** | Jalan untuk minta/kirim data | Aplikasi lain query chat via REST API |
| **Endpoint** | Alamat jalan di rumah | `/api/wa/get_history` adalah salah satu endpoint |
| **Fonnte** | Teman kurir antara WhatsApp dan Odoo | WhatsApp → Fonnte → Odoo |
| **ngrok** | Jembatan Internet untuk expose localhost | Buat localhost bisa diakses dari internet |
| **cURL** | Program untuk test API dari terminal | `curl http://localhost:8077/api/...` |
| **JSON** | Format data terstruktur | `{"name": "Taufik", "message": "Hello"}` |

---

## 🎯 Ringkasan Singkat

### Untuk Bekerja Sekarang:

```
1. Run Odoo: docker-compose up -d
2. Test manual: curl atau Postman
3. View di UI: http://localhost:8077
   → Menu: WhatsApp Headless → Chat History
```

### Untuk Real WhatsApp Messages:

```
1. Buat account Fonnte (https://fonnte.com)
2. Connect WhatsApp device
3. Setup webhook: http://your-domain/api/wa/webhook
4. Chat dari HP → akan appear di Odoo otomatis
```

### Yang Jangan Lupa:

```
⚠️ Localhost TIDAK bisa reach dari Fonnte
   → Gunakan ngrok atau VPS punya IP publik
⚠️ Webhook URL di Fonnte HARUS match dengan Odoo URL
⚠️ Format JSON HARUS benar, lihat contoh di atas
```

---

## ✨ Kesimpulan

**Sistem sudah 100% READY** untuk:
- ✅ Terima messages dari Fonnte
- ✅ Simpan ke database Odoo
- ✅ Query via REST API
- ✅ View di admin interface

**Yang perlu dilakukan:**
- 1️⃣ Setup Fonnte (jika ingin real WhatsApp)
- 2️⃣ Configure webhook URL
- 3️⃣ Test end-to-end

**Mau tanya lebih?**
→ Lihat log: `docker-compose logs web_1`
→ Cek database: `docker-compose exec db psql ...`
→ Test API: gunakan curl atau Postman

---

*Last Updated: 9 Feb 2026*
*Status: MVP Complete - Ready for Integration*

---

## 📁 Key Files Location

```
/home/taufik/odoo_clean_project/
├── custom_addons/whatsapp_headless/
│   ├── controllers/main.py          ← API Routes
│   ├── models/wa_history.py         ← Data Model
│   ├── views/wa_history_view.xml    ← UI Views
│   └── security/ir.model.access.csv ← Permissions
├── WHATSAPP_HEADLESS_API_GUIDE.md   ← Full API Doc
├── WHATSAPP_HEADLESS_TEST_REPORT.md ← Test Results
└── docker-compose.yml               ← Infrastructure
```

---

## 🔍 Troubleshooting

### 404 Not Found Error
```
Cause: Module not loaded
Fix: docker-compose restart web_1
Wait 30 seconds for module to load
```

### 500 Internal Server Error
```
Check logs:
docker-compose logs web_1 | tail -50
```

### Database Connection Error
```
Ensure db container is running:
docker-compose up -d db web_1
```

---

## 📝 Click-by-Click Demo Steps

### Step 1: Show Webhook Receiving
```
Open Postman → [Select POST /api/wa/webhook]
Fill request body with sample message
Send → Show success response
```

### Step 2: Navigate to UI
```
Open browser → http://localhost:8077
Login (admin/admin) → Go to WhatsApp Headless
Reload page → Show new message appeared
```

### Step 3: Query via API
```
Postman → [Select GET /api/wa/get_history]
Send → Show JSON response with all messages
Explain: This is what client apps query for data!
```

### Step 4: Show Filter
```
Postman → [Edit to include ?phone=... param]
Send → Show filtered result (1 message)
Explain: Client can filter by contact number
```

### Step 5: Show Statistics
```
Postman → [Select GET /api/wa/stats]
Send → Show count breakdown
Explain: Real-time monitoring dashboard
```

---

## ✅ Checklist Sebelum Demo

- [ ] Odoo running (`docker-compose ps` shows web + db UP)
- [ ] Module loaded (visit http://localhost:8077 - no errors)
- [ ] Postman installed & configured
- [ ] Test webhook working (send 1 test message)
- [ ] Internet connection stable
- [ ] Slides/documentation printed/ready
- [ ] Backup setup (in case something breaks)

---

## 🎯 Demo Talking Points

1. **Problem Solved**: Sales team bisa terima WhatsApp notification di UI Odoo
2. **Solution Design**: Headless backend → API → Client apps
3. **Technology Stack**: Odoo + REST API + JSON
4. **Real-Time Data**: Messages auto-saved saat diterima
5. **Scalable**: Mudah integrate dengan CRM, automation tools, custom apps
6. **Security Ready**: Can add API tokens, encryption di production

---

## 🚨 Emergency Contacts

**If Something Breaks**:
1. Check docker containers: `docker-compose ps`
2. Restart: `docker-compose restart web_1`
3. Check logs: `docker-compose logs web_1`
4. Nuke & rebuild: `docker-compose down && docker-compose up -d`

**Expected Recovery Time**: 1-3 minutes

---

**Last Updated**: 9 Feb 2026  
**MVP Status**: ✅ Ready for Demo  
**Next Phase**: Production Hardening + Fonnte Integration
