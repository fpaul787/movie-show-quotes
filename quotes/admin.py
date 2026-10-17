import datetime

from django import forms
from django.contrib import admin, messages

from .models import APIKey, Quote


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = ("name", "prefix", "owner", "is_active", "expires_at", "last_used_at")
    list_filter = ("is_active",)
    search_fields = ("name", "prefix")
    readonly_fields = ("prefix", "created_at", "last_used_at")

    def save_model(self, request, obj, form, change):
        raw_key = None if change else obj.set_new_key()
        super().save_model(request, obj, form, change)
        if raw_key:
            self.message_user(
                request,
                f"API key for '{obj.name}' (copy it now, it won't be shown again): {raw_key}",
                messages.WARNING,
            )


class QuoteAdminForm(forms.ModelForm):
    class Meta:
        model = Quote
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["created_at"].initial = datetime.date.today
        self.fields["tags"].help_text = 'JSON list, e.g. ["drama", "classic"]'


@admin.register(Quote)
class QuoteAdmin(admin.ModelAdmin):
    form = QuoteAdminForm
    list_display = ("title", "character", "year", "source", "language", "created_at")
    list_filter = ("source", "language", "year")
    search_fields = ("text", "title", "character")
    ordering = ("-created_at",)
