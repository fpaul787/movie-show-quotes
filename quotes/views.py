from datetime import date

from django.http import JsonResponse

from .models import Quote


def quote(request):
    quote, _ = Quote.objects.get_or_create(
        text="May the Force be with you.",
        year=1977,
        title="Star Wars",
        character="Han Solo",
        source="Movie",
        language="English",
        tags=["classic", "sci-fi"],
        created_at=date(1977, 5, 25),
    )
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
