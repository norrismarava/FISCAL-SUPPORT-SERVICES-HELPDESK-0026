from rest_framework import serializers
from .models import NewsletterSubscriber, NewsletterCampaign


class NewsletterSubscriberSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsletterSubscriber
        fields = ['id', 'email', 'name', 'is_active', 'subscribed_at', 'unsubscribed_at']
        read_only_fields = ['subscribed_at', 'unsubscribed_at']


class NewsletterSubscribeSerializer(serializers.Serializer):
    """Public newsletter subscription"""
    email = serializers.EmailField(required=True)
    name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    
    def validate_email(self, value):
        if NewsletterSubscriber.objects.filter(email=value, is_active=True).exists():
            raise serializers.ValidationError("This email is already subscribed.")
        return value
    
    def create(self, validated_data):
        subscriber, created = NewsletterSubscriber.objects.get_or_create(
            email=validated_data['email'],
            defaults={'name': validated_data.get('name', '')}
        )
        
        if not created:
            # Reactivate if previously unsubscribed
            subscriber.is_active = True
            subscriber.name = validated_data.get('name', subscriber.name)
            subscriber.save()
        
        return subscriber


class NewsletterCampaignSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    
    class Meta:
        model = NewsletterCampaign
        fields = [
            'id', 'title', 'subject', 'content', 'status',
            'created_by', 'created_by_name', 'scheduled_for', 'sent_at',
            'recipients_count', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'created_by', 'sent_at', 'recipients_count', 
            'created_at', 'updated_at'
        ]