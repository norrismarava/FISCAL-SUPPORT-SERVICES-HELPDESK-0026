from rest_framework import serializers
from .models import (
    BlogCategory, BlogPost, FAQCategory, FAQ, 
    Service, ServiceResource
)


class BlogCategorySerializer(serializers.ModelSerializer):
    posts_count = serializers.IntegerField(source='blogpost_set.count', read_only=True)
    
    class Meta:
        model = BlogCategory
        fields = ['id', 'name', 'slug', 'description', 'posts_count', 'created_at']
        read_only_fields = ['slug', 'created_at']


class BlogPostListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    author_name = serializers.CharField(source='author.get_full_name', read_only=True)
    
    class Meta:
        model = BlogPost
        fields = [
            'id', 'title', 'slug', 'excerpt', 'category', 'category_name',
            'author', 'author_name', 'featured_image', 'is_featured',
            'is_published', 'published_at', 'created_at'
        ]
        read_only_fields = ['slug', 'author', 'created_at']


class BlogPostDetailSerializer(serializers.ModelSerializer):
    category_details = BlogCategorySerializer(source='category', read_only=True)
    author_details = serializers.SerializerMethodField()
    
    class Meta:
        model = BlogPost
        fields = [
            'id', 'title', 'slug', 'content', 'excerpt',
            'category', 'category_details', 'author', 'author_details',
            'featured_image', 'is_featured', 'is_published',
            'published_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['slug', 'author', 'created_at', 'updated_at']
    
    def get_author_details(self, obj):
        return {
            'id': obj.author.id,
            'name': obj.author.get_full_name(),
            'email': obj.author.email
        }


class FAQCategorySerializer(serializers.ModelSerializer):
    faqs_count = serializers.IntegerField(source='faqs.count', read_only=True)
    
    class Meta:
        model = FAQCategory
        fields = ['id', 'name', 'order', 'faqs_count', 'created_at']
        read_only_fields = ['created_at']


class FAQSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    
    class Meta:
        model = FAQ
        fields = [
            'id', 'category', 'category_name', 'question', 'answer',
            'order', 'is_published', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class ServiceResourceSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
    
    class Meta:
        model = ServiceResource
        fields = [
            'id', 'title', 'description', 'file', 'file_url',
            'file_size', 'file_type', 'created_at'
        ]
        read_only_fields = ['file_size', 'file_type', 'created_at']
    
    def get_file_url(self, obj):
        request = self.context.get('request')
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        return None


class ServiceSerializer(serializers.ModelSerializer):
    resources = ServiceResourceSerializer(many=True, read_only=True)
    
    class Meta:
        model = Service
        fields = [
            'id', 'name', 'slug', 'description', 'short_description',
            'icon', 'image', 'is_active', 'order', 'resources',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['slug', 'created_at', 'updated_at']