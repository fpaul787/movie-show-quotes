from django.urls import path

from . import views

urlpatterns = [
    path("csrf", views.csrf, name="csrf"),
    path("signup", views.signup, name="signup"),
]
