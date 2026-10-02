from django.db import models
from django.conf import settings

class Budget(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='+')
    category = models.CharField(max_length=60)
    limit = models.DecimalField(max_digits=12, decimal_places=2, default=500)
    autopay = models.BooleanField(default=False)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['owner','category'], name='bayt_unique_budget')]

class Bill(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='+')
    merchant = models.CharField(max_length=100)
    category = models.CharField(max_length=60)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    due = models.DateField()
    paid = models.BooleanField(default=False)
    source = models.CharField(max_length=30, default='synthetic_demo')

class Payment(models.Model):
    bill = models.OneToOneField(Bill, on_delete=models.CASCADE, related_name='+')
    created = models.DateTimeField(auto_now_add=True)
    mode = models.CharField(max_length=20, default='manual_demo')

class Message(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='+')
    role = models.CharField(max_length=20)
    text = models.TextField()
    created = models.DateTimeField(auto_now_add=True)
