"""
Django REST Framework API views for GeoPlace
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
import logging

from .models import Tile, GenerationJob, ThreeDObject, VLMAnalysis, SystemStatus
from .serializers import (
    TileSerializer, GenerationJobSerializer, ThreeDObjectSerializer,
    VLMAnalysisSerializer, SystemStatusSerializer
)

logger = logging.getLogger('geoplace')


class TileViewSet(viewsets.ModelViewSet):
    """API viewset for tiles"""
    serializer_class = TileSerializer
    permission_classes = [AllowAny]
    
    def get_queryset(self):
        queryset = Tile.objects.all()
        
        # Filter by coordinates
        x = self.request.query_params.get('x')
        y = self.request.query_params.get('y')
        if x is not None and y is not None:
            queryset = queryset.filter(x=x, y=y)
        
        # Filter by region
        min_x = self.request.query_params.get('min_x')
        max_x = self.request.query_params.get('max_x')
        min_y = self.request.query_params.get('min_y')
        max_y = self.request.query_params.get('max_y')
        
        if all(v is not None for v in [min_x, max_x, min_y, max_y]):
            queryset = queryset.filter(
                x__gte=min_x, x__lte=max_x,
                y__gte=min_y, y__lte=max_y
            )
        
        return queryset.order_by('-updated_at')
    
    @action(detail=False, methods=['get'])
    def modified(self, request):
        """Get recently modified tiles"""
        since_minutes = int(request.query_params.get('since_minutes', 60))
        since_time = timezone.now() - timedelta(minutes=since_minutes)
        
        tiles = Tile.objects.filter(updated_at__gte=since_time)
        serializer = self.get_serializer(tiles, many=True)
        
        return Response({
            'tiles': serializer.data,
            'count': len(serializer.data),
            'since_minutes': since_minutes
        })
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get tile statistics"""
        total_tiles = Tile.objects.count()
        tiles_with_objects = Tile.objects.filter(objects__isnull=False).distinct().count()
        tiles_with_vlm = Tile.objects.filter(vlm_analysis__isnull=False).count()
        
        recent_24h = Tile.objects.filter(
            updated_at__gte=timezone.now() - timedelta(hours=24)
        ).count()
        
        return Response({
            'total': total_tiles,
            'with_objects': tiles_with_objects,
            'with_vlm_analysis': tiles_with_vlm,
            'recent_24h': recent_24h
        })


class GenerationJobViewSet(viewsets.ModelViewSet):
    """API viewset for generation jobs"""
    serializer_class = GenerationJobSerializer
    permission_classes = [AllowAny]
    
    def get_queryset(self):
        queryset = GenerationJob.objects.all()
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by date range
        since_hours = self.request.query_params.get('since_hours')
        if since_hours:
            since_time = timezone.now() - timedelta(hours=int(since_hours))
            queryset = queryset.filter(created_at__gte=since_time)
        
        return queryset.order_by('-created_at')
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a generation job"""
        job = self.get_object()
        
        if job.status in ['queued', 'processing']:
            job.status = 'cancelled'
            job.save()
            return Response({'message': 'Job cancelled successfully'})
        else:
            return Response(
                {'error': f'Cannot cancel job in status: {job.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=False, methods=['get'])
    def active(self, request):
        """Get active jobs"""
        active_jobs = GenerationJob.objects.filter(
            status__in=['queued', 'processing', 'vlm_analyzing', 'sd_generating', 'triposr_generating']
        )
        serializer = self.get_serializer(active_jobs, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get job statistics"""
        total_jobs = GenerationJob.objects.count()
        
        status_counts = {}
        for choice in GenerationJob.STATUS_CHOICES:
            status_key = choice[0]
            status_counts[status_key] = GenerationJob.objects.filter(status=status_key).count()
        
        recent_24h = GenerationJob.objects.filter(
            created_at__gte=timezone.now() - timedelta(hours=24)
        ).count()
        
        return Response({
            'total': total_jobs,
            'by_status': status_counts,
            'recent_24h': recent_24h
        })


