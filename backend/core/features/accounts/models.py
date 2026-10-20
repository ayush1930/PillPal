from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from core.common.models import TimestampedModel

class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('role', User.Role.ADMIN)
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)

class User(AbstractUser):

    class Role(models.TextChoices):
        PATIENT = ('patient', 'Patient')
        PHARMACIST = ('pharmacist', 'Pharmacist')
        DRIVER = ('driver', 'Driver')
        ADMIN = ('admin', 'Administrator')
    username = None
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.PATIENT)
    phone = models.CharField(max_length=40, blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True)
    is_verified = models.BooleanField(default=False)
    invited_by = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL)
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    objects = UserManager()

    @property
    def name(self):
        return self.get_full_name() or self.email

    class Meta:
        db_table = 'accounts_user'

class Address(TimestampedModel):
    user = models.ForeignKey('core.User', on_delete=models.CASCADE, related_name='addresses')
    label = models.CharField(max_length=80)
    street = models.CharField(max_length=180)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=80)
    postal_code = models.CharField(max_length=20)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True,
        validators=[MinValueValidator(-90), MaxValueValidator(90)])
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True,
        validators=[MinValueValidator(-180), MaxValueValidator(180)])
    is_default = models.BooleanField(default=False)

    class Meta:
        db_table = 'accounts_address'
