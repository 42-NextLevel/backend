from django.db import models

# Create your models here.

class ContractAddress(models.Model):
    address = models.CharField(max_length=42)  # 이더리움 주소는 42자
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'tb_blockchain_address'
        constraints = [
            models.CheckConstraint(check=models.Q(id=1), name='singleton')
        ]

    def save(self, *args, **kwargs):
        if not self.pk and ContractAddress.objects.exists():
            # 이미 레코드가 존재하면 저장하지 않음
            return
        super().save(*args, **kwargs)