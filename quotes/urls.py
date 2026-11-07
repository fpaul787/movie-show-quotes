from django.urls import path, re_path
from django.views.generic import RedirectView

from . import views

urlpatterns = [
    path("", views.react_homepage, name="home"),
    re_path(r"^homepage/?$", RedirectView.as_view(url="/", permanent=True)),
    re_path(r"^login/?$", views.react_homepage, name="login"),
    re_path(r"^signup/?$", views.react_homepage, name="signup"),
    re_path(r"^profile/?$", views.react_homepage, name="profile"),
    re_path(r"^profile/api-keys/?$", views.react_homepage, name="profile-api-keys"),
    path("api/keys", views.api_key, name="api-key"),
    path("quotes/random", views.random_quote, name="random-quote"),
]
