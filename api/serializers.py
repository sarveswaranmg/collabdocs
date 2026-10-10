from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import (
    AuditLog, Comment, Document, DocumentVersion, Tag, User,
    Workspace, WorkspaceMember,
)


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email", "phone", "password", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exclude(pk=getattr(self.instance, "pk", None)).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value.lower()

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class WorkspaceMemberSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = WorkspaceMember
        fields = ["id", "workspace", "user", "username", "email", "role", "joined_at"]
        read_only_fields = ["id", "workspace", "joined_at", "username", "email"]


class WorkspaceSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source="owner.username", read_only=True)
    member_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Workspace
        fields = ["id", "name", "owner", "owner_username", "is_active", "created_at", "member_count"]
        read_only_fields = ["id", "owner", "is_active", "created_at", "member_count"]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Workspace name cannot be empty.")
        return value


class DocumentVersionSerializer(serializers.ModelSerializer):
    saved_by_username = serializers.CharField(source="saved_by.username", read_only=True, default=None)

    class Meta:
        model = DocumentVersion
        fields = ["id", "document", "content", "version_number", "saved_by", "saved_by_username", "saved_at"]
        read_only_fields = ["id", "document", "version_number", "saved_by", "saved_at", "saved_by_username"]


class TagSerializer(serializers.ModelSerializer):
    document_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Tag
        fields = ["id", "name", "document_count"]
        read_only_fields = ["id", "document_count"]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Tag name cannot be empty.")
        return value


class DocumentSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source="created_by.username", read_only=True, default=None)
    workspace_name = serializers.CharField(source="workspace.name", read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    tag_ids = serializers.PrimaryKeyRelatedField(
        source="tags", many=True, queryset=Tag.objects.all(), write_only=True, required=False
    )
    version_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Document
        fields = [
            "id", "title", "content", "workspace", "workspace_name", "created_by",
            "created_by_username", "status", "updated_at", "tags", "tag_ids", "version_count",
        ]
        read_only_fields = ["id", "created_by", "updated_at", "version_count"]

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Document title cannot be empty.")
        return value

    def validate_status(self, value):
        if value == Document.Status.ARCHIVED and self.instance is None:
            raise serializers.ValidationError("Create the document first; archive it with an update.")
        return value


class CommentSerializer(serializers.ModelSerializer):
    author_username = serializers.CharField(source="author.username", read_only=True, default=None)

    class Meta:
        model = Comment
        fields = ["id", "document", "author", "author_username", "content", "parent", "created_at"]
        read_only_fields = ["id", "author", "created_at", "author_username"]

    def validate(self, attrs):
        parent = attrs.get("parent", getattr(self.instance, "parent", None))
        document = attrs.get("document", getattr(self.instance, "document", None))
        if parent and document and parent.document_id != document.id:
            raise serializers.ValidationError({"parent": "Parent comment must belong to the same document."})
        if not attrs.get("content", getattr(self.instance, "content", "")).strip():
            raise serializers.ValidationError({"content": "Comment content cannot be empty."})
        return attrs


class AuditLogSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source="actor.username", read_only=True, default=None)

    class Meta:
        model = AuditLog
        fields = ["id", "actor", "actor_username", "action", "model_name", "object_id", "timestamp"]
        read_only_fields = fields
