# 📋 CONTAINER TRACKER: IMPLEMENTATION CHECKLIST

Print this & check off as you implement fixes

---

## PHASE 0: PREPARATION (Before starting)

- [ ] **Read all audit documents** (4 hours)
  - [ ] CONTAINER_TRACKER_AUDIT_SUMMARY.md
  - [ ] CONTAINER_TRACKER_SECURITY_AUDIT.md
  - [ ] CONTAINER_TRACKER_IMPLEMENTATION_GUIDE.md

- [ ] **Get team approval & budget**
  - [ ] Share findings dengan stakeholders
  - [ ] Get buy-in untuk 2-3 weeks effort
  - [ ] Allocate resources

- [ ] **Setup staging environment**
  - [ ] Clone production database
  - [ ] Fresh Odoo instance untuk testing
  - [ ] SSH access ready
  - [ ] Database backups configured

- [ ] **Prepare team**
  - [ ] Developer trained on fixes
  - [ ] QA ready for testing
  - [ ] DevOps ready for database changes

---

## PHASE 1: CRITICAL SECURITY FIXES (2-3 days)

### Day 1: Code Changes

**Task 1.1: Backup original files**
- [ ] `cp controllers/main.py controllers/main.py.v1.backup`
- [ ] `cp models/sale_order.py models/sale_order.py.v1.backup`
- [ ] `cp security/ir.model.access.csv security/ir.model.access.csv.v1.backup`

**Task 1.2: Deploy improved controller**
- [ ] Review `CONTAINER_TRACKER_IMPROVED_CONTROLLERS.py` for conflicts
- [ ] Copy to `custom_addons/om_container_tracker/controllers/main.py`
- [ ] Check syntax: `python3 -m py_compile controllers/main.py`
- [ ] Restart Odoo: `sudo systemctl restart odoo`
- [ ] Check logs: `tail -50 /var/log/odoo/odoo.log` (no errors!)

**Task 1.3: Deploy improved model**
- [ ] Review `CONTAINER_TRACKER_IMPROVED_MODELS.py`
- [ ] Copy to `custom_addons/om_container_tracker/models/sale_order.py`
- [ ] Check syntax: `python3 -m py_compile models/sale_order.py`
- [ ] Restart Odoo again
- [ ] Verify no migration errors

**Task 1.4: Fix security/permissions**
- [ ] Copy `CONTAINER_TRACKER_IMPROVED_SECURITY.csv` to `security/ir.model.access.csv`
- [ ] Update Odoo module: `Go to Apps > Search: om_container_tracker > Upgrade`
- [ ] Verify permissions in Odoo UI

### Day 2: Database Optimization

**Task 2.1: Create indexes**
- [ ] Connect to database: `psql -U odoo -d odoo_database`
- [ ] Copy Section 1 dari `CONTAINER_TRACKER_DATABASE_OPTIMIZATION.sql`
- [ ] Run CREATE INDEX commands
- [ ] Verify indexes created:
  ```sql
  SELECT indexname FROM pg_indexes 
  WHERE tablename = 'sale_order' 
  AND indexname LIKE '%container%';
  ```
  Should show: `idx_sale_order_container_tracking`, etc

**Task 2.2: Create audit table**
- [ ] Run Section 3 (CREATE TABLE container_tracking_audit)
- [ ] Verify table created:
  ```sql
  \dt container_tracking_audit
  ```

**Task 2.3: Test query performance**
- [ ] Run EXPLAIN ANALYZE query dari guide
- [ ] Verify cost < 10 (using index, not full scan)

### Day 3: Testing & Validation

**Task 3.1: Unit tests**
- [ ] Run: `python3 container_tracker_tests.py --security-only`
- [ ] All security tests should PASS
- [ ] Fix any failures before proceeding

**Task 3.2: Smoke testing**
- [ ] Create test Sale Order dengan container number
- [ ] Generate tracking token
- [ ] Access tracking page (should work)
- [ ] Try with invalid token (should be rejected)
- [ ] Check rate limiting (make 15 requests, should limit after 10)

**Task 3.3: Regression testing**
- [ ] Verify normal tracking still works
- [ ] Verify other SO functionality not broken
- [ ] Check database integrity

---

## PHASE 2: MONITORING & LOGGING (3-5 days)

### Task 2.1: Configure Odoo logging
- [ ] Edit odoo.conf:
  ```ini
  log_level = info
  logfile = /var/log/odoo/container_tracker.log
  ```
- [ ] Restart Odoo
- [ ] Verify logs writing: `tail -f /var/log/odoo/container_tracker.log`

