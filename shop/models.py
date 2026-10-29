import logging
import requests
from datetime import timedelta
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from django.conf import settings as dj_settings
from django.db import models, transaction
from django.db.models import Q
from django.urls import reverse
from django.utils.text import slugify
from django.utils import timezone
from django.contrib.auth.models import User
import random
import string
import uuid


def timezone_now_str():
    return timezone.now().strftime('%Y%m%d')


# ==================== تنظیمات سایت ====================

class SiteSettings(models.Model):
    site_name = models.CharField(max_length=100, default="ساچمه فر", verbose_name="نام سایت")
    site_description = models.TextField(blank=True, verbose_name="توضیحات سایت")
    logo_text = models.CharField(max_length=50, default="ساچمه فر", verbose_name="متن لوگو")

    background_image = models.ImageField(upload_to='backgrounds/', blank=True, null=True, verbose_name="عکس پس‌زمینه")
    background_overlay_opacity = models.PositiveIntegerField(default=70, verbose_name="درصد تیرگی روی عکس (0-100)")
    background_fixed = models.BooleanField(default=True, verbose_name="ثابت بودن پس‌زمینه")

    address_line1 = models.CharField(max_length=200, default="", verbose_name="آدرس خط ۱")
    address_line2 = models.CharField(max_length=200, default="", verbose_name="آدرس خط ۲", blank=True)
    address_city = models.CharField(max_length=100, default="", verbose_name="شهر")
    address_state = models.CharField(max_length=100, default="", verbose_name="استان")
    address_postal_code = models.CharField(max_length=20, blank=True, verbose_name="کد پستی")

    phone1 = models.CharField(max_length=20, default="", verbose_name="تلفن ۱")
    phone2 = models.CharField(max_length=20, blank=True, verbose_name="تلفن ۲")
    mobile = models.CharField(max_length=20, default="", verbose_name="موبایل")
    email = models.EmailField(default="", verbose_name="ایمیل")

    instagram = models.CharField(max_length=100, blank=True, default="", verbose_name="اینستاگرام")
    telegram = models.CharField(max_length=100, blank=True, default="", verbose_name="تلگرام")
    discord = models.CharField(max_length=100, blank=True, verbose_name="دیسکورد")
    whatsapp = models.CharField(max_length=100, blank=True, default="", verbose_name="واتساپ")

    min_amount_for_shaba = models.PositiveIntegerField(
        default=10000000,
        verbose_name="حداقل مبلغ برای شماره شبا (تومان)",
        help_text="اگر مبلغ سفارش از این مقدار بیشتر باشد، شماره شبا نمایش داده می‌شود"
    )
    card_number = models.CharField(max_length=30, default="", verbose_name="شماره کارت",
                                   help_text="برای مبالغ کمتر از حد مجاز")
    card_holder_name = models.CharField(max_length=100, default="", verbose_name="نام صاحب کارت")
    shaba_number = models.CharField(max_length=30, default="", verbose_name="شماره شبا",
                                    help_text="برای مبالغ بیشتر از حد مجاز")
    bank_name = models.CharField(max_length=100, default="", verbose_name="نام بانک")

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "تنظیمات سایت"
        verbose_name_plural = "تنظیمات سایت"

    def __str__(self):
        return f"تنظیمات سایت - {self.site_name}"

    def get_full_address(self):
        parts = [self.address_line1]
        if self.address_line2:
            parts.append(self.address_line2)
        if self.address_city:
            parts.append(self.address_city)
        if self.address_state:
            parts.append(self.address_state)
        return "، ".join([p for p in parts if p])


# ==================== بخش‌های فروشگاه (بدون دسته‌بندی) ====================
#
# فقط سه بخش وجود دارد: ساچمه، شمش نقره، شمش مس. هر سه روی همان جدول Product ذخیره می‌شوند
# (تا سبد خرید و سفارش‌ها دست نخورند) و در ادمین هر کدام یک «مدل پروکسی» جدا دارند.

PRODUCT_SECTIONS = [
    ('shot', 'ساچمه'),
    ('silver-bar', 'شمش نقره'),
    ('copper-bar', 'شمش مس'),
]
SECTION_LABELS = dict(PRODUCT_SECTIONS)
SECTION_FILTERS = {
    'shot': Q(kind='shot'),
    'silver-bar': Q(kind='bar', purity='995'),
    'copper-bar': Q(kind='bar', purity='99.99'),
}

