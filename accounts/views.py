import json

from django.contrib.auth import authenticate, login, logout as django_logout
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .forms import EmailUpdateForm, SignupForm


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
        request.user.save(update_fields=["email"])

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

    user = form.save()
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
    user = authenticate(request, username=username, password=password)
    if user is None:
        return JsonResponse({"error": "Invalid username or password"}, status=401)

    login(request, user)
    return JsonResponse({"id": user.pk, "username": user.username})


@require_POST
def logout_view(request):
    django_logout(request)
    return JsonResponse({"success": True})
