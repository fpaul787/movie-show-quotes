from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import BaseUserCreationForm


EMAIL_TAKEN = "A user with that email already exists."


def email_in_use(email, exclude_pk=None):
    if not email:
        return False
    users = get_user_model().objects.filter(email__iexact=email)
    if exclude_pk is not None:
        users = users.exclude(pk=exclude_pk)
    return users.exists()


class EmailUpdateForm(forms.Form):
    email = forms.EmailField(required=False, max_length=254)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_email(self):
        email = self.cleaned_data["email"]
        if email_in_use(email, exclude_pk=self.user.pk if self.user else None):
            raise forms.ValidationError(EMAIL_TAKEN, code="unique")
        return email


class SignupForm(BaseUserCreationForm):
    class Meta:
        model = get_user_model()
        fields = ("username", "email")

    def clean_email(self):
        email = self.cleaned_data["email"]
        if email_in_use(email):
            raise forms.ValidationError(EMAIL_TAKEN, code="unique")
        return email
