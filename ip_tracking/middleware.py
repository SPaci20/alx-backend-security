import logging
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin
from django.http import HttpResponseForbidden
from django.core.cache import cache
from .models import RequestLog, BlockedIP


class IPTrackingMiddleware(MiddlewareMixin):
    """
    Middleware to log IP address, timestamp, and path of every incoming request.
    Also blocks requests from IPs in the BlockedIP model.
    """
    
    def __init__(self, get_response=None):
        super().__init__(get_response)
        self.logger = logging.getLogger('ip_tracking')
    
    def process_request(self, request):
        """
        Process incoming request, check if IP is blocked, and log the details.
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
            
            # Create log entry in database
            RequestLog.objects.create(
                ip_address=ip_address,
                timestamp=timezone.now(),
                path=path
            )
            
            # Also log to Django's logging system
            self.logger.info(
                f"Request logged: IP={ip_address}, Path={path}, "
                f"Timestamp={timezone.now()}"
            )
            
        except Exception as e:
            # Log any errors but don't interrupt the request flow
            self.logger.error(f"Error processing request: {str(e)}")
        
        return None  # Continue processing the request
    
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