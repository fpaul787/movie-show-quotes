from django.urls import path

from . import views

urlpatterns = [
    path("csrf", views.csrf, name="csrf"),
    path("me", views.current_user, name="current-user"),
    path("signup", views.signup, name="signup"),
    path("login", views.login_view, name="login"),
]
