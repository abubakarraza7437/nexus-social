"""
Publisher — Serializers
=======================
API representation of Post and Schedule models.
"""
from rest_framework import serializers
from apps.publisher.models import Post


class PostSerializer(serializers.ModelSerializer):
    class Meta:
        model = Post
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]