class ThreeDObjectViewSet(viewsets.ModelViewSet):
    """API viewset for 3D objects"""
    serializer_class = ThreeDObjectSerializer
    permission_classes = [AllowAny]
    
    def get_queryset(self):
        queryset = ThreeDObject.objects.all()
        
        # Filter by quality
        quality = self.request.query_params.get('quality')
        if quality:
            queryset = queryset.filter(quality=quality)
        
        # Filter by region
        min_x = self.request.query_params.get('min_x')
        max_x = self.request.query_params.get('max_x')
        min_z = self.request.query_params.get('min_z')
        max_z = self.request.query_params.get('max_z')
        
        if all(v is not None for v in [min_x, max_x, min_z, max_z]):
            queryset = queryset.filter(
                x__gte=float(min_x), x__lte=float(max_x),
                z__gte=float(min_z), z__lte=float(max_z)
            )
        
        return queryset.order_by('-created_at')
    
    @action(detail=False, methods=['get'])
    def aframe(self, request):
        """Get objects formatted for A-Frame"""
        limit = int(request.query_params.get('limit', 100))
        objects = self.get_queryset()[:limit]
        
        aframe_objects = []
        for obj in objects:
            aframe_objects.append(obj.to_aframe_dict())
        
        return Response({
            'objects': aframe_objects,
            'count': len(aframe_objects)
        })
    
    @action(detail=False, methods=['get'])
    def region(self, request):
        """Get objects in a specific region"""
        min_x = float(request.query_params.get('min_x', 0))
        min_z = float(request.query_params.get('min_z', 0))
        max_x = float(request.query_params.get('max_x', 100))
        max_z = float(request.query_params.get('max_z', 100))
        
        objects = ThreeDObject.objects.filter(
            x__gte=min_x, x__lte=max_x,
            z__gte=min_z, z__lte=max_z
        )
        
        serializer = self.get_serializer(objects, many=True)
        
        return Response({
            'objects': serializer.data,
            'count': len(serializer.data),
            'region': {
                'min_x': min_x, 'min_z': min_z,
                'max_x': max_x, 'max_z': max_z
            }
        })
    
    @action(detail=True, methods=['post'])
    def move(self, request, pk=None):
        """Move object to new position"""
        obj = self.get_object()
        
        x = request.data.get('x')
        y = request.data.get('y')
        z = request.data.get('z')
        
        if x is not None:
            obj.x = float(x)
        if y is not None:
            obj.y = float(y)
        if z is not None:
            obj.z = float(z)
        
        obj.save()
        
        serializer = self.get_serializer(obj)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get 3D object statistics"""
        total_objects = ThreeDObject.objects.count()
        
        quality_counts = {
            'light': ThreeDObject.objects.filter(quality='light').count(),
            'refined': ThreeDObject.objects.filter(quality='refined').count(),
            'fallback': ThreeDObject.objects.filter(quality='fallback').count()
        }
        
        recent_24h = ThreeDObject.objects.filter(
            created_at__gte=timezone.now() - timedelta(hours=24)
        ).count()
        
        return Response({
            'total': total_objects,
            'by_quality': quality_counts,
            'recent_24h': recent_24h
        })


class VLMAnalysisViewSet(viewsets.ModelViewSet):
    """API viewset for VLM analysis results"""
    serializer_class = VLMAnalysisSerializer
    permission_classes = [AllowAny]
    
    def get_queryset(self):
        queryset = VLMAnalysis.objects.all()
        
        # Filter by category
        category = self.request.query_params.get('category')
        if category:
            queryset = queryset.filter(category=category)
        
        # Filter by size
        size = self.request.query_params.get('size')
        if size:
            queryset = queryset.filter(size=size)
        
        # Filter by confidence threshold
        min_confidence = self.request.query_params.get('min_confidence')
        if min_confidence:
            queryset = queryset.filter(confidence_score__gte=float(min_confidence))
        
        return queryset.order_by('-created_at')
    
    @action(detail=False, methods=['get'])
    def categories(self, request):
        """Get category statistics"""
        categories = VLMAnalysis.objects.values('category').distinct()
        category_counts = {}
        
        for cat in categories:
            category = cat['category']
            category_counts[category] = VLMAnalysis.objects.filter(category=category).count()
        
        return Response(category_counts)
    
    @action(detail=False, methods=['get'])
    def sizes(self, request):
        """Get size distribution"""
        sizes = VLMAnalysis.objects.values('size').distinct()
        size_counts = {}
        
        for size_obj in sizes:
            size = size_obj['size']
            size_counts[size] = VLMAnalysis.objects.filter(size=size).count()
        
        return Response(size_counts)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get VLM analysis statistics"""
        total_analyses = VLMAnalysis.objects.count()
        
        avg_confidence = VLMAnalysis.objects.aggregate(
            avg_confidence=models.Avg('confidence_score')
        )['avg_confidence'] or 0
        
        avg_processing_time = VLMAnalysis.objects.aggregate(
            avg_time=models.Avg('processing_time')
        )['avg_time'] or 0
        
        return Response({
            'total': total_analyses,
            'average_confidence': round(avg_confidence, 3),
            'average_processing_time': round(avg_processing_time, 3)
        })


class SystemStatusViewSet(viewsets.ModelViewSet):
    """API viewset for system status"""
    serializer_class = SystemStatusSerializer
    permission_classes = [AllowAny]
    queryset = SystemStatus.objects.all()
    
    @action(detail=False, methods=['get'])
    def overview(self, request):
        """Get system overview"""
        statuses = {}
        for status_obj in SystemStatus.objects.all():
            statuses[status_obj.component] = {
                'status': status_obj.status,
                'error_message': status_obj.error_message,
                'last_check': status_obj.last_check,
                'metadata': status_obj.metadata
            }
        
        return Response(statuses)
    
    @action(detail=False, methods=['post'])
    def update_status(self, request):
        """Update component status"""
        component = request.data.get('component')
        status_value = request.data.get('status')
        error_message = request.data.get('error_message', '')
        metadata = request.data.get('metadata', {})
        
        if not component or not status_value:
            return Response(
                {'error': 'component and status are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        status_obj, created = SystemStatus.objects.get_or_create(
            component=component,
            defaults={
                'status': status_value,
                'error_message': error_message,
                'metadata': metadata
            }
        )
        
        if not created:
            status_obj.status = status_value
            status_obj.error_message = error_message
            status_obj.metadata = metadata
            status_obj.save()
        
        serializer = self.get_serializer(status_obj)
        return Response(serializer.data)
