from django.db import models


class AccountChat(models.Model):
    account = models.ForeignKey('unicom.Account', on_delete=models.CASCADE)
    chat = models.ForeignKey('unicom.Chat', on_delete=models.CASCADE)

    class Meta:
        unique_together = ('account', 'chat')

    def __str__(self) -> str:
        return f"{self.account.name}>--<{self.chat.name}"
