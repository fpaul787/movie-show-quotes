import datetime

from django import forms
from django.contrib import admin

from .models import Quote


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
