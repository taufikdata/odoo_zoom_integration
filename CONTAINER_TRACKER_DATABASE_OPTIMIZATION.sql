"""
DATABASE OPTIMIZATION & SCALING CHECKLIST
For: om_container_tracker module

Run these SQL commands untuk optimize database performance
untuk production dengan 1000+ orders
"""

-- ============================================================================
-- 1. CREATE INDEXES (FIX SCALABILITY ISSUE #9)
-- ============================================================================
-- Composite index untuk search query yang paling sering di-hit
CREATE UNIQUE INDEX idx_sale_order_container_tracking 
ON sale_order(container_number, access_token)
WHERE container_number IS NOT NULL AND access_token IS NOT NULL;

-- Single indexes untuk frequent searches
CREATE INDEX idx_sale_order_container_number 
ON sale_order(container_number)
WHERE container_number IS NOT NULL;

CREATE INDEX idx_sale_order_access_token 
ON sale_order(access_token)
WHERE access_token IS NOT NULL;

-- ============================================================================
-- 2. TABLE OPTIMIZATION
-- ============================================================================
-- Add CLUSTER (untuk faster sequential scans)
CLUSTER sale_order USING idx_sale_order_container_tracking;

-- Analyze table untuk optimal query planning
ANALYZE sale_order;

-- ============================================================================
-- 3. CREATE AUDIT TABLE (FIX LOGGING ISSUE #12)
-- ============================================================================
-- Track semua tracking attempts (untuk security monitoring)
CREATE TABLE container_tracking_audit (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMP DEFAULT NOW(),
    container_number VARCHAR(20),
    access_token VARCHAR(50),
    client_ip VARCHAR(45),
    user_agent TEXT,
    success BOOLEAN,
    response_time_ms INTEGER,
    error_message TEXT,
    indexed_at TIMESTAMP
);

-- Index untuk quick filtering
CREATE INDEX idx_tracking_audit_timestamp 
ON container_tracking_audit(created_at DESC);

CREATE INDEX idx_tracking_audit_container 
ON container_tracking_audit(container_number);

CREATE INDEX idx_tracking_audit_ip 
ON container_tracking_audit(client_ip);

-- ============================================================================
-- 4. CREATE CACHING TABLE (FIX SCALABILITY ISSUE #8)
-- ============================================================================
-- Cache API responses untuk reduce API calls (6-hour TTL)
CREATE TABLE container_tracking_cache (
    id SERIAL PRIMARY KEY,
    container_number VARCHAR(20) UNIQUE NOT NULL,
    api_response TEXT NOT NULL,
    cached_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP,
    hit_count INTEGER DEFAULT 0
);

CREATE INDEX idx_tracking_cache_expires 
ON container_tracking_cache(expires_at);

-- ============================================================================
-- 5. CREATE RATE LIMIT TABLE (FIX SECURITY ISSUE #1)
-- ============================================================================
-- Track rate limiting per IP dan token
CREATE TABLE container_tracking_ratelimit (
    id SERIAL PRIMARY KEY,
    identifier VARCHAR(100) NOT NULL,
    limit_type VARCHAR(20),  -- 'ip' or 'token'
    request_count INTEGER DEFAULT 1,
    first_request TIMESTAMP DEFAULT NOW(),
    last_request TIMESTAMP DEFAULT NOW(),
    UNIQUE(identifier, limit_type)
);

CREATE INDEX idx_ratelimit_first_request 
ON container_tracking_ratelimit(first_request DESC);

-- ============================================================================
-- 6. MAINTENANCE QUERIES (RUN PERIODICALLY)
-- ============================================================================

-- Cleanup expired cache (run daily via cron)
DELETE FROM container_tracking_cache 
WHERE expires_at < NOW();

-- Cleanup old audit logs (retain 90 days)
DELETE FROM container_tracking_audit 
WHERE created_at < NOW() - INTERVAL '90 days';

-- Cleanup old rate limit entries
DELETE FROM container_tracking_ratelimit 
WHERE last_request < NOW() - INTERVAL '2 hours';

-- Vacuum & analyze (weekly)
VACUUM ANALYZE container_tracking_audit;
VACUUM ANALYZE container_tracking_cache;

-- ============================================================================
-- 7. PERFORMANCE MONITORING QUERIES
-- ============================================================================

-- Check slow tracking queries
SELECT 
    container_number,
    COUNT(*) as access_count,
    AVG(response_time_ms) as avg_response_ms,
    MAX(response_time_ms) as max_response_ms
FROM container_tracking_audit
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY container_number
HAVING COUNT(*) > 10
ORDER BY avg_response_ms DESC;

-- Check rate limit violations
SELECT 
    client_ip,
    COUNT(*) as failed_attempts,
    created_at
FROM container_tracking_audit
WHERE success = FALSE
AND created_at > NOW() - INTERVAL '1 hour'
GROUP BY client_ip
ORDER BY failed_attempts DESC;

-- Cache hit ratio
SELECT 
    ROUND(100.0 * SUM(CASE WHEN hit_count > 1 THEN 1 ELSE 0 END) / COUNT(*), 2) as cache_hit_ratio_percent,
    COUNT(*) as total_cached_containers
FROM container_tracking_cache;

-- ============================================================================
-- 8. BACKUP STRATEGY (FOR 5-10 YEAR ARCHIVAL)
-- ============================================================================

-- Export tracking history (quarterly)
COPY container_tracking_audit 
TO '/backup/container_audit_2026_Q1.csv' WITH CSV HEADER;

-- Archive old tracking to separate table (yearly)
CREATE TABLE container_tracking_archive AS
SELECT * FROM container_tracking_audit
WHERE created_at < NOW() - INTERVAL '1 year';

DELETE FROM container_tracking_audit
WHERE created_at < NOW() - INTERVAL '1 year';

-- ============================================================================
-- 9. REPLICATION SETUP (FOR HIGH AVAILABILITY)
-- ============================================================================

-- Enable WAL (Write-Ahead Logging) untuk point-in-time recovery
ALTER SYSTEM SET wal_level = replica;

-- Setup read replicas untuk distribute load
-- Primary: production database
-- Replica 1: analytics/reporting
-- Replica 2: backup


-- ============================================================================
-- 10. MONITORING & ALERTS
-- ============================================================================

-- Setup monitoring untuk:
-- ✓ Table size growth (should be < 1GB per year)
-- ✓ Index size (should be < 500MB per year)
-- ✓ Disk space remaining
-- ✓ Query performance (slow query log)
-- ✓ Connection count (should be < 100 concurrent)
-- ✓ Replication lag (if using replicas)

-- Example: Check table sizes
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE tablename LIKE 'container_%' OR tablename = 'sale_order'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
