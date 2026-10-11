from django.http import JsonResponse


def quote(request):
    return JsonResponse({"message": "Hello World"})
