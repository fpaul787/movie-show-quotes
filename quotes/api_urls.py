from django.urls import path, re_path
from django.views.generic import RedirectView

from . import views

app_name = "api_v1"

urlpatterns = [
    path("quotes/", views.quote_list, name="quote-list"),
    path("quotes/random/", views.random_quote, name="random-quote"),
    path("quotes/<int:pk>/", views.quote_detail, name="quote-detail"),
    path("media/movies/", views.movie_list, name="movie-list"),
    path("media/tv-shows/", views.tv_show_list, name="tv-show-list"),
    path("media/<int:pk>/", views.media_detail, name="media-detail"),
    path("openapi.json", views.openapi_schema, name="openapi"),
    path("docs/", views.api_docs, name="docs"),
    path(
        "docs",
        RedirectView.as_view(pattern_name="api_v1:docs", permanent=True, query_string=True),
        name="docs-redirect",
    ),
    re_path(r"^.*$", views.api_not_found, name="not-found"),
]
