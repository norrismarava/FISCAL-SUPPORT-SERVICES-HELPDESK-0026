from rest_framework import serializers

from .models import ReportSchedule


class ReportScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportSchedule
        fields = [
            'id',
            'name',
            'interval',
            'recipients',
            'include_fields',
            'filters',
            'is_active',
            'last_sent_at',
            'created_by',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['last_sent_at', 'created_by', 'created_at', 'updated_at']