# وزن‌های مجاز شمش نقره (گرم). ۳۱.۱۰۳۵ = یک انس
SILVER_BAR_WEIGHTS = [
    ('1000', '1000 گرم'),
    ('500', '500 گرم'),
    ('250', '250 گرم'),
    ('100', '100 گرم'),
    ('50', '50 گرم'),
    ('31.1035', 'یک انس (31.1035 گرم)'),
    ('20', '20 گرم'),
]


class Product(models.Model):
    PURITY_CHOICES = [
        ('999.9', 'عیار 999.9 (نقره)'),
        ('995', 'عیار 995 (نقره)'),
        ('99.99', 'خلوص 99.99 (مس)'),
    ]

    name = models.CharField(max_length=100, verbose_name="نام")
    description = models.TextField(verbose_name="توضیحات")
    kind = models.CharField(
        max_length=10,
        choices=[('bar', 'شمش'), ('shot', 'ساچمه')],
        default='bar',
        verbose_name="نوع",
        editable=False,
    )
    price = models.DecimalField(max_digits=10, decimal_places=0, default=0, verbose_name="قیمت (خودکار)")

    stock = models.PositiveIntegerField(
        default=10,
        verbose_name="موجودی (تعداد)",
        help_text="تعداد موجود در انبار (برای سبد خرید لازم است)"
    )

    weight_grams = models.DecimalField(
        max_digits=11,
        decimal_places=4,
        default=0,
        verbose_name="وزن (گرم)",
    )

    purity = models.CharField(
        max_length=10,
        choices=PURITY_CHOICES,
        default='999.9',
        verbose_name="عیار",
    )

    video = models.FileField(upload_to='products/videos/', verbose_name="ویدیو (فقط یکی)", blank=True, null=True)
    is_available = models.BooleanField(default=True, verbose_name="موجود")
    is_new = models.BooleanField(default=False, verbose_name="جدید")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.section_label} - {self.name}"

    @property
    def section_key(self):
        if self.kind == 'shot':
            return 'shot'
        return 'copper-bar' if str(self.purity) == '99.99' else 'silver-bar'

    @property
    def section_label(self):
        return SECTION_LABELS[self.section_key]

    @property
    def main_image(self):
        """اولین عکس محصول (برای کارت‌ها و سبد خرید)؛ اگر عکسی نباشد None."""
        imgs = list(self.images.all())
        return imgs[0].image if imgs else None

    @property
    def in_stock(self):
        return self.stock > 0

    def clean(self):
        # فقط بررسی مشترک؛ قوانین هر بخش داخل خود همان بخش است (جدا از هم)
        from django.core.exceptions import ValidationError
        if self.weight_grams is None or Decimal(self.weight_grams) <= 0:
            raise ValidationError({'weight_grams': 'وزن باید بیشتر از صفر باشد.'})

    def compute_price(self, ps=None):
        return calculate_price(ps or PriceSettings.get(), self.purity, self.weight_grams,
                               self.kind == 'shot')

    def save(self, *args, **kwargs):
        # قیمت دستی نیست: همیشه از وزن + عیار حساب و نوشته می‌شود
        new_price = self.compute_price()
        self.price = new_price if new_price is not None else (self.price or 0)
        uf = kwargs.get('update_fields')
        if uf is not None and 'price' not in uf:
            kwargs['update_fields'] = list(uf) + ['price']
        super().save(*args, **kwargs)

    def weight_display(self):
        w = Decimal(self.weight_grams)
        if w == w.to_integral_value():
            return f"{int(w):,} گرم"
        return f"{w:,.4f}".rstrip('0').rstrip('.') + " گرم"

    def purity_display(self):
        return self.get_purity_display()

    class Meta:
        verbose_name = "محصول"
        verbose_name_plural = "محصولات"


class ShotProduct(Product):
    """ساچمه — عیار 999.9 یا 995؛ قیمت = گرم × قیمت لحظه‌ای هر گرم."""
    class Meta:
        proxy = True
        verbose_name = "ساچمه"
        verbose_name_plural = "ساچمه‌ها"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.kind = 'shot'  # قبل از اعتبارسنجی فرم، نوع مشخص باشد

    def clean(self):
        from django.core.exceptions import ValidationError
        super().clean()
        if str(self.purity) not in ('999.9', '995'):
            raise ValidationError({'purity': 'عیار ساچمه فقط 999.9 یا 995 است.'})

    def save(self, *args, **kwargs):
        self.kind = 'shot'
        if str(self.purity) not in ('999.9', '995'):
            self.purity = '999.9'
        super().save(*args, **kwargs)


