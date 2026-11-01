from django.http import JsonResponse
from django.shortcuts import render

from .auth import api_key_required
from .models import Quote


def react_homepage(request):
    username = request.user.username if request.user.is_authenticated else ""
    return render(request, "quotes/homepage.html", {"username": username})


@api_key_required
def random_quote(request):
    quote = Quote.objects.order_by("?").first()
    if quote is None:
        return JsonResponse({"error": "No quotes available"}, status=404)
    return JsonResponse(
        {
            "text": quote.text,
            "year": quote.year,
            "title": quote.title,
            "character": quote.character,
            "source": quote.source,
            "language": quote.language,
            "tags": quote.tags,
            "created_at": quote.created_at.isoformat(),
        }
    )
