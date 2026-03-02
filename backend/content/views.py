from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from .models import (
    BlogCategory, BlogPost, FAQCategory, FAQ,
    Service, ServiceResource
)
from .serializers import (
    BlogCategorySerializer, BlogPostListSerializer, BlogPostDetailSerializer,
    FAQCategorySerializer, FAQSerializer,
    ServiceSerializer, ServiceResourceSerializer
)
from .permissions import IsAdminUser


class BlogCategoryViewSet(viewsets.ModelViewSet):
    """Blog categories management"""
    queryset = BlogCategory.objects.all()
    serializer_class = BlogCategorySerializer
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsAuthenticated(), IsAdminUser()]


class BlogPostViewSet(viewsets.ModelViewSet):
    """Blog posts management"""
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['category', 'is_published', 'is_featured', 'author']
    search_fields = ['title', 'content', 'excerpt']
    ordering_fields = ['created_at', 'published_at']
    ordering = ['-created_at']
    
    def get_queryset(self):
        # Public users see only published posts
        if self.request.user.is_authenticated and self.request.user.role in ['admin', 'manager', 'accounts']:
            return BlogPost.objects.all()
        return BlogPost.objects.filter(is_published=True)
    
    def get_serializer_class(self):
        if self.action == 'list':
            return BlogPostListSerializer
        return BlogPostDetailSerializer
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsAuthenticated(), IsAdminUser()]
    
    def perform_create(self, serializer):
        serializer.save(author=self.request.user)
    
    @action(detail=False, methods=['get'])
    def featured(self, request):
        """Get featured blog posts"""
        posts = BlogPost.objects.filter(is_published=True, is_featured=True)[:5]
        serializer = BlogPostListSerializer(posts, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        """Publish a blog post"""
        post = self.get_object()
        
        if post.is_published:
            return Response(
                {'error': 'Post is already published.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        from django.utils import timezone
        post.is_published = True
        post.published_at = timezone.now()
        post.save()
        
        serializer = self.get_serializer(post)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def unpublish(self, request, pk=None):
        """Unpublish a blog post"""
        post = self.get_object()
        post.is_published = False
        post.save()
        
        serializer = self.get_serializer(post)
        return Response(serializer.data)


class FAQCategoryViewSet(viewsets.ModelViewSet):
    """FAQ categories management"""
    queryset = FAQCategory.objects.all()
    serializer_class = FAQCategorySerializer
    ordering = ['order', 'name']
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsAuthenticated(), IsAdminUser()]


class FAQViewSet(viewsets.ModelViewSet):
    """FAQs management"""
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['category', 'is_published']
    search_fields = ['question', 'answer']
    ordering = ['category', 'order']
    
    def get_queryset(self):
        # Public users see only published FAQs
        if self.request.user.is_authenticated and self.request.user.role in ['admin', 'manager', 'accounts']:
            return FAQ.objects.all()
        return FAQ.objects.filter(is_published=True)
    
    serializer_class = FAQSerializer
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsAuthenticated(), IsAdminUser()]
    
    @action(detail=False, methods=['get'])
    def by_category(self, request):
        """Get FAQs grouped by category"""
        categories = FAQCategory.objects.all()
        result = []
        
        for category in categories:
            faqs = FAQ.objects.filter(
                category=category,
                is_published=True
            )
            
            if faqs.exists():
                result.append({
                    'category': FAQCategorySerializer(category).data,
                    'faqs': FAQSerializer(faqs, many=True).data
                })
        
        return Response(result)


class ServiceViewSet(viewsets.ModelViewSet):
    """Services management"""
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['is_active']
    ordering = ['order', 'name']
    serializer_class = ServiceSerializer
    
    def get_queryset(self):
        # Public users see only active services
        if self.request.user.is_authenticated and self.request.user.role in ['admin', 'manager', 'accounts']:
            return Service.objects.all()
        return Service.objects.filter(is_active=True)
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsAuthenticated(), IsAdminUser()]


class ServiceResourceViewSet(viewsets.ModelViewSet):
    """Service resources (downloadable files)"""
    serializer_class = ServiceResourceSerializer
    
    def get_queryset(self):
        service_id = self.kwargs.get('service_pk')
        return ServiceResource.objects.filter(service_id=service_id)
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsAuthenticated(), IsAdminUser()]
    
    def perform_create(self, serializer):
        service_id = self.kwargs.get('service_pk')
        service = Service.objects.get(id=service_id)
        
        file = self.request.FILES['file']
        
        serializer.save(
            service=service,
            file_size=file.size,
            file_type=file.name.split('.')[-1].lower()
        )
