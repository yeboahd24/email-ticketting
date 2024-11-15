from django.urls import path
from . import views

app_name = 'tickets'

urlpatterns = [
    path('webhook/email/', views.email_webhook, name='email_webhook'),
    path('tickets/', views.ticket_list, name='ticket_list'),
    path('tickets/<str:ticket_id>/', views.ticket_detail, name='ticket_detail'),
    path('tickets/<str:ticket_id>/status/', views.update_ticket_status, name='update_ticket_status'),
    path('tickets/<str:ticket_id>/assign/', views.assign_ticket, name='assign_ticket'),
    path('staff/members/', views.get_staff_members, name='get_staff_members'),
]
