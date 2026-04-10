from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from apps.auth_core.permissions import IsEditor, IsViewer
from apps.auth_core.throttling import OrgPlanThrottle
from apps.posts.models import Post
from apps.posts.serializers import PostSerializer, PostCreateSerializer


class PostViewSet(viewsets.ModelViewSet):

    throttle_classes = [OrgPlanThrottle]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["status"]
    ordering_fields = ["scheduled_at", "created_at"]
    ordering = ["-scheduled_at", "-created_at"]

    def get_queryset(self):
        return (
            Post.objects.filter(organization=self.request.tenant)
            .prefetch_related("targets")
        )

    def get_serializer_class(self):
        if self.action == "create":
            return PostCreateSerializer
        return PostSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated(), IsViewer()]
        return [IsAuthenticated(), IsEditor()]
