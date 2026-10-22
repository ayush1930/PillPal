from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from core.features.accounts.models import User, Address
from core.features.pharmacies.models import Pharmacy, PharmacyStaff
from core.features.medications.models import Medication
from core.features.inventory.models import InventoryItem, ReorderRequest
from core.features.prescriptions.models import Prescription
from core.features.orders.models import Order, OrderItem

from core.features.suppliers.models import Supplier
from core.features.reminders.models import Reminder
from core.features.reviews.models import Review
from core.features.notifications.models import Notification

# Register addresses in the Django admin panel
admin.site.register(Address)

# Custom admin panel for PillPal users
@admin.register(User)
class PillPalUserAdmin(UserAdmin):
    ordering = ("email",)
    list_display = ("email", "role", "is_active", "is_staff")

    # Fields shown when editing a user
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "phone", "avatar")}),
        ("PillPal", {"fields": ("role", "is_verified", "invited_by")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}))

    # Fields shown when creating a new user
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "password1", "password2", "role")
        }))

# Register pharmacies and their staff
admin.site.register(Pharmacy)
admin.site.register(PharmacyStaff)

# Register medications
admin.site.register(Medication)

# Register inventory items and restock requests
admin.site.register(InventoryItem)
admin.site.register(ReorderRequest)

# Register prescriptions
admin.site.register(Prescription)

# Register orders and their items
admin.site.register(Order)
admin.site.register(OrderItem)

# Register suppliers
admin.site.register(Supplier)

# Register medication reminders
admin.site.register(Reminder)

# Register customer reviews
admin.site.register(Review)

# Register notifications
admin.site.register(Notification)