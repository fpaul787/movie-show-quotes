from django.http import JsonResponse


def api_error(code, message, status):
    return JsonResponse({"error": {"code": code, "message": message}}, status=status)
