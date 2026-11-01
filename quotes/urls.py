from django.urls import path, re_path
from django.views.generic import RedirectView

from . import views

urlpatterns = [
    path("", views.react_homepage, name="home"),
    re_path(r"^homepage/?$", RedirectView.as_view(url="/", permanent=True)),
    re_path(r"^signup/?$", views.react_homepage, name="signup"),
    path("quotes/random", views.random_quote, name="random-quote"),
]
