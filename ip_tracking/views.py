from django.http import JsonResponse
from ratelimit.decorators import ratelimit

# Helper: distinguish authenticated vs anonymous users
def user_or_ip(group, request):
    if request.user.is_authenticated:
        return str(request.user.pk)  # Rate-limit by user ID
    return request.META.get("REMOTE_ADDR")  # Fallback: IP address

# Sensitive login view with rate limiting
@ratelimit(key='ip', rate='5/m', method='POST', block=True)  # Anonymous users: 5/minute
@ratelimit(key=user_or_ip, rate='10/m', method='POST', block=True)  # Authenticated: 10/minute
def login_view(request):
    if request.method == "POST":
        # TODO: Hook this into your actual authentication logic
        return JsonResponse({"message": "Login attempt processed"})
    return JsonResponse({"error": "Only POST requests are allowed"}, status=405)
