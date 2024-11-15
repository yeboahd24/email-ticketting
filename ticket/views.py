from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from .models import Ticket, TicketMessage
from .services import EmailProcessor
import json
import logging
from django.utils.crypto import get_random_string
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.models import User

@csrf_exempt
@require_http_methods(["POST"])
def email_webhook(request):
    """Handle incoming emails from Postmark webhook."""
    logger = logging.getLogger(__name__)
    
    try:
        logger.info("Received webhook request")
        
        try:
            data = json.loads(request.body)
            logger.info(f"Webhook data: {data}")
            
            # Handle both Postmark format and test format
            email_data = {
                'from': data.get('From') or data.get('from'),
                'subject': data.get('Subject') or data.get('subject'),
                'body': (data.get('TextBody') or data.get('HtmlBody') or 
                        data.get('body') or "No content"),
                'cc': data.get('Cc') or data.get('cc', ''),
                'message_id': (data.get('MessageID') or data.get('message_id') or 
                             f"test-{get_random_string(12)}"),
                'in_reply_to': data.get('InReplyTo') or data.get('in_reply_to'),
                'attachments': data.get('Attachments', []),
                'to': data.get('To') or data.get('to', ''),
            }
            
            logger.info(f"Parsed email data: {email_data}")
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid JSON payload'
            }, status=400)
        
        processor = EmailProcessor()
        ticket = processor.process_incoming_email(email_data)
        
        logger.info(f"Successfully created/updated ticket: {ticket.ticket_id}")
        
        return JsonResponse({
            'status': 'success',
            'ticket_id': ticket.ticket_id
        })
        
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=400)

@login_required
def ticket_list(request):
    """Display list of tickets."""
    tickets = Ticket.objects.all().order_by('-created_at')
    return render(request, 'tickets/ticket_list.html', {'tickets': tickets})

@login_required
def ticket_detail(request, ticket_id):
    """Display ticket details."""
    logger = logging.getLogger(__name__)
    
    ticket = get_object_or_404(Ticket, ticket_id=ticket_id)
    staff_members = User.objects.filter(is_staff=True)
    
    # Debug logging
    logger.info(f"Found {staff_members.count()} staff members")
    for staff in staff_members:
        logger.info(f"Staff member: {staff.email} (ID: {staff.id})")
    
    context = {
        'ticket': ticket,
        'staff_members': staff_members,
    }
    
    logger.info(f"Rendering ticket detail with context: {context}")
    return render(request, 'tickets/ticket_detail.html', context)

@login_required
@require_http_methods(["POST"])
def update_ticket_status(request, ticket_id):
    """Update ticket status."""
    ticket = get_object_or_404(Ticket, ticket_id=ticket_id)
    data = json.loads(request.body)
    
    if 'status' in data and data['status'] in dict(Ticket.STATUS_CHOICES):
        ticket.status = data['status']
        ticket.save()
        return JsonResponse({'status': 'success'})
    
    return JsonResponse({
        'status': 'error',
        'message': 'Invalid status'
    }, status=400)

@login_required
@require_http_methods(["POST"])
def assign_ticket(request, ticket_id):
    """Assign a ticket to a staff member."""
    try:
        ticket = get_object_or_404(Ticket, ticket_id=ticket_id)
        staff_id = request.POST.get('staff_id')
        
        if not staff_id:
            return JsonResponse({
                'status': 'error',
                'message': 'No staff member selected'
            }, status=400)
            
        staff = get_object_or_404(User, id=staff_id)
        if not staff.is_staff:
            return JsonResponse({
                'status': 'error',
                'message': 'Selected user is not a staff member'
            }, status=400)
            
        ticket.assigned_to = staff
        ticket.status = 'open'
        ticket.save()
        
        # Send notification to assigned staff
        send_mail(
            subject=f'Ticket {ticket.ticket_id} assigned to you',
            message=f'You have been assigned ticket: {ticket.subject}',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[staff.email],
        )
        
        return JsonResponse({
            'status': 'success',
            'message': f'Ticket assigned to {staff.email}',
            'assigned_to': {
                'id': staff.id,
                'email': staff.email,
                'name': staff.get_full_name() or staff.email
            },
            'ticket': {
                'status': ticket.status,
                'ticket_id': ticket.ticket_id
            }
        })
            
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

@login_required
def get_staff_members(request):
    """Get list of staff members for assignment."""
    staff_members = User.objects.filter(is_staff=True).values('id', 'email', 'first_name', 'last_name')
    return JsonResponse({
        'status': 'success',
        'staff_members': list(staff_members)
    })
