from django.urls import path, re_path

from . import views

app_name = "api_v1"

urlpatterns = [
    path("quotes/", views.quote_list, name="quote-list"),
    path("quotes/random/", views.random_quote, name="random-quote"),
    path("quotes/<int:pk>/", views.quote_detail, name="quote-detail"),
    re_path(r"^.*$", views.api_not_found, name="not-found"),
]
