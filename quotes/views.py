from django.http import JsonResponse

from .models import Quote


def quote(request):
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
