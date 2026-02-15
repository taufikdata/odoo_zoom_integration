# 🔗 Setup Fonnte - Panduan Super Simpel untuk Pemula

**Durasi: ~20 menit**  
**Kesulitan: Sangat Mudah**  
**Pre-requisite: Akun WhatsApp aktif di hp**

---

## 📱 Mengapa Perlu Fonnte?

```
TANPA FONNTE:
HP: Chat ke ke Odoo? → Gak bisa! Odoo butuh URL publik, hp gak bisa mengirim

DENGAN FONNTE:
HP: Chat ke Fonnte → Fonnte: kirim ke Odoo → Odoo: simpan pesan ✅
```

**Singkatnya:** Fonnte = "kurir" atau "perantara" antara WhatsApp dan Odoo.

---

## 🚀 TAHAP 1: BUAT AKUN FONNTE (5 MENIT)

### Step 1.1: Buka website
```
Buka di browser: https://fonnte.com
```

### Step 1.2: Daftar
Cari tombol "Sign Up" atau "Daftar", klik itu.

**Isi form:**
```
Email:     (pakai email Anda yang aktif)
Password:  (buat password kuat, minimal 8 karakter)
Negara:    Indonesia (pilih dari dropdown)
Klik:      "Register" atau "Daftar"
```

### Step 1.3: Verifikasi Email
```
1. Cek email Anda (inbox atau spam folder)
2. Ada email dari Fonnte dengan tombol "Verify" atau link verifikasi
3. Klik tombol itu
4. Selesai! Sekarang bisa login ke Fonnte

Tips: Jika tidak ada email, tunggu 2-3 menit, atau check "Spam" folder
```

---

## 📲 TAHAP 2: CONNECT WHATSAPP KE FONNTE (10 MENIT)

### Step 2.1: Login ke Fonnte
```
1. Buka https://fonnte.com/login
2. Masukkan email + password
3. Klik "Login"
```

### Step 2.2: Scan QR Code
Setelah login, harus ada option seperti ini:

**Cari tombol yang menulis:**
- "Add Device" atau
- "Connect WhatsApp" atau  
- "Scan QR Code"

Klik itu.

**Akan muncul QR Code besar - SCAN DENGAN WHATSAPP HP ANDA:**

```
1. Buka WhatsApp di HP
2. Pergi ke: Settings → Linked Devices (atau Device)
3. Tap "Link a Device"
4. Arahkan kamera ke QR Code di layar komputer
5. Tunggu sampai HP kasih notifikasi "Device linked"
```

### Step 2.3: Tunggu Connected
```
Di Fonnte dashboard harus muncul:
"Device Status: Connected" ✅

Jika masih "Pending":
- Tunggu 30 detik lagi
- Atau refresh halaman (F5)
- Atau try lagi scan QR code
```

**Selesai!** TIK, sekarang WhatsApp-nya terhubung ke Fonnte.

---

## 🪝 TAHAP 3: SETUP WEBHOOK KE ODOO (10 MENIT)

**Tujuan:** Setiap ada chat, otomatis kirim ke Odoo.

### Step 3.1: Buka Settings Webhook

Di menu Fonnte, cari:
- "Webhook" atau
- "Settings → Webhook" atau
- "Integrations → Webhook"

Klik itu.

### Step 3.2: Tambah Webhook Baru

Cari tombol: "Add Webhook" atau "Create Webhook" atau "+", klik itu.

**Form akan muncul, isi seperti ini:**

```
Webhook URL:    http://8.210.20.102:8069/api/wa/webhook
                (atau gunakan IP/domain Odoo Anda)

Events:         Pilih: "Incoming Message" 
                atau "message.received"

Status:         Pilih: "Active"

Method:         Pilih: "POST"

Klik: "Save" atau "Create"
```

⚠️ **PENTING - PILIH URL YANG BENAR:**

```
Jika Odoo di localhost (laptop Anda):
  ❌ URL: http://localhost:8077/api/wa/webhook  
  ✅ Gunakan ngrok/localtunnel (lihat di bawah)

Jika Odoo di VPS/Server dengan IP publik:
  ✅ URL: http://[IP-server]:8077/api/wa/webhook
  ✅ Atau: http://domain-anda.com/api/wa/webhook

Jika Odoo di Docker yang accessible:
  ✅ URL: http://[IP-router]:8077/api/wa/webhook
```

### Step 3.3: Test Webhook

Di Fonnte dashboard, ada button "Send Test" atau "Test Webhook", klik itu.

**Akan muncul message:**
```
"Test successful" ✅  → BAGUS, lanjut step selanjutnya
"Webhook error" ❌   → Cek URL, mungkin salah
```

---

## 🌐 JIKA ODOO DI LOCALHOST: PAKAI NGROK

**Kenapa perlu ngrok?**
```
Fonnte di cloud (internet) → Localhost Anda gak bisa diakses
Solusi: Gunakan ngrok untuk "expose" localhost ke internet
```

### Cara Pakai ngrok:

**Step 1: Download ngrok**
```
Buka https://ngrok.com/download
Download untuk platform Anda (Windows/Mac/Linux)
Extract file
```

**Step 2: Buka terminal BARU**
```bash
# Masuk folder ngrok
cd [folder-ngrok]

# Run ngrok
./ngrok http 8077
# Atau di Windows:
ngrok.exe http 8077
```

**Akan muncul sesuatu seperti:**
```
ngrok by @inconshreveable

Forwarding                    https://1234abcd-5678ef.ngrok.io -> localhost:8077

Web Interface                 http://127.0.0.1:4040
```

