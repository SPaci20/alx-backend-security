import logging
import requests
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin
from django.http import HttpResponseForbidden
from django.core.cache import cache
from django.conf import settings
from .models import RequestLog, BlockedIP


class IPTrackingMiddleware(MiddlewareMixin):
    """
    Middleware to log IP address, timestamp, path, and geolocation data of every incoming request.
    Also blocks requests from IPs in the BlockedIP model.
    """
    
    def __init__(self, get_response=None):
        super().__init__(get_response)
        self.logger = logging.getLogger('ip_tracking')
        # Timeout for geolocation API requests (seconds)
        self.geo_timeout = 5
    
    def process_request(self, request):
        """
        Process incoming request, check if IP is blocked, get geolocation, and log the details.
        """
        try:
            # Get the client's IP address
            ip_address = self.get_client_ip(request)
            
            # Check if IP is blocked
            if self.is_ip_blocked(ip_address):
                self.logger.warning(
                    f"Blocked request from IP: {ip_address}, "
                    f"Path: {request.get_full_path()}"
                )
                return HttpResponseForbidden(
                    "<h1>403 Forbidden</h1>"
                    "<p>Your IP address has been blocked.</p>"
                )
            
            # Get the request path
            path = request.get_full_path()
            
            # Get geolocation data
            geo_data = self.get_geolocation(ip_address)
            
            # Create log entry in database
            RequestLog.objects.create(
                ip_address=ip_address,
                timestamp=timezone.now(),
                path=path,
                country=geo_data.get('country'),
                city=geo_data.get('city')
            )
            
            # Also log to Django's logging system
            location_info = ""
            if geo_data.get('city') and geo_data.get('country'):
                location_info = f", Location: {geo_data['city']}, {geo_data['country']}"
            elif geo_data.get('country'):
                location_info = f", Location: {geo_data['country']}"
            
            self.logger.info(
                f"Request logged: IP={ip_address}, Path={path}, "
                f"Timestamp={timezone.now()}{location_info}"
            )
            
        except Exception as e:
            # Log any errors but don't interrupt the request flow
            self.logger.error(f"Error processing request: {str(e)}")
        
        return None  # Continue processing the request
    
    def get_geolocation(self, ip_address):
        """
        Get geolocation data for an IP address using multiple fallback services.
        Caches results for 24 hours to reduce API calls.
        """
        # Skip geolocation for private/local IP addresses
        if self.is_private_ip(ip_address):
            return {'country': None, 'city': None}
        
        cache_key = f"geolocation_{ip_address}"
        
        # Try to get from cache first
        geo_data = cache.get(cache_key)
        
        if geo_data is None:
            # Not in cache, fetch from geolocation service
            geo_data = self.fetch_geolocation(ip_address)
            
            # Cache the result for 24 hours (86400 seconds)
            cache.set(cache_key, geo_data, 86400)
        
        return geo_data
    
    def fetch_geolocation(self, ip_address):
        """
        Fetch geolocation data from external APIs with fallback options.
        """
        geo_data = {'country': None, 'city': None}
        
        # List of free geolocation APIs with fallbacks
        apis = [
            {
                'url': f'http://ip-api.com/json/{ip_address}',
                'country_key': 'country',
                'city_key': 'city',
                'status_key': 'status',
                'success_value': 'success'
            },
            {
                'url': f'https://ipapi.co/{ip_address}/json/',
                'country_key': 'country_name',
                'city_key': 'city',
                'error_key': 'error'
            },
            {
                'url': f'http://www.geoplugin.net/json.gp?ip={ip_address}',
                'country_key': 'geoplugin_countryName',
                'city_key': 'geoplugin_city'
            }
        ]
        
        for api in apis:
            try:
                response = requests.get(
                    api['url'], 
                    timeout=self.geo_timeout,
                    headers={'User-Agent': 'Django-IP-Tracker/1.0'}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Check if API returned an error
                    if api.get('error_key') and data.get(api['error_key']):
                        continue
                    
                    if api.get('status_key'):
                        if data.get(api['status_key']) != api.get('success_value'):
                            continue
                    
                    # Extract country and city
                    country = data.get(api['country_key'])
                    city = data.get(api['city_key'])
                    
                    if country and country != 'None':
                        geo_data['country'] = country
                    
                    if city and city != 'None':
                        geo_data['city'] = city
                    
                    # If we got valid data, break out of the loop
                    if geo_data['country']:
                        self.logger.debug(f"Geolocation found for {ip_address}: {geo_data}")
                        break
                        
            except requests.exceptions.RequestException as e:
                self.logger.debug(f"Geolocation API {api['url']} failed: {str(e)}")
                continue
            except (ValueError, KeyError) as e:
                self.logger.debug(f"Error parsing geolocation response: {str(e)}")
                continue
        
        if not geo_data['country']:
            self.logger.debug(f"Could not determine geolocation for {ip_address}")
        
        return geo_data
    
    def is_private_ip(self, ip_address):
        """
        Check if an IP address is private/local.
        """
        try:
            from ipaddress import ip_address as ip_addr
            ip = ip_addr(ip_address)
            return ip.is_private or ip.is_loopback or ip.is_link_local
        except ValueError:
            return True  # If invalid IP, treat as private
    
    def is_ip_blocked(self, ip_address):
        """
        Check if an IP address is in the blocked list.
        Uses caching to improve performance.
        """
        cache_key = f"blocked_ip_{ip_address}"
        
        # Try to get from cache first
        is_blocked = cache.get(cache_key)
        
        if is_blocked is None:
            # Not in cache, check database
            try:
                BlockedIP.objects.get(ip_address=ip_address)
                is_blocked = True
            except BlockedIP.DoesNotExist:
                is_blocked = False
            
            # Cache the result for 5 minutes
            cache.set(cache_key, is_blocked, 300)
        
        return is_blocked
    
    def get_client_ip(self, request):
        """
        Extract the client's real IP address from the request.
        Handles cases where the request comes through proxies or load balancers.
        """
        # Check for IP in X-Forwarded-For header (proxy/load balancer)
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            # Take the first IP in case of multiple IPs
            ip = x_forwarded_for.split(',')[0].strip()
            return ip
        
        # Check for IP in X-Real-IP header (nginx proxy)
        x_real_ip = request.META.get('HTTP_X_REAL_IP')
        if x_real_ip:
            return x_real_ip.strip()
        
        # Fallback to REMOTE_ADDR
        return request.META.get('REMOTE_ADDR', '0.0.0.0')