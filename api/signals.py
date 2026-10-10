from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from .models import AuditLog, Document


@receiver(pre_save, sender=Document)
def remember_document_state(sender, instance, **kwargs):
    # post_save has _state.adding=False; snapshot the pre-save state.
    instance._audit_was_adding = instance._state.adding


@receiver(post_save, sender=Document)
def audit_document_save(sender, instance, **kwargs):
    AuditLog.objects.create(
        actor=instance.created_by,
        action="created" if getattr(instance, "_audit_was_adding", False) else "updated",
        model_name="Document",
        object_id=str(instance.pk),
    )