class SilverBarProduct(Product):
    """شمش نقره — همیشه عیار 995، فقط وزن‌های مجاز."""
    class Meta:
        proxy = True
        verbose_name = "شمش نقره"
        verbose_name_plural = "شمش‌های نقره"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.kind = 'bar'
        self.purity = '995'

    def clean(self):
        from django.core.exceptions import ValidationError
        super().clean()
        allowed = [Decimal(v) for v, _ in SILVER_BAR_WEIGHTS]
        if Decimal(self.weight_grams) not in allowed:
            raise ValidationError({'weight_grams': 'وزن شمش نقره فقط می‌تواند 1000، 500، 250، 100، 50، یک انس یا 20 گرم باشد.'})

    def save(self, *args, **kwargs):
        self.kind = 'bar'
        self.purity = '995'
        super().save(*args, **kwargs)


class CopperBarProduct(Product):
    """شمش مس — همیشه خلوص 99.99."""
    class Meta:
        proxy = True
        verbose_name = "شمش مس"
        verbose_name_plural = "شمش‌های مس"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.kind = 'bar'
        self.purity = '99.99'

    def save(self, *args, **kwargs):
        self.kind = 'bar'
        self.purity = '99.99'
        super().save(*args, **kwargs)


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images',
                                 verbose_name="محصول")
    image = models.ImageField(upload_to='products/gallery/', verbose_name="تصویر")
    order = models.PositiveIntegerField(default=0, verbose_name="ترتیب")

    class Meta:
        ordering = ['order', 'id']
        verbose_name = "تصویر محصول"
        verbose_name_plural = "تصاویر محصول"

    def __str__(self):
        return f"تصویر {self.product.name} - {self.id}"


# ==================== وضعیت قیمت جهانی (بدون ادمین) ====================

class PriceSettings(models.Model):
    """ردیف تک‌نفره‌ی وضعیت: آخرین قیمت جهانی و قیمت مرجع. در ادمین ثبت نشده است."""
    silver_usd_per_oz = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    copper_usd_per_oz = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    # قیمت جهانیِ لحظه‌ای که قیمت‌های تابلو (۴۷۰٬۰۰۰ و ...) با آن هم‌تراز شده‌اند
    ref_silver_oz = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    ref_copper_oz = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    last_updated = models.DateTimeField(null=True, blank=True)
    last_attempt = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def is_stale(self):
        if not self.last_updated:
            return True
        minutes = getattr(dj_settings, 'PRICE_MAX_STALE_MINUTES', 15)
        return (timezone.now() - self.last_updated).total_seconds() > minutes * 60


class PriceSnapshot(models.Model):
    """تاریخچه‌ی قیمت جهانی برای چارت صفحه اول."""
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    silver_usd_per_oz = models.DecimalField(max_digits=12, decimal_places=4)
    copper_usd_per_oz = models.DecimalField(max_digits=12, decimal_places=4)

    class Meta:
        ordering = ['-created_at']


# ==================== سوالات پرتکرار ====================

class FAQ(models.Model):
    question = models.CharField(max_length=300, verbose_name="سوال")
    answer = models.TextField(verbose_name="پاسخ")
    order = models.PositiveIntegerField(default=0, verbose_name="ترتیب")
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "سوال پرتکرار"
        verbose_name_plural = "سوالات پرتکرار"
        ordering = ['order', '-created_at']

    def __str__(self):
        return self.question


# ==================== کاربر و پروفایل ====================

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    referral_code = models.CharField(max_length=7, unique=True, verbose_name="کد معرف")
    credits = models.DecimalField(max_digits=10, decimal_places=0, default=0, verbose_name="اعتبار")
    phone = models.CharField(max_length=15, blank=True, verbose_name="شماره تماس")
    address = models.TextField(blank=True, verbose_name="آدرس")
    postal_code = models.CharField(max_length=20, blank=True, verbose_name="کد پستی")
    full_name = models.CharField(max_length=100, blank=True, verbose_name="نام و نام خانوادگی")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.referral_code:
            self.referral_code = self.generate_referral_code()
        super().save(*args, **kwargs)

    def generate_referral_code(self):
        characters = string.ascii_uppercase + string.digits
        code = ''.join(random.choice(characters) for _ in range(7))
        while UserProfile.objects.filter(referral_code=code).exists():
            code = ''.join(random.choice(characters) for _ in range(7))
        return code

    def __str__(self):
        return f"{self.user.username} - {self.referral_code}"


