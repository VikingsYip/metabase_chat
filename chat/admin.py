"""
Admin configuration for chat models.
"""
from django.contrib import admin
from .models import Conversation, Message, QueryHistory, SavedReport, OpenAIConfig


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'created_at', 'updated_at']
    list_filter = ['created_at', 'updated_at']
    search_fields = ['title', 'user__username']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['conversation', 'role', 'content_preview', 'created_at']
    list_filter = ['role', 'created_at']
    search_fields = ['content', 'conversation__title']
    readonly_fields = ['created_at']

    def content_preview(self, obj):
        return obj.content[:100] + '...' if len(obj.content) > 100 else obj.content
    content_preview.short_description = 'Content'


@admin.register(QueryHistory)
class QueryHistoryAdmin(admin.ModelAdmin):
    list_display = ['id', 'message', 'database_id', 'result_count', 'execution_time_ms', 'created_at']
    list_filter = ['database_id', 'created_at']
    search_fields = ['natural_language', 'sql_query']
    readonly_fields = ['created_at']


@admin.register(SavedReport)
class SavedReportAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'card_id', 'created_at', 'updated_at']
    list_filter = ['created_at', 'updated_at']
    search_fields = ['name', 'description', 'query']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(OpenAIConfig)
class OpenAIConfigAdmin(admin.ModelAdmin):
    list_display = ['name', 'model', 'is_active', 'base_url', 'created_at', 'updated_at']
    list_filter = ['is_active', 'created_at', 'model']
    search_fields = ['name', 'api_key', 'base_url']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'is_active')
        }),
        ('API Configuration', {
            'fields': ('api_key', 'base_url', 'model')
        }),
        ('Generation Parameters', {
            'fields': ('temperature', 'max_tokens', 'enable_thinking')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def save_model(self, request, obj, form, change):
        # If this is being marked as active, deactivate all other configs
        if obj.is_active:
            OpenAIConfig.objects.filter(is_active=True).exclude(pk=obj.pk).update(is_active=False)
        super().save_model(request, obj, form, change)
