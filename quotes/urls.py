from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("quotes/random", views.random_quote, name="random-quote"),
]
