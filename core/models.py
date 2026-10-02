from django.db import models
from django.conf import settings

class Wallet(models.Model):
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

class PaymentMethod(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    bank = models.CharField(max_length=80)
    network = models.CharField(max_length=20)
    last4 = models.CharField(max_length=4)
    cardholder = models.CharField(max_length=100, blank=True)
    expiry = models.CharField(max_length=7, blank=True)
    active = models.BooleanField(default=True)
    def __str__(self):
        return f'{self.bank} {self.network} •••• {self.last4}'

class ActionRequest(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    kind = models.CharField(max_length=30)
    arguments = models.JSONField(default=dict)
    status = models.CharField(max_length=20, default='pending')
    created = models.DateTimeField(auto_now_add=True)

class Budget(models.Model):
    payment_method = models.ForeignKey(PaymentMethod, null=True, blank=True, on_delete=models.SET_NULL)

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
    currency = models.CharField(max_length=3, default='AED')
    due = models.DateField()
    paid = models.BooleanField(default=False)
    period = models.DateField(null=True, blank=True)
    source = models.CharField(max_length=30, default='synthetic_demo')

class Payment(models.Model):
    payment_method = models.ForeignKey(PaymentMethod, null=True, blank=True, on_delete=models.SET_NULL)
    bill = models.OneToOneField(Bill, on_delete=models.CASCADE, related_name='+')
    created = models.DateTimeField(auto_now_add=True)
    mode = models.CharField(max_length=20, default='manual_demo')

class Conversation(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=100, default="New chat")
    created = models.DateTimeField(auto_now_add=True)

class Message(models.Model):
    metadata = models.JSONField(default=dict, blank=True)
    conversation = models.ForeignKey(Conversation, null=True, blank=True, on_delete=models.CASCADE)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='+')
    role = models.CharField(max_length=20)
    text = models.TextField()
    created = models.DateTimeField(auto_now_add=True)