**Ambil URL itu:** `https://1234abcd-5678ef.ngrok.io`

**Step 3: Gunakan URL di Fonnte**
```
Di Fonnte Webhook URL:
https://1234abcd-5678ef.ngrok.io/api/wa/webhook

(bukan localhost, tapi ngrok URL!)
```

**⚠️ PENTING:** 
- ngrok URL berubah setiap 8 jam
- Jika disconnect, update lagi di Fonnte

---

## ✅ TAHAP 4: TEST KONEKSI (5 MENIT)

### Test 1: Fonnte Send Test Message

```
Di Fonnte Dashboard, cari tombol "Send Test" di webhook settings
Klik → akan send message ke Odoo
```

**Lalu cek di Odoo:**
```
1. Buka Odoo: http://localhost:8077
2. Login: user=admin, pass=admin
3. Menu → WhatsApp Headless → Chat History
4. Lihat apakah ada test message yang muncul di list
```

Jika ada → Bagus! Lanjut ke Test 2.

### Test 2: Chat dari WhatsApp Real

```
1. Buka WhatsApp di HP
2. Chat ke nomor yang connect di Fonnte (device Anda)
3. Ketik pesan: "Halo Odoo!"
4. Tunggu 5 detik
5. Refresh Odoo di browser (F5)
6. Lihat Chat History - pesan harus appear di sana!
```

---

## 🎯 Checklist Status

Setelah selesai, check ini:

```
□ Fonnte account buat? 
  Status: Done ✓

□ WhatsApp device connected ke Fonnte?
  Buka Fonnte → lihat status "Connected" ✓

□ Webhook URL sudah set di Fontte?
  Url: _________________ ✓

□ Fontte webhook test berhasil?
  Status: Success ✓

□ Chat dari Odoo muncul di Chat History?
  Result: __________ ✓

□ Chat dari HP WhatsApp muncul di Odoo?
  Result: __________ ✓
```

Jika semua ceklist Done → **SELESAI! SISTEM BERHASIL CONNECTED! 🎉**

---

## 🆘 KALAU ADA ERROR

### Error 1: "Webhook Error - Connection Refused"

**Penyebab:** URL Odoo tidak bisa diakses  

**Solusi:**
```
□ Apakah Odoo running? 
   docker-compose ps → lihat "web" state = Up
   
□ Apakah ngrok running?
   Buka terminal, lihat ngrok active?
   
□ Apakah URL di Fontte benar?
   Check: https://xxx.ngrok.io/api/wa/webhook
   (jangan lupa https, bukan http!)
   
□ Apakah ada firewall block?
   Coba matiin antivirus/firewall sementara
```

### Error 2: "WhatsApp Device Status: Not Connected"

**Penyebab:** QR Code scan gagal atau koneksi putus

**Solusi:**
```
1. Cek HP - apakah WhatsApp masih aktif?
2. Cek koneksi HP (WiFi atau data)
3. Scan QR code ulang:
   - Di Fontte cari tombol "Re-scan" atau "Reconnect"
   - Scan lagi pakai HP
4. Tunggu 30 detik sampai "Connected"
```

### Error 3: "Chat tidak muncul di Odoo"

**Penyebab:** Webhook mungkin tidak berhasil terima chat

**Solusi:**
```
1. Cek webhook status di Fonnte:
   - Harus "Active"
   - Terakhir trigger: baru2 ini
   
2. Send test ulang:
   - Di Fontte klik "Send Test"
   - Jika gagal → error
   
3. Cek logs Odoo:
   docker-compose logs web_1 | grep -i whatsapp
   
4. Cek database:
   docker-compose exec db psql -U odoo -d zoom_bersih \
     -c "SELECT * FROM whatsapp_history LIMIT 5;"
```

---

## 💡 Tips & Tricks

```
TIP 1: Jangan clear WhatsApp chat sambil test
       Biar bisa verifikasi edge case

TIP 2: Gunakan nomor yang beda untuk test
       Nanti saat demo bisa kontrol flow

TIP 3: Jangan tutup terminal ngrok sambil pakai
       Jika tutup, koneksi putus!

TIP 4: Fonnte ada free trial/credits
       Biaya per pesan sangat terjangkau

TIP 5: Baca dokumentasi Fonnte untuk detail lebih
       https://fonnte.com/docs
```

---

## 📞 Support

Jika stuck di mana pun:

**1. Check documentation:**
- Fonnte docs: https://fonnte.com/docs
- Odoo webhook: search "whatsapp_headless api guide"

**2. Check logs:**
```bash
docker-compose logs web_1 | tail -100
```

**3. Test endpoint manual:**
```bash
curl -X POST http://localhost:8077/api/wa/webhook \
  -H "Content-Type: application/json" \
  -d '{"sender":"+6281234567","pushName":"Test","message":"Hello"}'
```

**4. Reset dan coba ulang:**
```bash
docker-compose down
docker-compose up -d
sleep 30
```

---

## 🎉 Setelah Selesai Setup

**Sekarang bisa:**
✅ Chat dari HP otomatis masuk ke Odoo  
✅ Semua chat tersimpan di database  
✅ Bisa query via REST API  
✅ Persiapan untuk CRM integration  

**Sudah siap untuk:**
- Demo ke client
- Testing lebih lanjut
- Development phase 2

---

**Berhasil? Congrats! 🎊**

Silakan lanjut ke fase berikutnya atau test fitur lainnya.

*Guide ini dibuat untuk sangat pemula - semua steps dijelaskan detail*
*Jika masih bingung, tanya saja - mudah kok!*
