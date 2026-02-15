# 🔧 CONTAINER TRACKER: IMPLEMENTATION GUIDE
**How to Apply Security & Scalability Fixes**

---

## PHASE 1: IMMEDIATE FIXES (Week 1-2)
### Priority: CRITICAL - Do before production

### Step 1.1: Update Security Configuration
```bash
# Backup current security file
cp custom_addons/om_container_tracker/security/ir.model.access.csv \
   custom_addons/om_container_tracker/security/ir.model.access.csv.backup

# Replace dengan improved version
cp CONTAINER_TRACKER_IMPROVED_SECURITY.csv \
   custom_addons/om_container_tracker/security/ir.model.access.csv
```

**What changed:**
- Regular users: read-only access to EDI status
- Managers: full access (read/write/create)
- System admin: always full access

---

### Step 1.2: Database Optimization

**Run these SQL commands:**
```sql
-- Connect ke Odoo database
psql -U odoo -d odoo_database

-- Copy-paste commands dari CONTAINER_TRACKER_DATABASE_OPTIMIZATION.sql
-- Section 1 (CREATE INDEXES)
```

**Verify indexes dibuat:**
```sql
SELECT indexname FROM pg_indexes 
WHERE tablename = 'sale_order' 
AND indexname LIKE '%container%';

-- Should return:
-- idx_sale_order_container_tracking
-- idx_sale_order_container_number
-- idx_sale_order_access_token
```

---

### Step 1.3: Update Core Controller

**Replace file:** `custom_addons/om_container_tracker/controllers/main.py`

**Steps:**
```bash
# Backup original
cp custom_addons/om_container_tracker/controllers/main.py \
   custom_addons/om_container_tracker/controllers/main.py.v1

# Copy improved version
cp CONTAINER_TRACKER_IMPROVED_CONTROLLERS.py \
   custom_addons/om_container_tracker/controllers/main.py
```

**What's new in v2.0:**
- ✅ Rate limiting (10 requests/hour per IP, 5/hour per token)
- ✅ XSS protection (HTML escaping)
- ✅ Input validation (ISO 6346 format)
- ✅ Optimized timeout (30s → from 60s)
- ✅ Comprehensive error handling
- ✅ Security logging

---

### Step 1.4: Update Sale Order Model

**Replace file:** `custom_addons/om_container_tracker/models/sale_order.py`

**Steps:**
```bash
# Backup original
cp custom_addons/om_container_tracker/models/sale_order.py \
   custom_addons/om_container_tracker/models/sale_order.py.v1

# Copy improved version
cp CONTAINER_TRACKER_IMPROVED_MODELS.py \
   custom_addons/om_container_tracker/models/sale_order.py
```

**What's new:**
- ✅ Secure token generation (secrets module)
- ✅ Container format validation (ISO 6346)
- ✅ Permission checks (only sales managers)
- ✅ Audit trail (who generated when)
- ✅ Database indexes
- ✅ Token reset feature (for compromised tokens)

---

### Step 1.5: Restart & Test

```bash
# Restart Odoo service
sudo systemctl restart odoo

# Check logs untuk errors
tail -f /var/log/odoo/odoo.log

# Expected output pada startup:
# [om_container_tracker] Loaded security configuration
# [om_container_tracker] v2.0 initialized with security enhancements
```

**Quick smoke test:**
```python
# Login ke Odoo console
./odoo shell

# Test container number validation
from odoo import http
call = http.Controller()
call._validate_container_number("CSNU6184414")  # Should return True
call._validate_container_number("invalid")  # Should return False
```

---

## PHASE 2: MONITORING & LOGGING (Week 2-3)

### Step 2.1: Configure Logging

**Edit:** `odoo.conf`
```ini
[options]
# Enable debug untuk container tracker
log_level = info

# Create separate log file
logfile = /var/log/odoo/container_tracker.log

# Increase log rotation
log_file_size = 52428800  # 50MB
log_file_backups = 10
```

---

### Step 2.2: Set Up Audit Trail

