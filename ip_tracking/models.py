from django.db import models
from django.utils import timezone


class RequestLog(models.Model):
    """
    Model to store request logging information including IP address,
    timestamp, and request path.
    """
    ip_address = models.GenericIPAddressField(
        help_text="IP address of the client making the request"
    )
    timestamp = models.DateTimeField(
        default=timezone.now,
        help_text="Timestamp when the request was made"
    )
    path = models.CharField(
        max_length=500,
        help_text="Request path/URL"
    )

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Request Log"
        verbose_name_plural = "Request Logs"

    def __str__(self):
        return f"{self.ip_address} - {self.path} at {self.timestamp}"


class BlockedIP(models.Model):
    """
    Model to store blocked IP addresses.
    """
    ip_address = models.GenericIPAddressField(
        unique=True,
        help_text="IP address to be blocked"
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        help_text="Timestamp when the IP was blocked"
    )
    reason = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Reason for blocking this IP address"
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Blocked IP"
        verbose_name_plural = "Blocked IPs"

    def __str__(self):
        return f"Blocked IP: {self.ip_address}"