# ==================== سیستم معرف ====================

class ReferralSettings(models.Model):
    is_active = models.BooleanField(default=True, verbose_name="فعال بودن سیستم دعوت")
    referrer_discount_type = models.CharField(
        max_length=10,
        choices=[('percentage', 'درصدی'), ('fixed', 'ثابت')],
        default='percentage',
        verbose_name="نوع تخفیف برای معرف"
    )
    referrer_discount_amount = models.DecimalField(
        max_digits=5, decimal_places=2, default=5.00,
        verbose_name="مقدار تخفیف برای معرف (درصد یا مبلغ ثابت)"
    )
    referrer_credit_amount = models.DecimalField(
        max_digits=10, decimal_places=0, default=50000,
        verbose_name="مقدار اعتبار برای معرف (تومان)"
    )
    new_user_discount_type = models.CharField(
        max_length=10,
        choices=[('percentage', 'درصدی'), ('fixed', 'ثابت')],
        default='percentage',
        verbose_name="نوع تخفیف برای کاربر جدید"
    )
    new_user_discount_amount = models.DecimalField(
        max_digits=5, decimal_places=2, default=5.00,
        verbose_name="مقدار تخفیف برای کاربر جدید (درصد یا مبلغ ثابت)"
    )
    discount_expiry_days = models.PositiveIntegerField(
        default=30, verbose_name="مدت اعتبار کد تخفیف (روز)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "تنظیمات دعوت"
        verbose_name_plural = "تنظیمات دعوت"

    def __str__(self):
        return f"تنظیمات دعوت - {'فعال' if self.is_active else 'غیرفعال'}"


class ReferralLog(models.Model):
    referrer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='referrals_made',
                                  verbose_name="معرف")
    new_user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='referred_by',
                                     verbose_name="کاربر جدید")
    discount_code = models.ForeignKey('DiscountCode', on_delete=models.SET_NULL, null=True,
                                       blank=True, verbose_name="کد تخفیف")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "لاگ دعوت"
        verbose_name_plural = "لاگ‌های دعوت"

    def __str__(self):
        return f"{self.referrer.username} -> {self.new_user.username}"


# ==================== کد تخفیف ====================

class DiscountCode(models.Model):
    DISCOUNT_TYPE_CHOICES = [
        ('percentage', 'درصدی'),
        ('fixed', 'ثابت'),
    ]

    code = models.CharField(max_length=50, unique=True, verbose_name="کد تخفیف")
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="کاربر")
    discount_type = models.CharField(max_length=10, choices=DISCOUNT_TYPE_CHOICES,
                                      default='percentage', verbose_name="نوع تخفیف")
    amount = models.DecimalField(max_digits=8, decimal_places=2, default=5.00,
                                  verbose_name="مبلغ/درصد تخفیف")
    is_used = models.BooleanField(default=False, verbose_name="استفاده شده")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(verbose_name="تاریخ انقضا")

    def __str__(self):
        return f"{self.code} - {self.user.username}"

    def apply_discount(self, total_amount):
        if self.discount_type == 'percentage':
            discount_amount = (total_amount * self.amount) / 100
        else:
            discount_amount = self.amount
        return max(total_amount - discount_amount, 0)


# ==================== سبد خرید ====================

class Cart(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='cart')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"سبد خرید {self.user.username}"

    def total_price(self):
        return sum(item.total_price() for item in self.items.all())

    def total_quantity(self):
        return sum(item.quantity for item in self.items.all())


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    def total_price(self):
        return self.product.price * self.quantity

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"


# ==================== سفارش ====================