**Run database audit table setup:**
```sql
-- From CONTAINER_TRACKER_DATABASE_OPTIMIZATION.sql
-- Section 3 (CREATE AUDIT TABLE)
```

**Add to Python model:**
```python
# In controllers/main.py, modify _check_rate_limit()
def _log_tracking_attempt(self, container, token, ip, success, response_time):
    query = """
    INSERT INTO container_tracking_audit 
    (container_number, access_token, client_ip, success, response_time_ms)
    VALUES (%s, %s, %s, %s, %s)
    """
    self.env.cr.execute(query, [container, token, ip, success, response_time])
```

---

### Step 2.3: Setup Alerts

**Configure alert rules:**
```bash
# If using Prometheus/Grafana:

# Alert 1: High failed tracking attempts
alert: container_tracking_failures_high
  expr: rate(container_tracking_failures[5m]) > 5
  
# Alert 2: Slow API responses
alert: container_tracking_slow_api
  expr: container_tracking_response_time_ms > 10000
  
# Alert 3: Rate limit violations
alert: ratelimit_throttling
  expr: increase(container_tracking_ratelimit_hit[1h]) > 100
```

---

## PHASE 3: CACHING STRATEGY (Week 3-4)

### Step 3.1: Redis Setup

**Install Redis:**
```bash
sudo apt-get install redis-server

# Or Docker:
docker run -d -p 6379:6379 redis:7-alpine
```

---

### Step 3.2: Update Controllers untuk Cache

**Modify `controllers/main.py`:**
```python
import redis
from datetime import timedelta

class ContainerTrackingController(http.Controller):
    
    def __init__(self):
        super().__init__()
        self.redis_client = redis.Redis(
            host='localhost',
            port=6379,
            decode_responses=True
        )
        self.CACHE_TTL = 21600  # 6 hours
    
    def _get_cached_tracking(self, container_number):
        """
        Check Redis cache sebelum API call
        """
        cache_key = f"tracking:{container_number}"
        cached = self.redis_client.get(cache_key)
        
        if cached:
            _logger.info(f"Cache HIT for {container_number}")
            return json.loads(cached)
        
        return None
    
    def _set_tracking_cache(self, container_number, data):
        """
        Cache API response ke Redis (6 jam)
        """
        cache_key = f"tracking:{container_number}"
        self.redis_client.setex(
            cache_key,
            self.CACHE_TTL,
            json.dumps(data)
        )
    
    def track_container_page(self, number=None, token=None, **kwargs):
        # ... existing validation code ...
        
        # Try cache first
        cached_data = self._get_cached_tracking(number)
        if cached_data:
            raw_json = cached_data
        else:
            # Hit API
            response = requests.get(url, params=params, timeout=30)
            raw_json = response.json()
            
            # Cache for next 6 hours
            self._set_tracking_cache(number, raw_json)
        
        # ... rest of implementation ...
```

---

### Step 3.3: Verify Cache Working

```bash
# Check Redis
redis-cli

# In Redis CLI:
KEYS "tracking:*"
GET "tracking:CSNU6184414"

# Should show cached data
```

---

## PHASE 4: LONG-TERM MAINTENANCE (Monthly)

### Step 4.1: Monthly Database Maintenance

**Create cron job:**
```bash
# /etc/cron.d/container-tracker-maintenance

# Weekly: Cleanup cache & audit
0 0 * * 0 psql -U odoo -d odoo_database -c "DELETE FROM container_tracking_cache WHERE expires_at < NOW();"

# Daily: Analyze table performance
0 1 * * * psql -U odoo -d odoo_database -c "VACUUM ANALYZE sale_order; VACUUM ANALYZE container_tracking_audit;"

# Monthly: Archive old audit logs
0 2 1 * * psql -U odoo -d odoo_database -c "CREATE TABLE container_tracking_archive_\$(date +%Y%m) AS SELECT * FROM container_tracking_audit WHERE created_at < NOW() - INTERVAL '6 months';"
```

---

### Step 4.2: Monthly Security Review

