import email
import re
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from .models import Ticket, TicketMessage, Attachment
from django.utils.crypto import get_random_string
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
import logging
import base64
import os
from django.core.files.base import ContentFile
from django.db import models
import mimetypes

logger = logging.getLogger(__name__)


class EmailProcessor:
    def __init__(self):
        self.support_email = "dyeboah@mesika.org"  # Replace with your actual support email
        self.domain = "mesika.org"  # Replace with your actual domain

    def generate_ticket_id(self):
        """Generate a unique ticket ID."""
        return f"TIC-{get_random_string(8).upper()}"

    def generate_reply_to_address(self, ticket_id):
        """Generate the reply-to address for a ticket."""
        return f"support+id{ticket_id}@{self.domain}"

    def extract_ticket_id_from_email(self, email_address):
        """Extract ticket ID from a reply-to email address."""
        match = re.search(r'support\+id([\w-]+)@', email_address)
        return match.group(1) if match else None

    def process_incoming_email(self, email_data):
        """Process an incoming email and create or update a ticket."""
        logger = logging.getLogger(__name__)
        
        try:
            # Handle both dictionary and raw email data
            if isinstance(email_data, dict):
                from_email = email_data['from']
                subject = email_data['subject']
                body = email_data['body']
                message_id = email_data.get('message_id')
                in_reply_to = email_data.get('in_reply_to')
                cc_list = [addr.strip() for addr in email_data.get('cc', '').split(',') if addr.strip()]
            else:
                # Parse raw email data
                msg = email.message_from_bytes(email_data)
                from_email = msg['from']
                subject = msg['subject']
                message_id = msg['message-id']
                in_reply_to = msg['in-reply-to']
                cc_list = [addr.strip() for addr in (msg['cc'] or '').split(',') if addr.strip()]
                body = self._get_email_body(msg)

            logger.info(f"Processing email from: {from_email}, subject: {subject}")
            
            if in_reply_to:
                # This is a reply to an existing ticket
                ticket_id = self.extract_ticket_id_from_email(msg['to'] if not isinstance(email_data, dict) else None)
                if ticket_id:
                    logger.info(f"Found existing ticket: {ticket_id}")
                    return self._process_reply(
                        ticket_id, from_email, body, message_id, 
                        in_reply_to, cc_list, msg if not isinstance(email_data, dict) else None
                    )
            
            # This is a new ticket
            logger.info("Creating new ticket")
            return self._create_new_ticket(
                from_email, subject, body, message_id, cc_list, 
                msg if not isinstance(email_data, dict) else None
            )
            
        except Exception as e:
            logger.error(f"Error processing email: {str(e)}", exc_info=True)
            raise

    def _get_email_body(self, msg):
        """Extract the email body from the email message."""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    return part.get_payload(decode=True).decode()
        return msg.get_payload(decode=True).decode()

    def _create_new_ticket(self, from_email, subject, body, message_id, cc_list=None, msg=None):
        """Create a new ticket from an email."""
        logger = logging.getLogger(__name__)
        
        try:
            # Generate unique ticket ID
            ticket_id = f"TIC-{get_random_string(8).upper()}"
            reply_to_email = f"support+id{ticket_id}@{self.domain}"
            
            # Create the ticket
            ticket = Ticket.objects.create(
                ticket_id=ticket_id,
                subject=subject or "No Subject",  # Ensure subject is never null
                body=body or "",  # Ensure body is never null
                from_email=from_email,
                reply_to_email=reply_to_email,
                status='new'
            )
            
            # Create the initial message
            ticket_message = TicketMessage.objects.create(
                ticket=ticket,
                sender=from_email,
                message_id=message_id or f"generated-{get_random_string(12)}",  # Ensure message_id is never null
                content=body or ""
            )
            
            # Process attachments if any
            if msg:
                self._process_attachments(msg, ticket_message)
            
            # Process CC recipients
            if cc_list:
                self._process_cc_recipients(ticket, cc_list)
            
            # Try to auto-assign the ticket
            self._auto_assign_ticket(ticket)
            
            logger.info(f"Created new ticket: {ticket_id}")
            return ticket
            
        except Exception as e:
            logger.error(f"Error creating ticket: {str(e)}", exc_info=True)
            raise

    def _process_reply(self, ticket_id, from_email, body, message_id, in_reply_to, cc_list, msg):
        """Process a reply to an existing ticket."""
        try:
            ticket = Ticket.objects.get(ticket_id=ticket_id)
            
            # Create new message
            ticket_message = TicketMessage.objects.create(
                ticket=ticket,
                sender=from_email,
                message_id=message_id,
                in_reply_to=in_reply_to,
                content=body
            )

            # Process attachments
            self._process_attachments(msg, ticket_message)

            # Process CC recipients
            self._process_cc_recipients(ticket, cc_list)

            # Update ticket status if it was closed
            if ticket.status == 'closed':
                ticket.status = 'open'
                ticket.save()

            return ticket

        except Ticket.DoesNotExist:
            # Handle case where ticket doesn't exist
            return self._create_new_ticket(from_email, f"Re: {msg['subject']}", body, 
                                         message_id, cc_list, msg)

    def _process_attachments(self, email_data, ticket_message):
        """Process and save email attachments."""
        logger = logging.getLogger(__name__)
        
        if isinstance(email_data, dict) and email_data.get('attachments'):
            for attachment in email_data['attachments']:
                try:
                    # Decode base64 content
                    content = base64.b64decode(attachment['Content'])
                    
                    # Create a unique filename
                    filename = attachment['Name']
                    file_obj = ContentFile(content, name=filename)
                    
                    # Save the attachment
                    ticket_attachment = Attachment.objects.create(
                        ticket_message=ticket_message,
                        file=file_obj,
                        filename=filename,
                        content_type=attachment['ContentType']
                    )
                    logger.info(f"Saved attachment: {filename}")
                    
                except Exception as e:
                    logger.error(f"Error saving attachment {filename}: {str(e)}")
                    continue
        
        elif email_data is not None and email_data.is_multipart():
            for part in email_data.walk():
                if part.get_content_maintype() == 'multipart':
                    continue
                if part.get('Content-Disposition') is None:
                    continue
                
                try:
                    filename = part.get_filename()
                    if filename:
                        content = part.get_payload(decode=True)
                        file_obj = ContentFile(content, name=filename)
                        
                        ticket_attachment = Attachment.objects.create(
                            ticket_message=ticket_message,
                            file=file_obj,
                            filename=filename,
                            content_type=part.get_content_type()
                        )
                        logger.info(f"Saved attachment: {filename}")
                        
                except Exception as e:
                    logger.error(f"Error saving attachment {filename}: {str(e)}")
                    continue

    def _process_cc_recipients(self, ticket, cc_list):
        """Process CC recipients and add them to the ticket."""
        for cc_email in cc_list:
            # Try to find existing user
            user = User.objects.filter(email=cc_email).first()
            
            if user:
                # If user exists, add them to the ticket's CC list
                ticket.cc_users.add(user)
            else:
                # Create a new user account with a random password
                username = cc_email.split('@')[0]
                base_username = username
                counter = 1
                
                # Ensure unique username
                while User.objects.filter(username=username).exists():
                    username = f"{base_username}{counter}"
                    counter += 1
                
                # Create user with temporary password
                temp_password = User.objects.make_random_password()
                user = User.objects.create_user(
                    username=username,
                    email=cc_email,
                    password=temp_password,
                    is_active=False  # User needs to activate account
                )
                
                # Add user to ticket's CC list
                ticket.cc_users.add(user)
                
                # Generate activation token
                token = default_token_generator.make_token(user)
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                
                # Prepare activation email
                context = {
                    'user': user,
                    'ticket': ticket,
                    'activation_link': f"{settings.SITE_URL}/activate/{uid}/{token}/",
                    'temp_password': temp_password,
                }
                
                message = render_to_string('ticket/email/cc_invitation.html', context)
                
                # Send invitation email
                send_mail(
                    subject=f"You've been CC'd on Ticket #{ticket.ticket_id}",
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[cc_email],
                    fail_silently=False,
                )
                
            # Send notification about the ticket
            context = {
                'ticket': ticket,
                'user': user,
                'support_email': self.support_email,
            }
            
            notification = render_to_string('ticket/email/cc_notification.html', context)
            
            send_mail(
                subject=f"[CC] Ticket #{ticket.ticket_id}: {ticket.subject}",
                message=notification,
                from_email=self.support_email,
                recipient_list=[cc_email],
                fail_silently=False,
            )

    def _auto_assign_ticket(self, ticket):
        """Automatically assign ticket based on rules."""
        try:
            # Get all staff members
            staff_members = User.objects.filter(is_staff=True)
            
            if not staff_members.exists():
                return
            
            # Simple round-robin assignment
            # Get the staff member with the least number of open tickets
            staff_assignment = staff_members.annotate(
                open_tickets=models.Count(
                    'assigned_tickets',
                    filter=models.Q(assigned_tickets__status__in=['new', 'open'])
                )
            ).order_by('open_tickets').first()
            
            if staff_assignment:
                ticket.assigned_to = staff_assignment
                ticket.status = 'open'
                ticket.save()
                
                # Send notification to assigned staff
                send_mail(
                    subject=f'New Ticket {ticket.ticket_id} automatically assigned to you',
                    message=f'You have been assigned a new ticket:\n\nSubject: {ticket.subject}\n\nBody: {ticket.body}',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[staff_assignment.email],
                )
                
                logger.info(f"Automatically assigned ticket {ticket.ticket_id} to {staff_assignment.email}")
        
        except Exception as e:
            logger.error(f"Error in auto-assignment: {str(e)}", exc_info=True)

    def _send_acknowledgment_email(self, ticket, recipient_email):
        """Send an acknowledgment email for a new ticket."""
        subject = f"[{ticket.ticket_id}] Ticket Received: {ticket.subject}"
        context = {
            'ticket': ticket,
            'support_email': self.support_email
        }
        
        message = render_to_string('tickets/email/acknowledgment.html', context)
        
        send_mail(
            subject=subject,
            message=message,
            from_email=self.support_email,
            recipient_list=[recipient_email],
            reply_to=[ticket.reply_to_email]
        )