class Order(models.Model):
    STATUS_CHOICES = [
        ('draft', 'پیش‌نویس (تکمیل نشده)'),
        ('pending', 'در انتظار پرداخت'),
        ('paid', 'پرداخت شده'),
        ('completed', 'تکمیل شده'),
        ('cancelled', 'لغو شده'),
    ]

    order_number = models.CharField(max_length=30, unique=True, blank=True, verbose_name="شماره سفارش")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE)
    total_amount = models.DecimalField(max_digits=10, decimal_places=0, verbose_name="مبلغ کل")
    discount_code = models.ForeignKey(DiscountCode, on_delete=models.SET_NULL, null=True,
                                       blank=True, verbose_name="کد تخفیف")
    final_amount = models.DecimalField(max_digits=10, decimal_places=0, verbose_name="مبلغ نهایی")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft',
                               verbose_name="وضعیت")
    price_locked_until = models.DateTimeField(null=True, blank=True, editable=False)

    full_name = models.CharField(max_length=100, blank=True, verbose_name="نام و نام خانوادگی گیرنده")
    phone = models.CharField(max_length=15, blank=True, verbose_name="شماره تماس")
    address = models.TextField(blank=True, verbose_name="آدرس کامل")
    postal_code = models.CharField(max_length=20, blank=True, verbose_name="کد پستی")

    # روش دریافت و خریدار (اگر برای شخص دیگری ارسال شود، full_name/phone بالا مشخصات «گیرنده» است)
    DELIVERY_CHOICES = [
        ('pickup', 'دریافت حضوری'),
        ('tipax', 'ارسال با تیپاکس'),
        ('irex', 'ارسال با ایرکس'),
    ]
    delivery_method = models.CharField(max_length=10, choices=DELIVERY_CHOICES, default='pickup',
                                       verbose_name="روش دریافت")
    send_to_other = models.BooleanField(default=False, verbose_name="ارسال برای شخص دیگر")
    buyer_name = models.CharField(max_length=100, blank=True, verbose_name="نام خریدار")
    buyer_phone = models.CharField(max_length=15, blank=True, verbose_name="تلفن خریدار")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_shipping(self):
        return self.delivery_method in ('tipax', 'irex')

    def save(self, *args, **kwargs):
        if not self.order_number and self.status != 'draft':
            self.order_number = f"ORD-{timezone_now_str()}-{uuid.uuid4().hex[:8].upper()}"
        if not self.final_amount:
            if self.discount_code:
                self.final_amount = self.discount_code.apply_discount(self.total_amount)
            else:
                self.final_amount = self.total_amount
        super().save(*args, **kwargs)

    def __str__(self):
        if self.order_number:
            return f"سفارش {self.order_number} - {self.user.username}"
        return f"سفارش ناتمام {self.user.username} - {self.created_at}"

    class Meta:
        verbose_name = "سفارش"
        verbose_name_plural = "سفارشات"


# ==================== رسید پرداخت ====================

class PaymentReceipt(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='receipt')
    receipt_image = models.ImageField(upload_to='receipts/', verbose_name="تصویر رسید پرداخت")
    payment_method = models.CharField(
        max_length=20,
        choices=[('card', 'کارت به کارت'), ('shaba', 'شماره شبا')],
        default='card',
        verbose_name="روش پرداخت"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"رسید پرداخت برای سفارش {self.order.order_number}"


# ==================== چت ====================

class ChatMessage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_messages')
    message = models.TextField(verbose_name="پیام", blank=True, null=True)
    image = models.ImageField(upload_to='chat/images/', verbose_name="عکس", blank=True, null=True)
    video = models.FileField(upload_to='chat/videos/', verbose_name="فیلم", blank=True, null=True)
    is_admin = models.BooleanField(default=False, verbose_name="پیام از ادمین")
    is_read = models.BooleanField(default=False, verbose_name="خوانده شده")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = "پیام چت"
        verbose_name_plural = "پیام‌های چت"

    def __str__(self):
        return f"{self.user.username} - {self.created_at}"


# ==================== گالری ====================

class GalleryItem(models.Model):
    ITEM_TYPES = [
        ('image', 'عکس'),
        ('video', 'ویدیو'),
    ]

    title = models.CharField(max_length=200, verbose_name="عنوان", blank=True)
    item_type = models.CharField(max_length=10, choices=ITEM_TYPES, default='image',
                                  verbose_name="نوع")
    image = models.ImageField(upload_to='gallery/images/', blank=True, null=True,
                               verbose_name="عکس")
    video_file = models.FileField(upload_to='gallery/videos/', blank=True, null=True,
                                   verbose_name="فایل ویدیو")
    thumbnail = models.ImageField(upload_to='gallery/thumbnails/', null=True, blank=True,
                                   verbose_name="بندانگشتی")
    description = models.TextField(blank=True, verbose_name="توضیحات")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True, verbose_name="فعال")

    class Meta:
        verbose_name = "آیتم گالری"
        verbose_name_plural = "گالری"
        ordering = ['-created_at']

    def __str__(self):
        return self.title or f"آیتم گالری {self.id}"