**Checklist:**
- [ ] Review audit logs untuk suspicious activities
- [ ] Check rate limit violations menggunakan query:
  ```sql
  SELECT client_ip, COUNT(*) FROM container_tracking_audit 
  WHERE success = FALSE AND created_at > NOW() - INTERVAL '30 days'
  GROUP BY client_ip HAVING COUNT(*) > 100;
  ```
- [ ] Verify no token reuse
- [ ] Check for XSS attempts dalam logs

---

### Step 4.3: Quarterly Backup & Archive

**Backup procedure:**
```bash
# Export audit trail
pg_dump odoo_database -t container_tracking_audit \
  | gzip > /backup/tracking_audit_$(date +%Y%m%d).sql.gz

# Retain for 7 years (requirement untuk shipping)
```

---

## TESTING CHECKLIST

### Security Tests

- [ ] **Brute Force Test**
  ```bash
  # Try 20 requests dengan different tokens
  for i in {1..20}; do
    curl "http://localhost:8069/tracking/container?number=CSNU6184414&token=invalid_token_$i"
  done
  # Should get rate limited after 10 requests
  ```

- [ ] **XSS Test**
  ```
  Container: <script>alert('xss')</script>
  Should show: [TEXT FILTERED]
  ```

- [ ] **SQL Injection Test**
  ```
  Container: '; DROP TABLE sale_order; --
  Should fail validation (incorrect format)
  ```

- [ ] **Token Generation Test**
  ```python
  # Verify tokens are cryptographically random
  tokens = set()
  for i in range(100):
    order.action_generate_tracking_token()
    tokens.add(order.access_token)
  
  # All 100 tokens should be unique
  assert len(tokens) == 100
  ```

---

### Performance Tests

- [ ] **Load Test (100 concurrent users)**
  ```bash
  # Using Apache Bench atau Locust
  ab -n 1000 -c 100 "http://localhost:8069/tracking/container?number=CSNU6184414&token=xyz"
  
  # Expected: avg response < 1 second
  ```

- [ ] **Cache Hit Test**
  ```bash
  # Track same container 10x
  # Expected: First = ~500ms (API), Rest = ~10ms (cache)
  ```

- [ ] **Database Performance**
  ```sql
  EXPLAIN ANALYZE SELECT * FROM sale_order 
  WHERE container_number = 'CSNU6184414' 
  AND access_token = 'xxx';
  
  # Should use index (cost < 10)
  ```

---

## ROLLBACK PROCEDURE

Jika ada issue setelah update:

```bash
# 1. Restore backup files
cp custom_addons/om_container_tracker/controllers/main.py.v1 \
   custom_addons/om_container_tracker/controllers/main.py

cp custom_addons/om_container_tracker/models/sale_order.py.v1 \
   custom_addons/om_container_tracker/models/sale_order.py

# 2. Drop new indexes (if needed)
DROP INDEX idx_sale_order_container_tracking;
DROP INDEX idx_sale_order_container_number;
DROP INDEX idx_sale_order_access_token;

# 3. Restart Odoo
sudo systemctl restart odoo

# 4. Notify team
echo "Rollback to v1.0 completed at $(date)" | mail -s "Container Tracker Rollback" team@example.com
```

---

## SUPPORT & ESCALATION

**If issues occur:**

1. Check logs: `/var/log/odoo/odoo.log`
2. Enable debug mode temporarily
3. Test in staging first
4. Open support ticket dengan logs + error message

**Timeline estimate:**
- Phase 1 (Critical fixes): 2-3 days
- Phase 2 (Monitoring): 3-5 days  
- Phase 3 (Caching): 1-2 days
- Phase 4 (Maintenance): Ongoing

**Total effort:** ~2 weeks untuk full implementation

---

## FUTURE ENHANCEMENTS (Year 2+)

- [ ] GraphQL API untuk tracking (replace REST)
- [ ] Webhook integration (real-time updates)
- [ ] Queue-based processing (Celery + RabbitMQ)
- [ ] Multi-provider support (beyond TimeToCargo)
- [ ] TMS integration (Transportation Management System)
- [ ] Predictive ETA (ML model)
- [ ] Mobile app for tracking
- [ ] IoT sensor integration (GPS/RFID)

