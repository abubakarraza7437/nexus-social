from rest_framework import serializers
from apps.posts.models import Post, PostTarget


class PostTargetSerializer(serializers.ModelSerializer):
    class Meta:
        model = PostTarget
        fields = [
            "id",
            "platform",
            "status",
            "remote_post_id",
            "published_at",
            "error",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "remote_post_id",
            "published_at",
            "error",
            "created_at",
            "updated_at",
        ]


class PostSerializer(serializers.ModelSerializer):
    targets = PostTargetSerializer(many=True, read_only=True)

    class Meta:
        model = Post
        fields = [
            "id",
            "status",
            "scheduled_at",
            "published_at",
            "targets",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "published_at",
            "created_at",
            "updated_at",
        ]


class PostCreateSerializer(serializers.ModelSerializer):
    """Used for POST /posts/ — writes org and author from request context."""

    targets = PostTargetSerializer(many=True, read_only=True)

    class Meta:
        model = Post
        fields = [
            "id",
            "scheduled_at",
            "targets",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def create(self, validated_data):
        request = self.context["request"]
        # request.org is set by JWTAuthenticationWithContext (alias for request.tenant).
        # request.tenant is the fallback in case org was not yet aliased.
        validated_data["organization"] = getattr(request, "org", None) or request.tenant
        validated_data["author"] = request.user
        return super().create(validated_data)
