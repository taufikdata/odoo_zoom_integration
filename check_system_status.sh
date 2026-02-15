#!/bin/bash

# WhatsApp Headless System Status Checker
# Untuk Pemula - Script ini check apakah semua komponen running dengan baik

echo "════════════════════════════════════════════════════════════════"
echo "  WHATSAPP HEADLESS SYSTEM STATUS CHECKER"
echo "════════════════════════════════════════════════════════════════"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

TOTAL_CHECKS=0
PASSED_CHECKS=0

# Function: Check status
check_status() {
    local name=$1
    local command=$2
    local expected=$3
    
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    
    echo -n "[$TOTAL_CHECKS] Checking: $name ... "
    
    output=$(eval "$command" 2>&1)
    
    if echo "$output" | grep -q "$expected"; then
        echo -e "${GREEN}✓ PASS${NC}"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
        return 0
    else
        echo -e "${RED}✗ FAIL${NC}"
        echo "    Expected: $expected"
        echo "    Got: $output"
        return 1
    fi
}

echo "📋 CONTAINER STATUS"
echo "──────────────────────────────────────────────────────────────"

check_status "Docker Compose Running" \
    "docker-compose ps | grep 'Up'" \
    "Up"

if [ $? -eq 0 ]; then
    check_status "Odoo Web Container" \
        "docker-compose ps | grep web_1" \
        "Up"
    
    check_status "PostgreSQL Container" \
        "docker-compose ps | grep db_1" \
        "Up"
fi

echo ""
echo "🗄️  DATABASE STATUS"
echo "──────────────────────────────────────────────────────────────"

check_status "Database Connection" \
    "docker-compose exec -T db psql -U odoo -d zoom_bersih -c 'SELECT 1'" \
    "1"

check_status "WhatsApp History Table Exists" \
    "docker-compose exec -T db psql -U odoo -d zoom_bersih -c '\\dt whatsapp_history'" \
    "whatsapp_history"

check_status "Table Has Data" \
    "docker-compose exec -T db psql -U odoo -d zoom_bersih -c 'SELECT COUNT(*) FROM whatsapp_history'" \
    "[0-9]"

# Get message count
MSG_COUNT=$(docker-compose exec -T db psql -U odoo -d zoom_bersih -c "SELECT COUNT(*) FROM whatsapp_history" 2>&1 | grep -oE '[0-9]+' | head -1)
echo "    📊 Total Messages in Database: $MSG_COUNT"

echo ""
echo "🔌 API ENDPOINTS"
echo "──────────────────────────────────────────────────────────────"

check_status "Webhook Endpoint (POST /api/wa/webhook)" \
    "curl -s -o /dev/null -w '%{http_code}' -X POST http://localhost:8077/api/wa/webhook -H 'Content-Type: application/json' -d '{\"sender\":\"+123\",\"message\":\"test\"}'" \
    "200"

check_status "Get History Endpoint (GET /api/wa/get_history)" \
    "curl -s -o /dev/null -w '%{http_code}' http://localhost:8077/api/wa/get_history" \
    "200"

check_status "Stats Endpoint (GET /api/wa/stats)" \
    "curl -s -o /dev/null -w '%{http_code}' http://localhost:8077/api/wa/stats" \
    "200"

echo ""
echo "🧩 MODULE STATUS"
echo "──────────────────────────────────────────────────────────────"

check_status "Module Installed in Odoo" \
    "docker-compose logs web_1 2>&1 | grep -i 'whatsapp_headless'" \
    "whatsapp_headless"

echo ""
echo "════════════════════════════════════════════════════════════════"
echo -e "RESULT: ${GREEN}$PASSED_CHECKS/$TOTAL_CHECKS${NC} checks passed"
echo "════════════════════════════════════════════════════════════════"

if [ $PASSED_CHECKS -eq $TOTAL_CHECKS ]; then
    echo ""
    echo -e "${GREEN}✅ SISTEM SUDAH READY!${NC}"
    echo ""
    echo "Status: Semua komponen berjalan dengan normal"
    echo ""
    echo "Next Steps:"
    echo "1. Setup Fonnte untuk real WhatsApp messages"
    echo "2. Atau test dengan curl/Postman"
    echo "3. Lihat Chat History di Odoo UI"
    echo ""
    exit 0
else
    echo ""
    echo -e "${RED}⚠️  ADA YANG BERMASALAH!${NC}"
    echo ""
    echo "How to Fix:"
    echo "1. Cek apakah docker-compose running:"
    echo "   docker-compose ps"
    echo ""
    echo "2. Lihat detail error:"
    echo "   docker-compose logs web_1 | tail -50"
    echo ""
    echo "3. Restart semua:"
    echo "   docker-compose down"
    echo "   docker-compose up -d"
    echo "   sleep 30"
    echo "   bash ./check_status.sh  # Run script ini lagi"
    echo ""
    exit 1
fi
