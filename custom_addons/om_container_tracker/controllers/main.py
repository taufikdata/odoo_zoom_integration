from odoo import http
from odoo.http import request
import requests
import json
import hashlib
import logging
import re
from datetime import datetime, timedelta
from html import escape

_logger = logging.getLogger(__name__)

class ContainerTrackingController(http.Controller):
    """Security hardened v2.0: rate limiting, XSS protection, input validation"""

    MAX_REQUESTS_PER_IP = 10  # Issue #1: Brute force protection
    MAX_REQUESTS_PER_TOKEN = 5
    RATE_LIMIT_WINDOW = 3600  # 1 hour
    CONTAINER_FORMAT = r'^[A-Z]{4}[0-9]{6,7}$'  # Issue #4: Input validation (ISO 6346)
    API_TIMEOUT = 30  # Issue #10: Optimized timeout
    MAX_EVENTS = 100  # Issue #9: Pagination

    def _safe_get(self, data, key, default=None):
        if isinstance(data, dict): return data.get(key, default)
        return default

    def _format_date(self, date_str):
        if not date_str: return "-"
        try:
            clean_date = str(date_str).replace('Z', '').split('.')[0]
            dt_obj = datetime.fromisoformat(clean_date)
            return dt_obj.strftime("%m/%d/%y | %I:%M %p")
        except Exception as e:
            _logger.warning(f"Date format error: {str(e)}")
            return "-"

    def _sanitize_html(self, text):
        """Issue #2: XSS Protection - escape all user input"""
        if not text:
            return ""
        sanitized = escape(str(text))
        dangerous_patterns = ['<script', 'javascript:', 'onerror=', 'onclick=']
        for pattern in dangerous_patterns:
            if pattern.lower() in sanitized.lower():
                _logger.warning(f"Potential XSS detected: {pattern}")
                return "[TEXT FILTERED]"
        return sanitized

    def _validate_container_number(self, number):
        """Issue #4: Input validation - ISO 6346 format"""
        if not number or len(str(number)) > 20:
            return False
        if re.match(self.CONTAINER_FORMAT, number.upper()):
            return True
        _logger.warning(f"Invalid container format: {number}")
        return False

    def _check_rate_limit(self, identifier, limit_type='ip'):
        """Issue #1: Rate limiting to prevent brute force"""
        try:
            cache_key = f"container_track_{limit_type}_{identifier}"
            IrConfigParameter = request.env['ir.config_parameter'].sudo()
            current_time = datetime.now().timestamp()
            
            last_request_data = IrConfigParameter.get_param(cache_key)
            max_limit = self.MAX_REQUESTS_PER_IP if limit_type == 'ip' else self.MAX_REQUESTS_PER_TOKEN
            
            if last_request_data:
                data = json.loads(last_request_data)
                requests_in_window = data.get('count', 0)
                first_request_time = data.get('timestamp', current_time)
                
                if current_time - first_request_time > self.RATE_LIMIT_WINDOW:
                    requests_in_window = 0
                    first_request_time = current_time
            else:
                requests_in_window = 0
                first_request_time = current_time
            
            if requests_in_window >= max_limit:
                _logger.warning(f"Rate limit exceeded for {limit_type}: {identifier}")
                return (False, 0, first_request_time + self.RATE_LIMIT_WINDOW)
            
            requests_in_window += 1
            data = {'count': requests_in_window, 'timestamp': first_request_time}
            IrConfigParameter.set_param(cache_key, json.dumps(data))
            remaining = max_limit - requests_in_window
            
            return (True, remaining, None)
        except Exception as e:
            _logger.error(f"Rate limit check failed: {str(e)}")
            return (True, -1, None)

    def _get_client_ip(self):
        """Get actual client IP handling proxies"""
        if request.httprequest.environ.get('HTTP_X_FORWARDED_FOR'):
            return request.httprequest.environ['HTTP_X_FORWARDED_FOR'].split(',')[0].strip()
        return request.httprequest.remote_addr or '0.0.0.0'

    def _log_tracking_attempt(self, container, token, ip, success, response_time=None):
        """Issue #8: Audit logging for monitoring"""
        try:
            AuditModel = request.env['container.tracking.audit'].sudo()
            AuditModel.create({
                'container_number': container,
                'access_token': token[:20] if token else '',
                'client_ip': ip,
                'success': success,
                'response_time_ms': int(response_time * 1000) if response_time else 0,
            })
        except Exception as e:
            _logger.error(f"Failed to log tracking attempt: {str(e)}")

    @http.route('/tracking/container', type='http', auth='public', website=True, csrf=True)
    def track_container_page(self, number=None, token=None, **kwargs):
        start_time = datetime.now()
        
        # STEP 1: Validate input
        if not number or not token:
            _logger.info(f"Missing parameters: {self._get_client_ip()}")
            return "<h3>❌ Access Denied: Invalid Tracking Link.</h3>"

        if not self._validate_container_number(number):
            _logger.warning(f"Invalid container format: {number}")
            return "<h3>❌ Invalid Container Number Format. Expected: CSNU6184414</h3>"

        # STEP 2: Rate limiting
        client_ip = self._get_client_ip()
        ip_allowed, _, _ = self._check_rate_limit(client_ip, 'ip')
        if not ip_allowed:
            _logger.warning(f"Rate limit exceeded from IP: {client_ip}")
            return "<h3>⏱️ Too many requests. Please try again later.</h3>"

        token_allowed, _, _ = self._check_rate_limit(token, 'token')
        if not token_allowed:
            _logger.warning(f"Rate limit exceeded for token: {token[:20]}")
            return "<h3>⏱️ Tracking token has reached rate limit.</h3>"

        # STEP 3: Security check
        try:
            sale_order = request.env['sale.order'].sudo().search([
                ('container_number', '=', number.upper()),
                ('access_token', '=', token)
            ], limit=1)

            if not sale_order:
                _logger.info(f"Unauthorized access: {number}")
                self._log_tracking_attempt(number, token, client_ip, False)
                return "<h3>🔒 Unauthorized Access.</h3>"
        except Exception as e:
            _logger.error(f"Database error: {str(e)}")
            return "<h3>❌ System error.</h3>"

        # STEP 4: Get API key
        try:
            api_key = request.env['ir.config_parameter'].sudo().get_param('timetocargo.api_key')
            if not api_key:
                _logger.error("API key not configured")
                return "<h3>❌ System not configured. Contact support.</h3>"
        except Exception as e:
            _logger.error(f"Failed to retrieve API key: {str(e)}")
            return "<h3>❌ Configuration error.</h3>"

        # STEP 5: Call API
        url = "https://tracking.timetocargo.com/v1/container"
        params = {"api_key": api_key, "company": "AUTO", "container_number": number.upper()}

        try:
            response = requests.get(url, params=params, timeout=self.API_TIMEOUT,
                                  headers={'User-Agent': 'Odoo-ContainerTracker/2.0'})

            if response.status_code != 200:
                _logger.warning(f"API error {response.status_code}")
                self._log_tracking_attempt(number, token, client_ip, False, 
                                         (datetime.now() - start_time).total_seconds())
                return "<h3>❌ API Error. Try again later.</h3>"

            raw_json = response.json()
        except requests.Timeout:
            _logger.warning(f"API timeout for {number}")
            self._log_tracking_attempt(number, token, client_ip, False,
                                     (datetime.now() - start_time).total_seconds())
            return "<h3>❌ API timeout. Try again later.</h3>"
        except requests.RequestException as e:
            _logger.error(f"API connection error: {str(e)}")
            return "<h3>❌ Connection error.</h3>"
        except json.JSONDecodeError:
            _logger.error("Invalid API response")
            return "<h3>❌ Invalid API response.</h3>"
        except Exception as e:
            _logger.error(f"Unexpected error: {str(e)}")
            return "<h3>❌ Unexpected error.</h3>"

        # STEP 6: Parse response with sanitization
        try:
            data = self._safe_get(raw_json, 'data', {})
            if not isinstance(data, dict): data = {}

            # Location mapping with XSS protection
            loc_map = {}
            locations_list = data.get('locations', []) or []
            for loc in locations_list:
                if isinstance(loc, dict):
                    parts = [loc.get('name')]
                    if loc.get('state'): parts.append(loc.get('state'))
                    if loc.get('country'): parts.append(loc.get('country'))
                    full = ", ".join([p for p in parts if p])
                    iso_code = loc.get('country_iso_code')
                    loc_map[loc.get('id')] = {
                        'name': self._sanitize_html(full),
                        'iso': str(iso_code).lower() if iso_code else ''
                    }

            # Terminal mapping
            term_map = {}
            terminals_list = data.get('terminals', []) or []
            for term in terminals_list:
                if isinstance(term, dict):
                    term_map[term.get('id')] = self._sanitize_html(term.get('name', ''))

            summary = data.get('summary', {}) or {}
            
            # Company name extraction with sanitization
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

            container_info = data.get('container', {}) or {}
            container_type = self._sanitize_html(container_info.get('type', '-'))
            events_list = container_info.get('events', []) or []
            
            # Issue #9: Pagination - limit events
            if len(events_list) > self.MAX_EVENTS:
                events_list = events_list[:self.MAX_EVENTS]
                _logger.info(f"Event list truncated for {number}")

            current_status = self._sanitize_html(data.get('shipment_status', '-').replace('_', ' '))
            last_date_str = "-"
            
            if events_list:
                current_status = self._sanitize_html(events_list[0].get('status', '-'))
                last_date_str = self._format_date(events_list[0].get('date'))
                for evt in events_list:
                    if evt.get('actual') is True:
                        current_status = self._sanitize_html(evt.get('status', '-'))
                        last_date_str = self._format_date(evt.get('date'))
                        break

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
                origin_name = loc_map.get(events_list[-1].get('location'), {}).get('name', "Unknown")
            if dest_name == "-" and events_list: 
                dest_name = f"Current: {loc_map.get(events_list[0].get('location'), {}).get('name', '-')}"

            # Process Events
            processed_events = []
            status_records = request.env['container.tracking.status'].sudo().search([])
            edi_mapping = {rec.code: rec.name for rec in status_records}

            for evt in events_list:
                e_code = evt.get('status_code', '')
                notes_parts = []
                
                if e_code in edi_mapping:
                    notes_parts.append(edi_mapping[e_code])
                elif evt.get('status') == 'LOAD':
                    notes_parts.append("Container loaded at POL")
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

            values = {
                'number': escape(number),
                'token': token,
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
                'is_truncated': len(container_info.get('events', [])) > self.MAX_EVENTS,
            }

            response_time = (datetime.now() - start_time).total_seconds()
            self._log_tracking_attempt(number, token, client_ip, True, response_time)
            _logger.info(f"Successfully tracked {number} ({response_time:.2f}s)")
            return request.render("om_container_tracker.tracking_page_template", values)

        except Exception as e:
            _logger.error(f"Error processing data: {str(e)}")
            response_time = (datetime.now() - start_time).total_seconds()
            self._log_tracking_attempt(number, token, client_ip, False, response_time)
            return "<h3>❌ Error processing data.</h3>"