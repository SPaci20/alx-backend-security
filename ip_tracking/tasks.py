from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from .models import RequestLog, SuspiciousIP


@shared_task
def detect_suspicious_ips():
    """
    Detect IPs with unusual behavior:
    - More than 100 requests in the last hour
    - Accessing sensitive paths (e.g., /admin, /login)
    """
    one_hour_ago = timezone.now() - timedelta(hours=1)

    # Count requests per IP in the last hour
    request_counts = (
        RequestLog.objects
        .filter(timestamp__gte=one_hour_ago)
        .values('ip_address')
        .annotate(count=models.Count('id'))
    )

    # Flag IPs exceeding 100 requests/hour
    for entry in request_counts:
        ip = entry['ip_address']
        count = entry['count']
        if count > 100:
            SuspiciousIP.objects.get_or_create(
                ip_address=ip,
                defaults={'reason': f"{count} requests in the last hour"}
            )

    # Flag IPs accessing sensitive paths
    sensitive_paths = ['/admin', '/login']
    logs = RequestLog.objects.filter(timestamp__gte=one_hour_ago, path__in=sensitive_paths)
    for log in logs:
        SuspiciousIP.objects.get_or_create(
            ip_address=log.ip_address,
            defaults={'reason': f"Accessed sensitive path: {log.path}"}
        )
