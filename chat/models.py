"""
Database models for the chat application.
"""
from django.db import models
from django.contrib.auth.models import User


class Conversation(models.Model):
    """A chat session between user and AI assistant."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='conversations')
    title = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'Conversation'
        verbose_name_plural = 'Conversations'

    def __str__(self):
        return self.title


class Message(models.Model):
    """Individual messages in a conversation."""

    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('system', 'System'),
    ]

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'Message'
        verbose_name_plural = 'Messages'

    def __str__(self):
        content_preview = self.content[:50]
        return f"{self.role}: {content_preview}..."


class QueryHistory(models.Model):
    """Track queries executed against Metabase."""

    message = models.OneToOneField(
        Message,
        on_delete=models.CASCADE,
        related_name='query_history'
    )
    database_id = models.IntegerField()
    sql_query = models.TextField()
    natural_language = models.TextField()
    result_count = models.IntegerField(null=True, blank=True)
    execution_time_ms = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Query History'
        verbose_name_plural = 'Query Histories'

    def __str__(self):
        return f"Query on {self.created_at}: {self.natural_language[:50]}"


class SavedReport(models.Model):
    """Reports generated from queries."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_reports')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    card_id = models.IntegerField(null=True, blank=True)  # Metabase card ID
    query = models.TextField()
    visualization_settings = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Saved Report'
        verbose_name_plural = 'Saved Reports'

    def __str__(self):
        return self.name


class OpenAIConfig(models.Model):
    """OpenAI API configuration for NL-to-SQL conversion."""

    name = models.CharField(max_length=100, default='Default', help_text='Configuration name')
    api_key = models.CharField(max_length=255, help_text='OpenAI API Key')
    base_url = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text='Custom API base URL (e.g., https://api.openai.com/v1). Leave blank for default.'
    )
    model = models.CharField(
        max_length=50,
        default='gpt-4',
        help_text='Model name (e.g., gpt-4, gpt-3.5-turbo)'
    )
    temperature = models.FloatField(default=0.1, help_text='Temperature for generation (0.0-1.0)')
    max_tokens = models.IntegerField(default=1000, help_text='Maximum tokens to generate')
    enable_thinking = models.BooleanField(default=True, help_text='Enable thinking status messages to users during processing')
    is_active = models.BooleanField(default=True, help_text='Whether this configuration is active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'OpenAI Configuration'
        verbose_name_plural = 'OpenAI Configurations'
        ordering = ['-is_active', '-updated_at']

    def __str__(self):
        return f"{self.name} ({self.model})"
