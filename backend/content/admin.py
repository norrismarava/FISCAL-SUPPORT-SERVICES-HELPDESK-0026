from django.contrib import admin
from .models import Announcement, BlogCategory, BlogPost, FAQ, FAQCategory, Service, ServiceResource

admin.site.register(BlogCategory)
admin.site.register(BlogPost)
admin.site.register(FAQCategory)
admin.site.register(FAQ)
admin.site.register(Service)
admin.site.register(ServiceResource)


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ('title', 'type', 'priority', 'is_published', 'published_at', 'updated_at')
    list_filter = ('type', 'priority', 'is_published')
    search_fields = ('title', 'message')
