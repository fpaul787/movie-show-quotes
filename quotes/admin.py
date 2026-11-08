from django import forms
from django.contrib import admin, messages

from .models import APIKey, Character, Media, Quote


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


@admin.register(Media)
class MediaAdmin(admin.ModelAdmin):
    list_display = ("title", "media_type", "release_year", "external_id")
    list_filter = ("media_type", "release_year")
    search_fields = ("title", "external_id")


@admin.register(Character)
class CharacterAdmin(admin.ModelAdmin):
    list_display = ("name", "media")
    search_fields = ("name", "media__title")
    autocomplete_fields = ("media",)

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = super().get_readonly_fields(request, obj)
        if obj is not None and obj.quotes.exists():
            return (*readonly_fields, "media")
        return readonly_fields


class QuoteAdminForm(forms.ModelForm):
    class Meta:
        model = Quote
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tags"].required = False
        self.fields["tags"].help_text = 'JSON list, e.g. ["drama", "classic"]'

    def clean_tags(self):
        tags = self.cleaned_data["tags"]
        return [] if tags is None else tags


@admin.register(Quote)
class QuoteAdmin(admin.ModelAdmin):
    form = QuoteAdminForm
    list_display = ("media", "character", "language", "created_at")
    list_filter = ("media__media_type", "language", "media__release_year")
    search_fields = ("text", "media__title", "character__name")
    list_select_related = ("media", "character")
    autocomplete_fields = ("media", "character")
    ordering = ("-created_at",)
