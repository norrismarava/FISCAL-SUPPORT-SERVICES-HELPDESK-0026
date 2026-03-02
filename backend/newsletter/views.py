from rest_framework import viewsets, generics, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone

from .models import NewsletterSubscriber, NewsletterCampaign
from .serializers import (
    NewsletterSubscriberSerializer, NewsletterSubscribeSerializer,
    NewsletterCampaignSerializer
)
from .permissions import IsAdminUser


@api_view(['POST'])
@permission_classes([AllowAny])
def subscribe_newsletter(request):
    """
    Public endpoint for newsletter subscription
    """
    serializer = NewsletterSubscribeSerializer(data=request.data)
    
    if serializer.is_valid():
        subscriber = serializer.save()
        
        # Send confirmation email
        send_mail(
            subject='Newsletter Subscription Confirmed',
            message=f'Hello {subscriber.name or "there"},\n\n'
                    f'Thank you for subscribing to the FSSHELPDESK newsletter!\n\n'
                    f'You will receive updates about our services, tips, and news.\n\n'
                    f'If you wish to unsubscribe, please contact us.\n\n'
                    f'Best regards,\nFSSHELPDESK Team',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[subscriber.email],
            fail_silently=True,
        )
        
        return Response({
            'message': 'Successfully subscribed to newsletter!'
        }, status=status.HTTP_201_CREATED)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def unsubscribe_newsletter(request):
    """
    Public endpoint for newsletter unsubscription
    """
    email = request.data.get('email')
    
    if not email:
        return Response(
            {'error': 'Email is required.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        subscriber = NewsletterSubscriber.objects.get(email=email, is_active=True)
        subscriber.is_active = False
        subscriber.unsubscribed_at = timezone.now()
        subscriber.save()
        
        return Response({
            'message': 'Successfully unsubscribed from newsletter.'
        })
    except NewsletterSubscriber.DoesNotExist:
        return Response(
            {'error': 'Email not found in subscription list.'},
            status=status.HTTP_404_NOT_FOUND
        )


class NewsletterSubscriberViewSet(viewsets.ModelViewSet):
    """
    Manage newsletter subscribers (Admin only)
    """
    queryset = NewsletterSubscriber.objects.all()
    serializer_class = NewsletterSubscriberSerializer
    permission_classes = (IsAuthenticated, IsAdminUser)
    filterset_fields = ['is_active']
    search_fields = ['email', 'name']
    ordering = ['-subscribed_at']
    
    @action(detail=False, methods=['get'])
    def active(self, request):
        """Get active subscribers"""
        subscribers = NewsletterSubscriber.objects.filter(is_active=True)
        serializer = self.get_serializer(subscribers, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def count(self, request):
        """Get subscriber counts"""
        total = NewsletterSubscriber.objects.count()
        active = NewsletterSubscriber.objects.filter(is_active=True).count()
        inactive = total - active
        
        return Response({
            'total': total,
            'active': active,
            'inactive': inactive
        })


class NewsletterCampaignViewSet(viewsets.ModelViewSet):
    """
    Manage newsletter campaigns (Admin only)
    """
    queryset = NewsletterCampaign.objects.all()
    serializer_class = NewsletterCampaignSerializer
    permission_classes = (IsAuthenticated, IsAdminUser)
    filterset_fields = ['status']
    search_fields = ['title', 'subject']
    ordering = ['-created_at']
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def send_campaign(self, request, pk=None):
        """
        Send newsletter campaign to all active subscribers
        """
        campaign = self.get_object()
        
        if campaign.status == 'sent':
            return Response(
                {'error': 'Campaign has already been sent.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get active subscribers
        subscribers = NewsletterSubscriber.objects.filter(is_active=True)
        recipient_emails = [sub.email for sub in subscribers]
        
        if not recipient_emails:
            return Response(
                {'error': 'No active subscribers found.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update campaign status
        campaign.status = 'sending'
        campaign.save()
        
        # Send emails (in production, use Celery for async processing)
        try:
            send_mail(
                subject=campaign.subject,
                message=campaign.content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=recipient_emails,
                fail_silently=False,
            )
            
            # Update campaign
            campaign.status = 'sent'
            campaign.sent_at = timezone.now()
            campaign.recipients_count = len(recipient_emails)
            campaign.save()
            
            return Response({
                'message': f'Campaign sent successfully to {len(recipient_emails)} subscribers.'
            })
        
        except Exception as e:
            campaign.status = 'draft'
            campaign.save()
            
            return Response(
                {'error': f'Failed to send campaign: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def schedule(self, request, pk=None):
        """Schedule campaign for future sending"""
        campaign = self.get_object()
        scheduled_for = request.data.get('scheduled_for')
        
        if not scheduled_for:
            return Response(
                {'error': 'scheduled_for datetime is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        campaign.scheduled_for = scheduled_for
        campaign.status = 'scheduled'
        campaign.save()
        
        serializer = self.get_serializer(campaign)
        return Response(serializer.data)