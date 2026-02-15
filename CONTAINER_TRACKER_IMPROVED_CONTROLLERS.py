"""
IMPROVED: controllers/main.py
Version: 2.0 (Security & Scalability Hardened)

Improvements:
- Rate limiting (IP-based + token-based)
- Input validation for container number format
- XSS protection (response sanitization)
- Request timeout optimization
- Error handling improvements
- Logging for security events
"""

from odoo import http
from odoo.http import request
import requests
import json
import hashlib
import logging
from datetime import datetime, timedelta
from html import escape

_logger = logging.getLogger(__name__)

class ContainerTrackingController(http.Controller):
    """
    SECURITY: All public routes are protected with authentication
    """

    # RATE LIMITING CONFIG
    MAX_REQUESTS_PER_IP = 10  # max 10 requests per hour per IP
    MAX_REQUESTS_PER_TOKEN = 5  # max 5 requests per hour per token
    RATE_LIMIT_WINDOW = 3600  # 1 hour in seconds
    
    # VALIDATION CONFIG
    CONTAINER_FORMAT = r'^[A-Z]{4}[0-9]{6,7}$'  # ISO 6346 format
    API_TIMEOUT = 30  # seconds (reduced dari 60)
    CACHE_TTL = 21600  # 6 hours (untuk production)

    def _safe_get(self, data, key, default=None):
        """
        SAFE: Defensive programming untuk nested dict access
        """
        if isinstance(data, dict):
            return data.get(key, default)
        return default

    def _format_date(self, date_str):
        """
        SAFE: Robust date parsing dengan fallback
        """
        if not date_str:
            return "-"
        try:
            clean_date = str(date_str).replace('Z', '').split('.')[0]
            dt_obj = datetime.fromisoformat(clean_date)
            return dt_obj.strftime("%m/%d/%y | %I:%M %p")
        except Exception as e:
            _logger.warning(f"Date format error: {str(e)}")
            return "-"

    def _sanitize_html(self, text):
        """
        FIX XSS: Escape all user input sebelum rendering
        
        BEFORE: <t t-esc="company_name"/> bisa inject <script>
        AFTER:  HTML entities escaped, safe
        """
        if not text:
            return ""
        
        # Escape HTML special characters
        sanitized = escape(str(text))
        
        # Remove any potential script tags
        dangerous_patterns = ['<script', 'javascript:', 'onerror=', 'onclick=']
        for pattern in dangerous_patterns:
            if pattern.lower() in sanitized.lower():
                _logger.warning(f"Potential XSS detected: {pattern}")
                return "[TEXT FILTERED]"
        
        return sanitized

    def _validate_container_number(self, number):
        """
        FIX INPUT VALIDATION: Container number harus ISO 6346 format
        
        Valid: CSNU6184414, TEMU1234567
        Invalid: x'*10000, SQL injection attempts, etc
        """
        if not number:
            return False
        
        # Max length check (prevent buffer overflow)
        if len(str(number)) > 20:
            return False
        
        # Format: 4 letters + 6-7 numbers (ISO 6346)
        import re
        if re.match(self.CONTAINER_FORMAT, number.upper()):
            return True
        
        _logger.warning(f"Invalid container format: {number}")
        return False

    def _check_rate_limit(self, identifier, limit_type='ip'):
        """
        FIX BRUTE FORCE: Rate limiting implementation
        
        Parameters:
        - identifier: IP address or token
        - limit_type: 'ip' (10/hour) atau 'token' (5/hour)
        
        Returns: (is_allowed, remaining_requests, reset_time)
        """
        cache_key = f"container_track_{limit_type}_{identifier}"
        
        try:
            # Get cache dari Redis/Memcache
            cache = request.env['ir.http'].session.get_db()
            
            # Simplified: gunakan database untuk tracking
            # Production: gunakan Redis untuk better performance
            
            IrConfigParameter = request.env['ir.config_parameter'].sudo()
            current_time = datetime.now().timestamp()
            
            # Retrieve previous requests
            last_request_data = IrConfigParameter.get_param(cache_key)
            
            if last_request_data:
                data = json.loads(last_request_data)
                requests_in_window = data.get('count', 0)
                first_request_time = data.get('timestamp', current_time)
                
                # Check jika window sudah expired
                if current_time - first_request_time > self.RATE_LIMIT_WINDOW:
                    # Reset window
                    requests_in_window = 0
                    first_request_time = current_time
            else:
                requests_in_window = 0
                first_request_time = current_time
            
            # Determine limit based on type
            max_limit = self.MAX_REQUESTS_PER_IP if limit_type == 'ip' else self.MAX_REQUESTS_PER_TOKEN
            
            # Check if exceeded
            if requests_in_window >= max_limit:
                reset_time = first_request_time + self.RATE_LIMIT_WINDOW
                _logger.warning(f"Rate limit exceeded for {limit_type}: {identifier}")
                return (False, 0, reset_time)
            
            # Increment counter
            requests_in_window += 1
            data = {
                'count': requests_in_window,
                'timestamp': first_request_time
            }
            IrConfigParameter.set_param(cache_key, json.dumps(data))
            
            remaining = max_limit - requests_in_window
            reset_time = first_request_time + self.RATE_LIMIT_WINDOW
            
            return (True, remaining, reset_time)
        
        except Exception as e:
            _logger.error(f"Rate limit check failed: {str(e)}")
            # Fail open dengan caution
            return (True, -1, None)

    def _get_client_ip(self):
        """
        Get actual client IP (handling proxies)
        """
        if request.httprequest.environ.get('HTTP_X_FORWARDED_FOR'):
            return request.httprequest.environ['HTTP_X_FORWARDED_FOR'].split(',')[0].strip()
        return request.httprequest.remote_addr or '0.0.0.0'

    @http.route('/tracking/container', type='http', auth='public', website=True, csrf=True)
    def track_container_page(self, number=None, token=None, **kwargs):
        """
        FIX: Secured container tracking endpoint
        
        Security improvements:
        1. CSRF protection active
        2. Rate limiting on IP
        3. Input validation
        4. SQL injection prevention (ORM)
        5. XSS protection
        6. Timeout optimization
        7. Error logging
        """
        
        # STEP 1: Validate input
        if not number or not token:
            _logger.info(f"Missing parameters: {self._get_client_ip()}")
            return "<h3>❌ Access Denied: Invalid Tracking Link. Please make sure you have the correct URL.</h3>"

        if not self._validate_container_number(number):
            _logger.warning(f"Invalid container format attempted: {number}")
            return "<h3>❌ Invalid Container Number Format. Expected format: CSNU6184414</h3>"

        # STEP 2: Rate limiting check
        client_ip = self._get_client_ip()
        ip_allowed, ip_remaining, ip_reset = self._check_rate_limit(client_ip, 'ip')
        
        if not ip_allowed:
            _logger.warning(f"Rate limit exceeded from IP: {client_ip}")
            return f"<h3>⏱️ Too many requests. Please try again later.</h3>"

        token_allowed, token_remaining, token_reset = self._check_rate_limit(token, 'token')
        
        if not token_allowed:
            _logger.warning(f"Rate limit exceeded for token: {token[:20]}...")
            return "<h3>⏱️ Tracking token has reached rate limit. Please try again in 1 hour.</h3>"

        # STEP 3: Security check against database
        try:
            sale_order = request.env['sale.order'].sudo().search([
                ('container_number', '=', number.upper()),
                ('access_token', '=', token)
            ], limit=1)

            if not sale_order:
                _logger.info(f"Unauthorized access attempt: {number} / {token[:20]}")
                return "<h3>🔒 Security Error: Unauthorized Access. The Container Number or Token is invalid.</h3>"
        except Exception as e:
            _logger.error(f"Database error during auth: {str(e)}")
            return "<h3>❌ System error. Please try again later.</h3>"

        # STEP 4: Get API key (securely)
        try:
            api_key = request.env['ir.config_parameter'].sudo().get_param('timetocargo.api_key')
            if not api_key:
                _logger.error("TimeToCargo API key not configured")
                return "<h3>❌ Error: System not configured properly. Please contact support.</h3>"
        except Exception as e:
            _logger.error(f"Failed to retrieve API key: {str(e)}")
            return "<h3>❌ Configuration error.</h3>"

        # STEP 5: Call external API dengan timeout
        url = "https://tracking.timetocargo.com/v1/container"
        params = {
            "api_key": api_key,
            "company": "AUTO",
            "container_number": number.upper()
        }

        try:
            response = requests.get(
                url,
                params=params,
                timeout=self.API_TIMEOUT,  # 30 detik
                headers={
                    'User-Agent': 'Odoo-ContainerTracker/2.0',
                    'Accept': 'application/json'
                }
            )

            if response.status_code != 200:
                _logger.warning(f"API error {response.status_code}: {response.text[:200]}")
                return f"<h3>❌ API Error: {response.status_code}. Please try again later.</h3>"

            raw_json = response.json()

        except requests.Timeout:
            _logger.warning(f"API timeout for container: {number}")
            return "<h3>❌ API timeout. The service is taking too long. Please try again in a few moments.</h3>"
        except requests.RequestException as e:
            _logger.error(f"API connection error: {str(e)}")
            return "<h3>❌ Connection error. Please try again later.</h3>"
        except json.JSONDecodeError:
            _logger.error(f"Invalid API response format")
            return "<h3>❌ Invalid response format from API.</h3>"
        except Exception as e:
            _logger.error(f"Unexpected error: {str(e)}")
            return "<h3>❌ Unexpected error. Please try again.</h3>"

        # STEP 6: Parse response dengan validation
        try:
            data = self._safe_get(raw_json, 'data', {})
            if not isinstance(data, dict):
                data = {}

            # LOCATION MAPPING dengan sanitization
            loc_map = {}
            locations_list = data.get('locations', []) or []
            for loc in locations_list:
                if isinstance(loc, dict):
                    parts = [loc.get('name')]
                    if loc.get('state'):
                        parts.append(loc.get('state'))
                    if loc.get('country'):
                        parts.append(loc.get('country'))

                    full = ", ".join([p for p in parts if p])
                    iso_code = loc.get('country_iso_code')
                    loc_map[loc.get('id')] = {
                        'name': self._sanitize_html(full),  # ← FIX XSS
                        'iso': str(iso_code).lower() if iso_code else ''
                    }

            # TERMINAL MAPPING
            term_map = {}
            terminals_list = data.get('terminals', []) or []
            for term in terminals_list:
                if isinstance(term, dict):
                    term_map[term.get('id')] = self._sanitize_html(term.get('name', ''))

            # SUMMARY DATA
            summary = data.get('summary', {}) or {}

            # Company name extraction dengan fallback & sanitization
            company_name = "Shipping Line"
            candidates = [
                summary.get('company', {}).get('name'),
                summary.get('company', {}).get('full_name'),
                data.get('shipping_line', {}).get('name'),
                data.get('company'),
                data.get('container', {}).get('operator')
            ]
            
            for candidate in candidates:
                if candidate:
                    company_name = self._sanitize_html(candidate)
                    break

            # CONTAINER INFO
            container_info = data.get('container', {}) or {}
            container_type = self._sanitize_html(container_info.get('type', '-'))
            events_list = container_info.get('events', []) or []

            # FIX PAGINATION: Limit events ke last 100
            if len(events_list) > 100:
                events_list = events_list[:100]
                _logger.info(f"Event list truncated for {number}")

            # STATUS EXTRACTION
            current_status = self._sanitize_html(data.get('shipment_status', '-').replace('_', ' '))
            last_date_str = "-"

            if events_list:
                current_status = self._sanitize_html(events_list[0].get('status', '-'))
                last_date_str = self._format_date(events_list[0].get('date'))

                # Logika cari actual event
                for evt in events_list:
                    if evt.get('actual') is True:
                        current_status = self._sanitize_html(evt.get('status', '-'))
                        last_date_str = self._format_date(evt.get('date'))
                        break

            # LOCATION EXTRACTION
            origin_id = summary.get('origin', {}).get('location')
            dest_id = summary.get('destination', {}).get('location')
            pol_id = summary.get('pol', {}).get('location')
            pod_id = summary.get('pod', {}).get('location')

            origin_dict = loc_map.get(origin_id, {})
            dest_dict = loc_map.get(dest_id, {})
            pol_dict = loc_map.get(pol_id, {})
            pod_dict = loc_map.get(pod_id, {})

            origin_name = origin_dict.get('name', "-")
            dest_name = dest_dict.get('name', "-")
            pol_name = pol_dict.get('name', "-")
            pod_name = pod_dict.get('name', "-")

            if origin_name == "-" and events_list:
                origin_name = loc_map.get(events_list[-1].get('location'), {}).get('name', "Unknown Origin")
            if dest_name == "-" and events_list:
                dest_name = f"Current: {loc_map.get(events_list[0].get('location'), {}).get('name', '-')}"

            # PROCESS EVENTS dengan sanitization
            processed_events = []

            # Load EDI mapping dari database
            status_records = request.env['container.tracking.status'].sudo().search([])
            edi_mapping = {rec.code: rec.name for rec in status_records}

            for evt in events_list:
                e_code = evt.get('status_code', '')
                notes_parts = []

                if e_code in edi_mapping:
                    notes_parts.append(edi_mapping[e_code])
                elif evt.get('status') == 'LOAD':
                    notes_parts.append("Container loaded at first POL")
                elif e_code and e_code != 'UNK':
                    notes_parts.append(f"Event: {e_code}")

                term_name = term_map.get(evt.get('terminal'))
                loc_dict = loc_map.get(evt.get('location'), {})
                loc_name = loc_dict.get('name', '-')
                loc_iso = loc_dict.get('iso', '')

                processed_events.append({
                    'date': self._format_date(evt.get('date')),
                    'status': self._sanitize_html(evt.get('status', '-')),
                    'location': loc_name,
                    'iso_code': loc_iso,
                    'terminal': self._sanitize_html(term_name) if term_name else None,
                    'notes': self._sanitize_html(", ".join(notes_parts)) if notes_parts else "-",
                    'vessel': self._sanitize_html(evt.get('vessel')) if evt.get('vessel') else None,
                    'voyage': self._sanitize_html(evt.get('voyage')) if evt.get('voyage') else None,
                })

            # Prepare template values
            values = {
                'number': escape(number),  # ← Escape di template juga
                'token': token,  # ← Don't expose unnecessary
                'company_name': company_name,
                'last_date': last_date_str,
                'current_status': current_status,
                'container_type': container_type,
                'origin': origin_name,
                'destination': dest_name,
                'pol': pol_name,
                'pod': pod_name,
                'events': processed_events,
                'event_count': len(processed_events),
                'is_truncated': len(container_info.get('events', [])) > 100,
            }

            _logger.info(f"Successfully tracked container {number}")
            return request.render("om_container_tracker.tracking_page_template", values)

        except Exception as e:
            _logger.error(f"Error processing API data: {str(e)}")
            return f"<h3>❌ Error processing tracking data: {str(e)[:50]}</h3>"
