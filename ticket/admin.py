from django.contrib import admin
from .models import Ticket, TicketMessage, Attachment

class TicketMessageInline(admin.StackedInline):
    model = TicketMessage
    extra = 0
    readonly_fields = ('message_id', 'in_reply_to', 'created_at')

class AttachmentInline(admin.TabularInline):
    model = Attachment
    extra = 0
    readonly_fields = ('size', 'created_at')

@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('ticket_id', 'subject', 'status', 'from_email', 'created_at', 'assigned_to')
    list_filter = ('status', 'created_at', 'assigned_to')
    search_fields = ('ticket_id', 'subject', 'from_email')
    readonly_fields = ('ticket_id', 'created_at', 'updated_at')
    inlines = [TicketMessageInline]
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('assigned_to')

@admin.register(TicketMessage)
class TicketMessageAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'sender', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('ticket__ticket_id', 'sender', 'content')
    readonly_fields = ('message_id', 'in_reply_to', 'created_at')
    inlines = [AttachmentInline]
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('ticket')
