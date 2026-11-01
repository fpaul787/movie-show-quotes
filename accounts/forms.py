from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import BaseUserCreationForm


class EmailUpdateForm(forms.Form):
    email = forms.EmailField(required=False, max_length=254)


class SignupForm(BaseUserCreationForm):
    class Meta:
        model = get_user_model()
        fields = ("username", "email")
