from django.urls import path, re_path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    re_path(r"^homepage/?$", views.react_homepage, name="react-homepage"),
    path("quotes/random", views.random_quote, name="random-quote"),
]
