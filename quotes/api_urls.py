from django.urls import path, re_path

from . import views

app_name = "api_v1"

urlpatterns = [
    path("quotes/random/", views.random_quote, name="random-quote"),
    re_path(r"^.*$", views.api_not_found, name="not-found"),
]
