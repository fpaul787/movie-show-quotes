from django.db import models


class Quote(models.Model):
    text = models.TextField()
    year = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=255)
    character = models.CharField(max_length=255)
    source = models.CharField(max_length=50)
    language = models.CharField(max_length=50)
    tags = models.JSONField(default=list)
    created_at = models.DateField()

    def __str__(self):
        return f"{self.title} — {self.character}"
