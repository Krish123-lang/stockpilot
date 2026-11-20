from django.db import models

# Create your models here.
from django.contrib.auth.models import AbstractUser
from django.db.models.functions import Lower
from .managers import CustomUserManager


class User(AbstractUser):
    username = None
    email = models.EmailField(unique = True)
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = CustomUserManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                name="accounts_user_email_ci_unique",
            )
        ]

    def __str__(self):
        return self.email
