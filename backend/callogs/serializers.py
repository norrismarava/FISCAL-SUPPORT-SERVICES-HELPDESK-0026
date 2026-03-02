from rest_framework import serializers
from django.utils import timezone
from .models import CallLog, EngineerComment, CallLogActivity
from users.serializers import UserSerializer


class EngineerCommentSerializer(serializers.ModelSerializer):
    engineer_name = serializers.CharField(source='engineer.get_full_name', read_only=True)
    
    class Meta:
        model = EngineerComment
        fields = ['id', 'call_log', 'engineer', 'engineer_name', 'comment', 'created_at']
        read_only_fields = ['engineer', 'created_at']


class CallLogActivitySerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    
    class Meta:
        model = CallLogActivity
        fields = [
            'id', 'user', 'user_name', 'activity_type',
            'description', 'metadata', 'created_at'
        ]
        read_only_fields = ['created_at']


class CallLogListSerializer(serializers.ModelSerializer):
    """Serializer for call log list view"""
    assigned_technician_name = serializers.CharField(
        source='assigned_technician.get_full_name', 
        read_only=True
    )
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    fault_type_display = serializers.CharField(source='get_fault_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    balance_due = serializers.SerializerMethodField()
    
    class Meta:
        model = CallLog
        fields = [
            'id', 'job_id', 'job_number', 'customer_name', 'customer_email',
            'job_type', 'fault_type', 'fault_type_display',
            'status', 'status_display', 'full_amount', 'amount_deposited', 'balance_due',
            'amount_charged', 'currency',
            'payment_terms_type', 'discount_amount',
            'time_start', 'time_finish', 'billed_hours', 'resolution_date', 'resolution_time',
            'assigned_technician', 'assigned_technician_name',
            'created_by', 'created_by_name',
            'booking_date', 'created_at', 'updated_at'
        ]
        read_only_fields = ['job_id', 'job_number', 'created_at', 'updated_at']

    def get_balance_due(self, obj):
        return float(obj.balance_due or 0)


class CallLogDetailSerializer(serializers.ModelSerializer):
    """Serializer for detailed call log view"""
    assigned_technician_details = UserSerializer(source='assigned_technician', read_only=True)
    created_by_details = UserSerializer(source='created_by', read_only=True)
    engineer_comments = EngineerCommentSerializer(many=True, read_only=True)
    activities = CallLogActivitySerializer(many=True, read_only=True)
    related_ticket_id = serializers.UUIDField(source='related_ticket.ticket_id', read_only=True)
    balance_due = serializers.SerializerMethodField()
    
    class Meta:
        model = CallLog
        fields = [
            'id', 'job_id', 'job_number',
            'customer_name', 'customer_email', 'customer_phone', 'customer_address',
            'related_ticket', 'related_ticket_id',
            'job_type', 'fault_type', 'fault_description', 'resolution_notes',
            'full_amount', 'amount_deposited', 'balance_due',
            'amount_charged', 'currency', 'zimra_reference', 'invoice_number',
            'payment_terms_type', 'discount_amount', 'special_terms_notes',
            'assigned_technician', 'assigned_technician_details',
            'status', 'booking_date', 'booking_time',
            'resolution_date', 'resolution_time', 'time_start', 'time_finish', 'billed_hours',
            'created_by', 'created_by_details',
            'engineer_comments', 'activities',
            'created_at', 'updated_at', 'completed_at'
        ]
        read_only_fields = [
            'job_id', 'job_number', 'created_by', 
            'created_at', 'updated_at', 'completed_at'
        ]

    def get_balance_due(self, obj):
        return float(obj.balance_due or 0)


class CallLogCreateSerializer(serializers.ModelSerializer):
    """Create new call log/job card"""
    assigned_technician_name = serializers.SerializerMethodField()
    
    class Meta:
        model = CallLog
        fields = [
            'id', 'job_number', 'status',
            'customer_name', 'customer_email', 'customer_phone', 'customer_address',
            'related_ticket', 'job_type', 'fault_type', 'fault_description',
            'full_amount', 'amount_deposited',
            'amount_charged', 'currency', 'zimra_reference', 'invoice_number',
            'payment_terms_type', 'discount_amount', 'special_terms_notes',
            'assigned_technician', 'assigned_technician_name', 'booking_date', 'booking_time',
            'resolution_date', 'resolution_time', 'time_start', 'time_finish', 'billed_hours'
        ]
        read_only_fields = ['id', 'job_number', 'status', 'assigned_technician_name']

    def get_assigned_technician_name(self, obj):
        tech = getattr(obj, 'assigned_technician', None)
        if not tech:
            return None
        return tech.get_full_name() or tech.username

    def validate(self, attrs):
        customer_address = (attrs.get('customer_address') or '').strip()
        if not customer_address:
            raise serializers.ValidationError({
                'customer_address': 'Customer address is required.'
            })
        attrs['customer_address'] = customer_address

        if not attrs.get('booking_date'):
            raise serializers.ValidationError({
                'booking_date': 'Date booked is required.'
            })

        amount_charged = attrs.get('amount_charged') or 0
        full_amount = attrs.get('full_amount')
        amount_deposited = attrs.get('amount_deposited') or 0

        # If full amount is omitted/zero, infer from charged or deposit to avoid avoidable 400s.
        if not full_amount or full_amount == 0:
            full_amount = max(amount_charged, amount_deposited)
            attrs['full_amount'] = full_amount

        if amount_deposited > full_amount:
            raise serializers.ValidationError({
                'amount_deposited': 'Amount deposited cannot be greater than full amount.'
            })

        payment_terms_type = attrs.get('payment_terms_type', 'none')
        discount_amount = attrs.get('discount_amount') or 0
        special_terms_notes = (attrs.get('special_terms_notes') or '').strip()

        if payment_terms_type != 'none' or discount_amount > 0:
            if not special_terms_notes:
                raise serializers.ValidationError({
                    'special_terms_notes': 'Special terms notes are required for discounts/partial/periodic/lay-by arrangements.'
                })
        return attrs
    
    def create(self, validated_data):
        user = self.context['request'].user
        validated_data['created_by'] = user
        validated_data['status'] = 'pending'
        
        call_log = CallLog.objects.create(**validated_data)
        
        # Create activity log
        CallLogActivity.objects.create(
            call_log=call_log,
            user=user,
            activity_type='created',
            description=f'Job card created by {user.get_full_name()}'
        )

        if call_log.payment_terms_type != 'none' or (call_log.discount_amount and call_log.discount_amount > 0):
            CallLogActivity.objects.create(
                call_log=call_log,
                user=user,
                activity_type='updated',
                description=(
                    f'Special payment terms captured: {call_log.get_payment_terms_type_display()} '
                    f'| Discount: {call_log.currency} {call_log.discount_amount}'
                ),
                metadata={'special_terms_notes': call_log.special_terms_notes}
            )
        
        return call_log


class CallLogUpdateSerializer(serializers.ModelSerializer):
    """Update existing call log"""
    
    class Meta:
        model = CallLog
        fields = [
            'customer_name', 'customer_email', 'customer_phone', 'customer_address',
            'job_type', 'fault_type', 'fault_description', 'resolution_notes',
            'full_amount', 'amount_deposited',
            'amount_charged', 'currency', 'zimra_reference', 'invoice_number',
            'payment_terms_type', 'discount_amount', 'special_terms_notes',
            'assigned_technician', 'status',
            'booking_date', 'booking_time', 'resolution_date', 'resolution_time', 'time_start', 'time_finish', 'billed_hours'
        ]

    def validate(self, attrs):
        current_address = (getattr(self.instance, 'customer_address', '') or '').strip()
        customer_address = (attrs.get('customer_address', current_address) or '').strip()
        if not customer_address:
            raise serializers.ValidationError({
                'customer_address': 'Customer address is required.'
            })
        attrs['customer_address'] = customer_address

        current_full = getattr(self.instance, 'full_amount', 0) or 0
        current_charged = getattr(self.instance, 'amount_charged', 0) or 0
        current_deposited = getattr(self.instance, 'amount_deposited', 0) or 0
        full_amount = attrs.get('full_amount', current_full)
        amount_charged = attrs.get('amount_charged', current_charged) or 0
        amount_deposited = attrs.get('amount_deposited', getattr(self.instance, 'amount_deposited', 0)) or 0

        if not full_amount or full_amount == 0:
            full_amount = max(amount_charged, amount_deposited, current_deposited)
            attrs['full_amount'] = full_amount

        if amount_deposited > full_amount:
            raise serializers.ValidationError({
                'amount_deposited': 'Amount deposited cannot be greater than full amount.'
            })

        payment_terms_type = attrs.get('payment_terms_type', getattr(self.instance, 'payment_terms_type', 'none'))
        discount_amount = attrs.get('discount_amount', getattr(self.instance, 'discount_amount', 0)) or 0
        special_terms_notes = attrs.get('special_terms_notes', getattr(self.instance, 'special_terms_notes', '')) or ''

        if payment_terms_type != 'none' or discount_amount > 0:
            if not special_terms_notes.strip():
                raise serializers.ValidationError({
                    'special_terms_notes': 'Special terms notes are required for discounts/partial/periodic/lay-by arrangements.'
                })
        return attrs
    
    def update(self, instance, validated_data):
        user = self.context['request'].user
        changes = []
        
        # Track status changes
        if 'status' in validated_data and instance.status != validated_data['status']:
            old_status = instance.get_status_display()
            new_status = dict(CallLog.STATUS_CHOICES)[validated_data['status']]
            changes.append(f'Status changed from {old_status} to {new_status}')
            
            # Set completion timestamp
            if validated_data['status'] == 'complete':
                validated_data['completed_at'] = timezone.now()
        
        # Track assignment changes
        if 'assigned_technician' in validated_data:
            if instance.assigned_technician != validated_data['assigned_technician']:
                if validated_data['assigned_technician']:
                    changes.append(
                        f'Assigned to {validated_data["assigned_technician"].get_full_name()}'
                    )
                else:
                    changes.append('Unassigned')

        new_terms_type = validated_data.get('payment_terms_type', instance.payment_terms_type)
        new_discount = validated_data.get('discount_amount', instance.discount_amount)
        if (
            new_terms_type != instance.payment_terms_type
            or new_discount != instance.discount_amount
            or validated_data.get('special_terms_notes', instance.special_terms_notes) != instance.special_terms_notes
        ):
            changes.append(
                f'Special terms updated: {dict(CallLog.PAYMENT_TERMS_CHOICES).get(new_terms_type, new_terms_type)} | '
                f'Discount: {instance.currency} {new_discount}'
            )
        
        # Update the call log
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Log activities
        for change in changes:
            CallLogActivity.objects.create(
                call_log=instance,
                user=user,
                activity_type='updated',
                description=change
            )
        
        return instance
