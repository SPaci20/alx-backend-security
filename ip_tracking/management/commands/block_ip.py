from django.core.management.base import BaseCommand, CommandError
from django.core.cache import cache
from django.core.validators import validate_ipv46_address
from django.core.exceptions import ValidationError
from ip_tracking.models import BlockedIP


class Command(BaseCommand):
    help = 'Block an IP address by adding it to the BlockedIP model'

    def add_arguments(self, parser):
        parser.add_argument(
            'ip_address',
            type=str,
            help='IP address to block (IPv4 or IPv6)'
        )
        parser.add_argument(
            '--reason',
            type=str,
            help='Reason for blocking this IP address',
            default=''
        )
        parser.add_argument(
            '--unblock',
            action='store_true',
            help='Remove IP address from blocked list instead of adding it'
        )

    def handle(self, *args, **options):
        ip_address = options['ip_address']
        reason = options['reason']
        unblock = options['unblock']

        # Validate IP address format
        try:
            validate_ipv46_address(ip_address)
        except ValidationError:
            raise CommandError(f'"{ip_address}" is not a valid IP address.')

        if unblock:
            # Remove IP from blocked list
            try:
                blocked_ip = BlockedIP.objects.get(ip_address=ip_address)
                blocked_ip.delete()
                
                # Clear from cache
                cache_key = f"blocked_ip_{ip_address}"
                cache.delete(cache_key)
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Successfully unblocked IP address: {ip_address}'
                    )
                )
            except BlockedIP.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(
                        f'IP address {ip_address} was not in the blocked list.'
                    )
                )
        else:
            # Add IP to blocked list
            blocked_ip, created = BlockedIP.objects.get_or_create(
                ip_address=ip_address,
                defaults={'reason': reason}
            )
            
            if created:
                # Clear cache to ensure immediate blocking
                cache_key = f"blocked_ip_{ip_address}"
                cache.set(cache_key, True, 300)
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Successfully blocked IP address: {ip_address}'
                    )
                )
                if reason:
                    self.stdout.write(f'Reason: {reason}')
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f'IP address {ip_address} is already blocked.'
                    )
                )
                
                # Update reason if provided
                if reason and blocked_ip.reason != reason:
                    blocked_ip.reason = reason
                    blocked_ip.save()
                    self.stdout.write(f'Updated reason: {reason}')