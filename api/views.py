from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .models import AuditLog, Comment, Document, DocumentVersion, Tag, User, Workspace, WorkspaceMember
from .serializers import (
    AuditLogSerializer, CommentSerializer, DocumentSerializer, DocumentVersionSerializer,
    TagSerializer, UserSerializer, WorkspaceMemberSerializer, WorkspaceSerializer,
)


def member_for(user, workspace):
    return WorkspaceMember.objects.filter(user=user, workspace=workspace).first()


def require_role(user, workspace, allowed):
    membership = member_for(user, workspace)
    if membership is None or membership.role not in allowed:
        raise PermissionDenied("You do not have permission to perform this action.")
    return membership


def save_version(document, actor):
    number = document.versions.count() + 1
    return DocumentVersion.objects.create(
        document=document, content=document.content, version_number=number, saved_by=actor
    )


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [AllowAny]
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def get_queryset(self):
        # Authenticated users can retrieve their own record; unauthenticated requests can only register.
        if self.request.user.is_authenticated:
            return User.objects.filter(pk=self.request.user.pk)
        return User.objects.none()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response({
            "user": UserSerializer(user).data,
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }, status=status.HTTP_201_CREATED)


class WorkspaceViewSet(viewsets.ModelViewSet):
    serializer_class = WorkspaceSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return (
            Workspace.objects.filter(members__user=self.request.user, is_active=True)
            .select_related("owner")
            .annotate(member_count=Count("members", distinct=True))
            .distinct()
        )

    def perform_create(self, serializer):
        try:
            with transaction.atomic():
                workspace = serializer.save(owner=self.request.user)
                WorkspaceMember.objects.create(
                    workspace=workspace, user=self.request.user, role=WorkspaceMember.Role.ADMIN
                )
        except IntegrityError as exc:
            raise ValidationError({"detail": "Workspace could not be created due to a data conflict."}) from exc

    def perform_update(self, serializer):
        require_role(self.request.user, self.get_object(), [WorkspaceMember.Role.ADMIN])
        serializer.save()

    def perform_destroy(self, instance):
        require_role(self.request.user, instance, [WorkspaceMember.Role.ADMIN])
        instance.delete()

    @action(detail=True, methods=["get", "post"], url_path="members")
    def members(self, request, pk=None):
        workspace = self.get_object()
        if request.method == "GET":
            require_role(request.user, workspace, WorkspaceMember.Role.values)
            qs = workspace.members.select_related("user").all()
            return Response(WorkspaceMemberSerializer(qs, many=True).data)

        require_role(request.user, workspace, [WorkspaceMember.Role.ADMIN])
        user_id = request.data.get("user")
        role = request.data.get("role", WorkspaceMember.Role.VIEWER)
        if not user_id:
            raise ValidationError({"user": "This field is required."})
        if role not in WorkspaceMember.Role.values:
            raise ValidationError({"role": "Choose admin, editor, or viewer."})
        user = get_object_or_404(User, pk=user_id)
        try:
            with transaction.atomic():
                membership = WorkspaceMember.objects.create(workspace=workspace, user=user, role=role)
        except IntegrityError as exc:
            return Response({"detail": "This user is already a workspace member."}, status=status.HTTP_409_CONFLICT)
        return Response(WorkspaceMemberSerializer(membership).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="summary")
    def summary(self, request, pk=None):
        workspace = self.get_object()
        require_role(request.user, workspace, WorkspaceMember.Role.values)
        docs = workspace.documents.aggregate(
            total=Count("id"),
        )
        comments = Comment.objects.filter(document__workspace=workspace).count()
        return Response({
            "workspace_id": str(workspace.id),
            "member_count": workspace.members.count(),
            "document_count": docs["total"],
            "comment_count": comments,
        })