# ==================== جشنواره‌ها ====================

class Festival(models.Model):
    title = models.CharField(max_length=200, verbose_name="عنوان جشنواره")
    content = models.TextField(verbose_name="محتوا")
    image = models.ImageField(upload_to='festivals/', blank=True, null=True, verbose_name="تصویر")
    slug = models.SlugField(unique=True, blank=True, verbose_name="اسلاگ")
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    views = models.PositiveIntegerField(default=0, verbose_name="تعداد بازدید")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title, allow_unicode=True) or 'festival'
            slug = base_slug
            counter = 1
            while Festival.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('shop:festival_detail', kwargs={'slug': self.slug})

    class Meta:
        verbose_name = "جشنواره"
        verbose_name_plural = "جشنواره‌ها"
        ordering = ['-created_at']

    def __str__(self):
        return self.title


# ==================== اسلایدر ====================

class Slider(models.Model):
    image = models.ImageField(upload_to='slider/', verbose_name="تصویر اسلاید")
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "اسلایدر"
        verbose_name_plural = "اسلایدرها"
        ordering = ['-created_at']

    def __str__(self):
        return f"اسلاید {self.id}"


# ==================== درباره ما ====================

class AboutUs(models.Model):
    title = models.CharField(max_length=200, default="درباره ما", verbose_name="عنوان")
    content = models.TextField(verbose_name="متن درباره ما")
    image = models.ImageField(upload_to='about/', blank=True, null=True, verbose_name="تصویر")
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "درباره ما"
        verbose_name_plural = "درباره ما"

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.is_active:
            AboutUs.objects.filter(is_active=True).exclude(id=self.id).update(is_active=False)
        super().save(*args, **kwargs)


# ==================== محاسبه‌ی خودکار قیمت ====================
#
# منطق: قیمت‌های تابلوی شما نقطه‌ی شروع‌اند (۹۹۵ = ۴۷۰٬۰۰۰ تومان بر گرم و ...).
# قیمت جهانی انس نقره/مس اولین بار که دریافت شود «مرجع» ثبت می‌شود؛ از آن به بعد هر تغییر
# درصدیِ انس جهانی به همان نسبت روی قیمت پایه اعمال می‌شود. بعد درصد سود وزنی اضافه می‌شود.
# همه‌ی اعداد از settings.py قابل تغییرند (نام‌ها در _cfg) و چیزی به ادمین اضافه نمی‌شود.

logger = logging.getLogger(__name__)
D = Decimal
TROY_OUNCE_GRAMS = D('31.1034768')

DEFAULT_TIERS = [(1000, 4.5), (500, 4.5), (250, 6), (100, 8), (50, 8), (31.1035, 10), (20, 12)]


def _cfg(name, default):
    return getattr(dj_settings, name, default)


def metal_of(purity):
    return 'copper' if str(purity) == '99.99' else 'silver'


def base_gram_price(ps, purity):
    """قیمت پایه‌ی هر گرم (تومان) برای این عیار، هم‌تراز با انس جهانی روز."""
    purity = str(purity)
    if purity == '99.99':
        # مس: تابلو ۱۰۰۰ گرم = ۴٬۵۰۰٬۰۰۰ با ۴.۵٪ سود وزنی  ->  پایه = ۴٬۵۰۰٬۰۰۰ / ۱.۰۴۵ / ۱۰۰۰
        base = D(str(_cfg('PRICE_BASE_COPPER', D(4500000) / D('1.045') / 1000)))
        cur, ref = ps.copper_usd_per_oz, ps.ref_copper_oz
    else:
        base = D(str(_cfg('PRICE_BASE_999_9' if purity == '999.9' else 'PRICE_BASE_995',
                          480000 if purity == '999.9' else 470000)))
        cur, ref = ps.silver_usd_per_oz, ps.ref_silver_oz
    if cur and ref:
        base = base * D(cur) / D(ref)
    return base


def tier_markup_percent(weight):
    tiers = sorted(((D(str(w)), D(str(p))) for w, p in _cfg('PRICE_TIERS', DEFAULT_TIERS)))
    chosen = tiers[0][1]
    for min_w, pct in tiers:
        if weight >= min_w:
            chosen = pct
    return chosen


