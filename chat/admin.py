from django.contrib import admin

from .models import ChatMessage, ChatSession


class MessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    readonly_fields = ("role", "content", "context", "provider", "model", "created_at")
    can_delete = False


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "updated_at")
    inlines = [MessageInline]
