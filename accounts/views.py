import json

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth import authenticate, login, logout as django_logout
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from . import throttle
from .forms import EMAIL_TAKEN, EmailUpdateForm, SignupForm

EMAIL_CONSTRAINT = "unique_user_email_ci"


def is_email_conflict(error):
    return EMAIL_CONSTRAINT in str(error)


def email_conflict_response():
    return JsonResponse(
        {"errors": {"email": [{"message": EMAIL_TAKEN, "code": "unique"}]}},
        status=400,
    )


@require_GET
@ensure_csrf_cookie
def csrf(request):
    return JsonResponse({"csrfToken": get_token(request)})


@require_GET
def current_user(request):
    if not request.user.is_authenticated:
        return JsonResponse({"user": None})

    return JsonResponse(
        {
            "user": {
                "id": request.user.pk,
                "username": request.user.username,
            }
        }
    )


@require_http_methods(["GET", "PATCH"])
def profile(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)

    if request.method == "PATCH":
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        if not isinstance(data, dict) or "email" not in data:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        form = EmailUpdateForm(data, user=request.user)
        if not form.is_valid():
            return JsonResponse({"errors": form.errors.get_json_data()}, status=400)

        request.user.email = form.cleaned_data["email"]
        try:
            with transaction.atomic():
                request.user.save(update_fields=["email"])
        except IntegrityError as error:
            if not is_email_conflict(error):
                raise
            return email_conflict_response()

    return JsonResponse(
        {"username": request.user.username, "email": request.user.email or None}
    )


@require_POST
def signup(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    form = SignupForm(data)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)

    try:
        with transaction.atomic():
            if get_user_model().objects.count() >= settings.MAX_USERS:
                return JsonResponse({"error": "Limit reached"}, status=403)
            user = form.save()
    except IntegrityError as error:
        if not is_email_conflict(error):
            raise
        return email_conflict_response()
    return JsonResponse({"id": user.pk, "username": user.username}, status=201)


@require_POST
def login_view(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    username = data.get("username")
    password = data.get("password")
    if not isinstance(username, str) or not isinstance(password, str):
        return JsonResponse(
            {"error": "Username and password are required"}, status=400
        )

    username = SignupForm.base_fields["username"].to_python(username)
    throttle_username = throttle.normalize_username(username)
    ip = throttle.client_ip(request)
    if throttle.reserve_attempt(throttle_username, ip):
        return JsonResponse(
            {"error": "Too many login attempts. Try again later."}, status=429
        )
    user = authenticate(request, username=username, password=password)
    if user is None:
        return JsonResponse({"error": "Invalid username or password"}, status=401)

    throttle.release_success(throttle_username, ip)
    login(request, user)
    return JsonResponse({"id": user.pk, "username": user.username})


@require_POST
def logout_view(request):
    django_logout(request)
    return JsonResponse({"success": True})
