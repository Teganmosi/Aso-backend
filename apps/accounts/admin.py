from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, CustomerProfile, Address

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('email', 'first_name', 'last_name', 'phone_number', 'email_confirmed', 'is_staff', 'is_active', 'date_joined')
    list_filter = ('is_staff', 'is_active', 'is_superuser', ('email_verified_at', admin.EmptyFieldListFilter))
    search_fields = ('email', 'first_name', 'last_name', 'phone_number')
    search_help_text = 'Search by name, email or phone'
    ordering = ('-date_joined',)
    actions = ['mark_email_confirmed']

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'phone_number', 'email_verified_at')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'first_name', 'last_name', 'password1', 'password2'),
        }),
    )

    @admin.display(boolean=True, description='Email confirmed', ordering='email_verified_at')
    def email_confirmed(self, obj):
        return obj.email_verified_at is not None

    @admin.action(description='Mark email as confirmed (e.g. confirmed by phone with support)')
    def mark_email_confirmed(self, request, queryset):
        from django.utils import timezone
        updated = queryset.filter(email_verified_at__isnull=True).update(email_verified_at=timezone.now())
        self.message_user(request, f'{updated} account(s) marked as confirmed.')


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'created_at')
    search_fields = ('user__email', 'user__first_name', 'user__last_name')


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'user', 'city', 'state', 'phone_number', 'is_default', 'created_at')
    list_filter = ('is_default', 'state', 'city')
    search_fields = ('full_name', 'street_address', 'city', 'state', 'user__email')