### Task 2.2: Setup audit logging
- [ ] Add logging calls ke controllers/main.py (see implementation guide)
- [ ] First tracking attempt should log:
  - [ ] Container number
  - [ ] Client IP
  - [ ] Success/failure
  - [ ] Response time

### Task 2.3: Create monitoring dashboard
- [ ] Setup Monitoring tool (Grafana/Prometheus atau simple script)
- [ ] Track metric: Failed tracking attempts per hour
- [ ] Track metric: Average response time
- [ ] Track metric: Rate limit hits per hour
- [ ] Track metric: API error rate

### Task 2.4: Setup alerts
- [ ] Alert if > 5 failed attempts in 5 min
- [ ] Alert if response time > 5 seconds
- [ ] Alert if > 100 rate limit hits per hour
- [ ] Alert if API error rate > 10%

---

## PHASE 3: CACHING & PERFORMANCE (2-3 days)

### Task 3.1: Setup Redis
- [ ] Install Redis: `sudo apt-get install redis-server`
- [ ] Or Docker: `docker run -d -p 6379:6379 redis:7-alpine`
- [ ] Verify Redis running: `redis-cli ping` (should return PONG)

### Task 3.2: Implement caching in code
- [ ] Modify `controllers/main.py`:
  - [ ] Add `_get_cached_tracking()` method
  - [ ] Add `_set_tracking_cache()` method
  - [ ] Check cache before API call
  - [ ] Cache for 6 hours TTL

### Task 3.3: Test caching
- [ ] Track same container 2x
- [ ] First = ~500ms (API call)
- [ ] Second = ~50ms (cache hit)
- [ ] Verify Redis: `redis-cli KEYS "tracking:*"` (should show entries)

### Task 3.4: Performance testing
- [ ] Run: `python3 container_tracker_tests.py --performance`
- [ ] Measure:
  - [ ] Single request latency < 500ms ✓
  - [ ] Cached request < 50ms ✓
  - [ ] 10 concurrent users no degradation ✓

---

## PHASE 4: DEPLOYMENT PREP (1-2 days)

### Task 4.1: Final testing
- [ ] Run full test suite: `python3 container_tracker_tests.py`
- [ ] All tests PASS ✓
- [ ] Generate report: `container_tracker_test_report_YYYYMMDD.txt`

### Task 4.2: Documentation
- [ ] Update README dengan v2.0 changes
- [ ] Document new environment variables (Redis, etc)
- [ ] Update deployment instructions

### Task 4.3: Runbook preparation
- [ ] Prepare deployment runbook
- [ ] Prepare rollback procedure
- [ ] Prepare incident response guide

### Task 4.4: Team training
- [ ] Train support team on new logging/monitoring
- [ ] Train admin on new token generation features
- [ ] Document any new features

---

## PHASE 5: PRODUCTION DEPLOYMENT (1 day)

### Deployment Window: (Off-peak hours, e.g., Sunday 2 AM)

**Pre-Deployment (check all):**
- [ ] All tests passing
- [ ] Staging fully tested (24 hours running)
- [ ] Backup created & verified
- [ ] Rollback procedure documented
- [ ] Team on standby
- [ ] Monitoring setup ready
- [ ] Communication plan (notify customers?)

**Deployment Steps:**
- [ ] Stop Odoo: `sudo systemctl stop odoo`
- [ ] Backup production DB: `pg_dump odoo | gzip > backup_$(date +%Y%m%d).sql.gz`
- [ ] Copy new code:
  ```bash
  cp CONTAINER_TRACKER_IMPROVED_CONTROLLERS.py custom_addons/om_container_tracker/controllers/main.py
  cp CONTAINER_TRACKER_IMPROVED_MODELS.py custom_addons/om_container_tracker/models/sale_order.py
  cp CONTAINER_TRACKER_IMPROVED_SECURITY.csv custom_addons/om_container_tracker/security/ir.model.access.csv
  ```
- [ ] Start Odoo: `sudo systemctl start odoo`
- [ ] Wait 2 minutes for startup
- [ ] Check logs (no errors)
- [ ] Verify web UI loads
- [ ] Test tracking page (should work)
- [ ] Check monitoring dashboard (values appearing)

**Post-Deployment (immediate):**
- [ ] Monitor errors (1 hour)
- [ ] Monitor performance (1 hour)
- [ ] Run quick test:
  ```
  - Create test SO
  - Generate token
  - Access tracking page
  - Verify rate limiting
  ```
- [ ] Check monitoring metrics

**Post-Deployment (24 hours):**
- [ ] Review logs for issues
- [ ] Check database size growth (normal?)
- [ ] Verify cache hit ratio (> 70%?)
- [ ] Confirm no customer complaints

---

