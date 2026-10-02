from django.db import models
from django.db.models.fields.files import FileField, FieldFile
import hashlib

class DedupFieldFile(FieldFile):
    def save(self, name, content, save=True):
        # Compute hash
        content.seek(0)
        file_data = content.read()
        content.seek(0)
        file_hash = hashlib.sha256(file_data).hexdigest()
        # Set hash on instance
        setattr(self.instance, self.field.hash_field, file_hash)
        # Check for duplicate in same model
        Model = type(self.instance)
        existing = Model.objects.filter(**{self.field.hash_field: file_hash}).exclude(pk=self.instance.pk).first()
        if existing:
            # Point to existing file path, do NOT call super().save()
            self.name = getattr(existing, self.field.name).name
            setattr(self.instance, self.field.attname, self.name)
            # Save the model instance to persist the file path and hash
            self.instance.save(update_fields=[self.field.name, self.field.hash_field])
        else:
            super().save(name, content, save=save)

class DedupFileField(FileField):
    attr_class = DedupFieldFile

    def __init__(self, *args, hash_field='hash', **kwargs):
        self.hash_field = hash_field
        super().__init__(*args, **kwargs)

    def contribute_to_class(self, cls, name, **kwargs):
        super().contribute_to_class(cls, name, **kwargs)
        # Document: model must have a nullable, indexed (not unique) hash field with name self.hash_field

# Utility for model delete methods

def only_delete_file_if_unused(instance, file_field_name, hash_field_name):
    """
    Call this in your model's delete method before deleting the file.
    Deletes the file only if no other objects of the same model share the same hash.
    """
    Model = type(instance)
    file_field = getattr(instance, file_field_name)
    file_hash = getattr(instance, hash_field_name)
    if file_field and file_hash:
        others = Model.objects.filter(**{hash_field_name: file_hash}).exclude(pk=instance.pk)
        if not others.exists():
            file_field.delete(save=False)
# Usage:
# 1. Add a nullable, indexed (not unique) hash field to your model (e.g. hash = models.CharField(max_length=64, blank=True, null=True, db_index=True))
# 2. Use DedupFileField in place of FileField, e.g. file = DedupFileField(upload_to=..., hash_field='hash')
# 3. In your model's delete method, call only_delete_file_if_unused(self, 'file', 'hash') before super().delete() 