def calculate_price(ps, purity, weight, shot=False):
    """
    ساچمه: وزن (گرم) × قیمت لحظه‌ایِ هر گرم (از انس جهانی)، رُند به تومان، بدون درصد سود.
    شمش: قیمت هر گرم × وزن × (۱ + درصد سود پلکانی وزنی)، رُند به پایین (۱۰۰ هزار/۱ هزار).
    """
    weight = D(weight or 0)
    if weight <= 0:
        return None
    gram = base_gram_price(ps, purity)
    if shot:
        pct = D(str(_cfg('PRICE_SHOT_MARKUP', 0)))
        return (gram * weight * (1 + pct / 100)).quantize(D('1'), rounding=ROUND_HALF_UP)
    pct = tier_markup_percent(weight)
    price = (gram * weight * (1 + pct / 100)).quantize(D('1'), rounding=ROUND_HALF_UP)
    big = price >= _cfg('PRICE_ROUND_THRESHOLD', 10000000)
    step = D(_cfg('PRICE_ROUND_LARGE', 100000) if big else _cfg('PRICE_ROUND_SMALL', 1000))
    return (price / step).to_integral_value(rounding=ROUND_FLOOR) * step


def recalculate_all_products(ps=None):
    ps = ps or PriceSettings.get()
    changed = []
    for p in Product.objects.all():
        new = calculate_price(ps, p.purity, p.weight_grams, p.kind == 'shot')
        if new is not None and new != p.price:
            p.price = new
            changed.append(p)
    if changed:
        Product.objects.bulk_update(changed, ['price'], batch_size=500)
    return len(changed)


POUND_IN_TROY_OUNCES = D('453.59237') / TROY_OUNCE_GRAMS  # ≈ 14.5833


def fetch_world_prices():
    """
    قیمت جهانی نقره و مس بدون نیاز به کلید API، از api.gold-api.com:
        XAG = نقره (دلار بر تروی‌اونس)
        HG  = مس COMEX (دلار بر پوند) -> به دلار بر اونس تبدیل می‌شود
    اگر سرویس دیگری با همان فرمت خواستید: METAL_PRICE_API_URL در settings.py.
    """
    base = _cfg('METAL_PRICE_API_URL', 'https://api.gold-api.com/price').rstrip('/')

    def get(symbol):
        r = requests.get(f'{base}/{symbol}', timeout=8)
        r.raise_for_status()
        price = D(str(r.json()['price']))
        if price <= 0:
            raise ValueError(f'قیمت نامعتبر برای {symbol}')
        return price

    silver_oz = get('XAG')
    copper_lb = get('HG')
    return silver_oz, copper_lb / POUND_IN_TROY_OUNCES


def refresh_prices_if_stale():
    """هر PRICE_REFRESH_SECONDS (پیش‌فرض ۳۰) حداکثر یک بار از API می‌گیرد (قفل اتمیک دیتابیس)."""
    ps = PriceSettings.get()
    now = timezone.now()
    cutoff = now - timedelta(seconds=_cfg('PRICE_REFRESH_SECONDS', 30))
    won = PriceSettings.objects.filter(pk=ps.pk).filter(
        Q(last_attempt__isnull=True) | Q(last_attempt__lt=cutoff)
    ).update(last_attempt=now)
    if not won:
        return ps
    try:
        silver, copper = fetch_world_prices()
        with transaction.atomic():
            fields = {'silver_usd_per_oz': silver, 'copper_usd_per_oz': copper,
                      'last_updated': timezone.now(), 'last_error': ''}
            if ps.ref_silver_oz is None:
                fields['ref_silver_oz'] = silver
            if ps.ref_copper_oz is None:
                fields['ref_copper_oz'] = copper
            PriceSettings.objects.filter(pk=ps.pk).update(**fields)
            ps = PriceSettings.get()
            PriceSnapshot.objects.create(silver_usd_per_oz=silver, copper_usd_per_oz=copper)
            if random.random() < 0.01:
                PriceSnapshot.objects.filter(created_at__lt=timezone.now() - timedelta(days=7)).delete()
            recalculate_all_products(ps)
    except Exception as e:
        logger.exception('world price refresh failed')
        PriceSettings.objects.filter(pk=ps.pk).update(last_error=str(e)[:500])
        ps = PriceSettings.get()
    return ps