## PHASE 6: ONGOING MAINTENANCE (Monthly)

**Monthly Tasks (first Friday):**
- [ ] Review audit logs untuk suspicious activity
  ```sql
  SELECT client_ip, COUNT(*) FROM container_tracking_audit 
  WHERE created_at > NOW() - INTERVAL '30 days'
  AND success = FALSE
  GROUP BY client_ip HAVING COUNT(*) > 50;
  ```
- [ ] Check rate limit violations
- [ ] Review performance metrics (response time, API calls)
- [ ] Check cache hit ratio (target: > 80%)

**Quarterly Tasks:**
- [ ] Database cleanup
  ```sql
  DELETE FROM container_tracking_cache WHERE expires_at < NOW();
  DELETE FROM container_tracking_audit WHERE created_at < NOW() - INTERVAL '90 days';
  ANALYZE container_tracking_audit;
  ```
- [ ] Index maintenance
  ```sql
  REINDEX TABLE sale_order;
  ```

**Yearly Tasks (Jan):**
- [ ] Full security audit
- [ ] Backup archival (7 year retention)
- [ ] Code review for updates
- [ ] Update dependencies

---

## TROUBLESHOOTING (If Issues Arise)

**Problem: Tests failing after deployment**
- [ ] Check logs: `tail -100 /var/log/odoo/odoo.log`
- [ ] Verify syntax: `python3 -m py_compile custom_addons/om_container_tracker/controllers/main.py`
- [ ] Rollback if needed (use backup files .v1)

**Problem: Tracking page returns 500 error**
- [ ] Check Rate limit table: `SELECT COUNT(*) FROM container_tracking_ratelimit;`
- [ ] Check if Redis running: `redis-cli ping`
- [ ] Re-index database: `REINDEX TABLE sale_order;`

**Problem: Rate limiting too aggressive**
- [ ] Adjust limits in code:
  - From: `MAX_REQUESTS_PER_IP = 10` 
  - To: `MAX_REQUESTS_PER_IP = 20` (if need to increase)
- [ ] Restart Odoo

**Problem: Cache not working**
- [ ] Verify Redis: `redis-cli` > `INFO memory`
- [ ] Check logs for cache errors
- [ ] Restart Redis: `sudo systemctl restart redis-server`

---

## ROLLBACK PROCEDURE (if needed)

If critical issue found after deployment:

1. **STOP: Don't make more changes**
2. **Rollback Code:**
   ```bash
   cp custom_addons/om_container_tracker/controllers/main.py.v1.backup custom_addons/om_container_tracker/controllers/main.py
   cp custom_addons/om_container_tracker/models/sale_order.py.v1.backup custom_addons/om_container_tracker/models/sale_order.py
   cp custom_addons/om_container_tracker/security/ir.model.access.csv.v1.backup custom_addons/om_container_tracker/security/ir.model.access.csv
   sudo systemctl restart odoo
   ```
3. **Rollback Database (if needed):**
   ```bash
   sudo systemctl stop odoo
   psql -U odoo -d odoo_database < backup_YYYYMMDD.sql.gz
   sudo systemctl start odoo
   ```
4. **Verify:** Test tracking page works again
5. **Report:** Document what went wrong
6. **Re-plan:** Schedule fix attempt for next week

---

## SUCCESS CRITERIA (All must be ✓)

- [ ] All 20+ security tests PASS
- [ ] All 5+ performance tests PASS
- [ ] Latency < 500ms (API), < 50ms (cache)
- [ ] Rate limiting working (10 req/hour per IP)
- [ ] XSS test cases blocked
- [ ] SQL injection test cases blocked
- [ ] 100 concurrent users handled
- [ ] Cache hit ratio > 70%
- [ ] Zero errors in production logs (24 hours)
- [ ] Monitoring dashboard showing metrics
- [ ] Team trained & confident
- [ ] Rollback procedure tested & documented

---

## SIGNATURES / APPROVALS

**Development Lead:**
- Name: ________________
- Date: ________________
- Approved: ☐ Yes ☐ No

**QA Lead:**
- Name: ________________  
- Date: ________________
- Approved: ☐ Yes ☐ No

**DevOps/Infrastructure:**
- Name: ________________
- Date: ________________
- Approved: ☐ Yes ☐ No

**Project Manager:**
- Name: ________________
- Date: ________________
- Approved: ☐ Yes ☐ No

---

**Estimated Timeline:** 2-3 weeks  
**Success Probability:** 95% (with recommended procedure)  
**Support Available:** Yes (see CONTAINER_TRACKER_IMPLEMENTATION_GUIDE.md)

---

**Print this, check off as you go! Good luck! 🚀**
