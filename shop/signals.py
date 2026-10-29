from django.db.models.signals import post_save, post_migrate
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.utils import timezone
from .models import UserProfile, ReferralSettings, SiteSettings, AboutUs, PriceSettings


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()


@receiver(post_migrate)
def create_default_settings(sender, **kwargs):
    if sender.name == 'shop':
        ReferralSettings.objects.get_or_create(
            id=1,
            defaults={
                'is_active': True,
                'referrer_discount_type': 'percentage',
                'referrer_discount_amount': 5.00,
                'referrer_credit_amount': 50000,
                'new_user_discount_type': 'percentage',
                'new_user_discount_amount': 5.00,
                'discount_expiry_days': 30,
            }
        )

        SiteSettings.objects.get_or_create(
            id=1,
            defaults={
                'site_name': 'ساچمه فر',
                'site_description': 'فروشگاه ساچمه فر',
                'logo_text': 'ساچمه فر',
            }
        )

        PriceSettings.objects.get_or_create(pk=1)

        AboutUs.objects.get_or_create(
            is_active=True,
            defaults={
                'title': 'درباره ساچمه فر',
                'content': 'به فروشگاه ساچمه فر خوش آمدید.',
            }
        )


def user_has_unused_discount_codes(self):
    from .models import DiscountCode
    return self.discountcode_set.filter(is_used=False, expires_at__gte=timezone.now()).exists()


def user_get_unused_discount_codes(self):
    from .models import DiscountCode
    return self.discountcode_set.filter(is_used=False, expires_at__gte=timezone.now())


User.add_to_class('has_unused_discount_codes', user_has_unused_discount_codes)
User.add_to_class('get_unused_discount_codes', user_get_unused_discount_codes)