class DocumentViewSet(viewsets.ModelViewSet):
    serializer_class = DocumentSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "put", "head", "options"]

    def get_queryset(self):
        workspace_ids = WorkspaceMember.objects.filter(user=self.request.user).values_list("workspace_id", flat=True)
        qs = (
            Document.objects.filter(workspace_id__in=workspace_ids)
            .select_related("workspace", "created_by")
            .prefetch_related("tags")
            .annotate(version_count=Count("versions", distinct=True))
        )
        params = self.request.query_params
        if params.get("workspace"):
            qs = qs.filter(workspace_id=params["workspace"])
        if params.get("status"):
            qs = qs.filter(status__in=params.get("status").split(","))
        if params.get("title"):
            qs = qs.filter(title__icontains=params["title"])
        if params.get("search"):
            term = params["search"]
            qs = qs.filter(Q(title__icontains=term) | Q(content__icontains=term))
        if params.get("updated_after"):
            value = parse_datetime(params["updated_after"])
            if value is None:
                raise ValidationError({"updated_after": "Use an ISO-8601 datetime."})
            qs = qs.filter(updated_at__gte=value)
        if params.get("updated_before"):
            value = parse_datetime(params["updated_before"])
            if value is None:
                raise ValidationError({"updated_before": "Use an ISO-8601 datetime."})
            qs = qs.filter(updated_at__lte=value)
        if params.get("ids"):
            qs = qs.filter(id__in=params["ids"].split(","))
        if params.get("tag"):
            qs = qs.filter(tags__name__icontains=params["tag"])
        return qs.distinct()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        workspace = get_object_or_404(Workspace, pk=serializer.validated_data["workspace"].pk, is_active=True)
        require_role(request.user, workspace, [WorkspaceMember.Role.ADMIN, WorkspaceMember.Role.EDITOR])
        try:
            with transaction.atomic():
                document = serializer.save(created_by=request.user, workspace=workspace)
                save_version(document, request.user)
        except IntegrityError as exc:
            raise ValidationError({"detail": "Document could not be created."}) from exc
        return Response(self.get_serializer(document).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        document = self.get_object()
        workspace = document.workspace
        require_role(request.user, workspace, [WorkspaceMember.Role.ADMIN, WorkspaceMember.Role.EDITOR])
        serializer = self.get_serializer(document, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                locked = Document.objects.select_for_update().get(pk=document.pk)
                serializer.instance = locked
                saved = serializer.save()
                save_version(saved, request.user)
        except Document.DoesNotExist as exc:
            return Response({"detail": "Document not found."}, status=status.HTTP_404_NOT_FOUND)
        except IntegrityError as exc:
            raise ValidationError({"detail": "Document update failed due to a data conflict."}) from exc
        return Response(self.get_serializer(saved).data)

    @action(detail=True, methods=["get"], url_path="versions")
    def versions(self, request, pk=None):
        document = self.get_object()
        qs = document.versions.select_related("saved_by").all()
        return Response(DocumentVersionSerializer(qs, many=True).data)

    @action(detail=True, methods=["get"], url_path="stats")
    def stats(self, request, pk=None):
        document = self.get_object()
        return Response({
            "document_id": str(document.id),
            "version_count": document.versions.count(),
            "comment_count": document.comments.count(),
            "tag_count": document.tags.count(),
        })

    @action(detail=True, methods=["post"], url_path="tags")
    def add_tags(self, request, pk=None):
        document = self.get_object()
        require_role(request.user, document.workspace, [WorkspaceMember.Role.ADMIN, WorkspaceMember.Role.EDITOR])
        ids = request.data.get("tag_ids", [])
        if not isinstance(ids, list):
            raise ValidationError({"tag_ids": "Expected a list of tag UUIDs."})
        tags = list(Tag.objects.filter(id__in=ids))
        if len(tags) != len(set(ids)):
            raise ValidationError({"tag_ids": "One or more tags do not exist."})
        document.tags.add(*tags)
        return Response(self.get_serializer(document).data, status=status.HTTP_200_OK)

    def perform_destroy(self, instance):
        require_role(self.request.user, instance.workspace, [WorkspaceMember.Role.ADMIN])
        instance.delete()


class CommentViewSet(viewsets.ModelViewSet):
    serializer_class = CommentSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        workspace_ids = WorkspaceMember.objects.filter(user=self.request.user).values_list("workspace_id", flat=True)
        qs = Comment.objects.filter(document__workspace_id__in=workspace_ids).select_related(
            "document", "document__workspace", "author", "parent"
        )
        if self.request.query_params.get("document"):
            qs = qs.filter(document_id=self.request.query_params["document"])
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document = serializer.validated_data["document"]
        if not member_for(request.user, document.workspace):
            raise PermissionDenied("Join the workspace before commenting.")
        comment = serializer.save(author=request.user)
        return Response(self.get_serializer(comment).data, status=status.HTTP_201_CREATED)


class TagViewSet(viewsets.ModelViewSet):
    serializer_class = TagSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return Tag.objects.annotate(document_count=Count("documents", distinct=True)).order_by("name")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            tag = serializer.save()
        except IntegrityError as exc:
            return Response({"detail": "A tag with this name already exists."}, status=status.HTTP_409_CONFLICT)
        return Response(self.get_serializer(tag).data, status=status.HTTP_201_CREATED)


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        params = self.request.query_params
        qs = AuditLog.objects.filter(actor=self.request.user).select_related("actor")
        if params.get("actor"):
            qs = qs.filter(actor_id=params["actor"])
        if params.get("from"):
            dt = parse_datetime(params["from"])
            if dt is None:
                raise ValidationError({"from": "Use an ISO-8601 datetime."})
            qs = qs.filter(timestamp__gte=dt)
        if params.get("to"):
            dt = parse_datetime(params["to"])
            if dt is None:
                raise ValidationError({"to": "Use an ISO-8601 datetime."})
            qs = qs.filter(timestamp__lte=dt)
        if params.get("ids"):
            qs = qs.filter(id__in=params["ids"].split(","))
        return qs
