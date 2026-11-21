import logging
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

from .social import media_kind, CAPTION_LIMIT, TEXT_LIMIT, MAX_IMAGE_BYTES, MAX_VIDEO_BYTES


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

    img_shot = models.ImageField(upload_to='sections/', blank=True, null=True, verbose_name="عکس دسته ساچمه")
    img_copper_bar = models.ImageField(upload_to='sections/', blank=True, null=True, verbose_name="عکس دسته مس")
    img_silver_bar = models.ImageField(upload_to='sections/', blank=True, null=True, verbose_name="عکس دسته شمش نقره")
    img_turquoise = models.ImageField(upload_to='sections/', blank=True, null=True, verbose_name="عکس دسته فیروزه")

    address_line1 = models.CharField(max_length=200, default="", verbose_name="آدرس خط ۱")
    address_line2 = models.CharField(max_length=200, default="", blank=True, verbose_name="آدرس خط ۲")
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

    shipping_cost_tipax = models.PositiveIntegerField(
        default=0, verbose_name="هزینه ارسال با تیپاکس (تومان)",
        help_text="در مرحله‌ی پرداخت به مبلغ سفارش اضافه می‌شود. ۰ یعنی رایگان / پس‌کرایه."
    )
    shipping_cost_irex = models.PositiveIntegerField(
        default=0, verbose_name="هزینه ارسال با ایرکس (تومان)",
        help_text="در مرحله‌ی پرداخت به مبلغ سفارش اضافه می‌شود. ۰ یعنی رایگان / پس‌کرایه."
    )

    # ---- دریافت خودکار نرخ از وب‌سرویس زربها داده‌گستر ----
    zarbaha_enabled = models.BooleanField(default=False, verbose_name="دریافت خودکار نرخ از زربها فعال باشد")
    zarbaha_username = models.CharField(max_length=100, blank=True, default="", verbose_name="نام کاربری زربها")
    zarbaha_password = models.CharField(max_length=100, blank=True, default="", verbose_name="رمز عبور زربها")
    zarbaha_interval_minutes = models.PositiveIntegerField(
        default=5, verbose_name="فاصله‌ی دریافت نرخ (دقیقه)",
        help_text="طبق قوانین زربها کمتر از ۵ دقیقه مجاز نیست؛ عدد کمتر از ۵ خودکار ۵ حساب می‌شود.")
    zarbaha_multiplier = models.DecimalField(
        max_digits=10, decimal_places=4, default=1, verbose_name="ضریب تبدیل نرخ به تومان",
        help_text="اگر زربها نرخ را به‌صورت «هزار تومان» می‌دهد ۱۰۰۰ بگذارید؛ اگر تومان می‌دهد ۱.")

    zarbaha_key_shot_995 = models.CharField(max_length=60, blank=True, default="", verbose_name="ساچمه ۹۹۵ — هر گرم")
    zarbaha_key_shot_9999 = models.CharField(max_length=60, blank=True, default="", verbose_name="ساچمه ۹۹۹.۹ — هر گرم")
    zarbaha_key_silver_bar_1000 = models.CharField(max_length=60, blank=True, default="", verbose_name="شمش نقره ۱۰۰۰ گرمی")
    zarbaha_key_silver_bar_500 = models.CharField(max_length=60, blank=True, default="", verbose_name="شمش نقره ۵۰۰ گرمی")
    zarbaha_key_silver_bar_100 = models.CharField(max_length=60, blank=True, default="", verbose_name="شمش نقره ۱۰۰ گرمی")
    zarbaha_key_silver_bar_50 = models.CharField(max_length=60, blank=True, default="", verbose_name="شمش نقره ۵۰ گرمی")
    zarbaha_key_copper_bar_1000 = models.CharField(max_length=60, blank=True, default="", verbose_name="شمش مس ۱۰۰۰ گرمی")
    zarbaha_key_copper_bar_500 = models.CharField(max_length=60, blank=True, default="", verbose_name="شمش مس ۵۰۰ گرمی")
    zarbaha_key_copper_bar_100 = models.CharField(max_length=60, blank=True, default="", verbose_name="شمش مس ۱۰۰ گرمی")
    zarbaha_key_copper_bar_50 = models.CharField(max_length=60, blank=True, default="", verbose_name="شمش مس ۵۰ گرمی")

    # وضعیت داخلی (در فرم ادمین نمایش داده نمی‌شود یا فقط‌خواندنی است)
    zarbaha_token = models.TextField(blank=True, default="", editable=False)
    zarbaha_token_at = models.DateTimeField(null=True, blank=True, editable=False)
    zarbaha_last_attempt = models.DateTimeField(null=True, blank=True, editable=False)
    zarbaha_last_status = models.CharField(max_length=300, blank=True, default="", editable=False)
    zarbaha_last_data = models.TextField(blank=True, default="", editable=False)

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


# ==================== بخش‌های فروشگاه ====================
#
# چهار بخش: ساچمه، شمش نقره، شمش مس، سنگ فیروزه. همه روی همان جدول Product ذخیره می‌شوند
# (تا سبد خرید و سفارش‌ها دست نخورند) و در ادمین هر کدام یک «مدل پروکسی» جدا دارند.

PRODUCT_SECTIONS = [
    ('shot', 'ساچمه'),
    ('silver-bar', 'شمش نقره'),
    ('copper-bar', 'شمش مس'),
    ('turquoise', 'سنگ فیروزه'),
]
SECTION_LABELS = dict(PRODUCT_SECTIONS)
SECTION_FILTERS = {
    'shot': Q(kind='shot'),
    'silver-bar': Q(kind='bar') & ~Q(purity='99.99'),
    'copper-bar': Q(kind='bar', purity='99.99'),
    'turquoise': Q(kind='turquoise'),
}

BAR_WEIGHTS = [
    ('1000', '1000 گرم'),
    ('500', '500 گرم'),
    ('100', '100 گرم'),
    ('50', '50 گرم'),
]
SILVER_BAR_WEIGHTS = BAR_WEIGHTS
COPPER_BAR_WEIGHTS = BAR_WEIGHTS


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
        choices=[('bar', 'شمش'), ('shot', 'ساچمه'), ('turquoise', 'فیروزه')],
        default='bar',
        verbose_name="نوع",
        editable=False,
    )
    price = models.DecimalField(max_digits=14, decimal_places=0, default=0, verbose_name="قیمت (خودکار)")

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
        if self.kind == 'turquoise':
            return 'turquoise'
        return 'copper-bar' if str(self.purity) == '99.99' else 'silver-bar'

    @property
    def section_label(self):
        return SECTION_LABELS[self.section_key]

    @property
    def main_image(self):
        imgs = list(self.images.all())
        return imgs[0].image if imgs else None

    @property
    def in_stock(self):
        return self.stock > 0

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.weight_grams is None or Decimal(self.weight_grams) <= 0:
            raise ValidationError({'weight_grams': 'وزن باید بیشتر از صفر باشد.'})

    def compute_price(self, ps=None):
        return calculate_price(ps or PriceSettings.get(), self.purity, self.weight_grams,
                               self.kind == 'shot')

    def auto_name(self):
        if self.kind == 'shot':
            return f"ساچمه نقره {self.purity} - {self.weight_display()}"
        if self.kind == 'turquoise':
            return f"سنگ فیروزه - {self.weight_display()}"
        metal = 'مس' if str(self.purity) == '99.99' else f"نقره {self.purity}"
        return f"شمش {metal} - {self.weight_display()}"

    def save(self, *args, **kwargs):
        if not (self.name or '').strip():
            self.name = self.auto_name()
        if self.kind == 'turquoise':
            # فیروزه قیمت دستی دارد؛ از PriceSettings حساب نمی‌شود.
            self.price = self.price or 0
        else:
            # قیمت دستی نیست: همیشه از «قیمت‌ها» (ساچمه هر گرم / شمش قیمت هر وزن) حساب می‌شود
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
        self.kind = 'shot'

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
    """شمش نقره — همیشه عیار 999.9، فقط وزن‌های مجاز؛ قیمت هر وزن در «قیمت‌ها» وارد می‌شود."""
    class Meta:
        proxy = True
        verbose_name = "شمش نقره"
        verbose_name_plural = "شمش‌های نقره"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.kind = 'bar'
        self.purity = '999.9'

    def clean(self):
        from django.core.exceptions import ValidationError
        super().clean()
        allowed = [Decimal(v) for v, _ in SILVER_BAR_WEIGHTS]
        if Decimal(self.weight_grams) not in allowed:
            raise ValidationError({'weight_grams': 'وزن شمش نقره فقط می‌تواند 1000، 500، 100 یا 50 گرم باشد.'})

    def save(self, *args, **kwargs):
        self.kind = 'bar'
        self.purity = '999.9'
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

    def clean(self):
        from django.core.exceptions import ValidationError
        super().clean()
        allowed = [Decimal(v) for v, _ in COPPER_BAR_WEIGHTS]
        if Decimal(self.weight_grams) not in allowed:
            raise ValidationError({'weight_grams': 'وزن شمش مس فقط می‌تواند 1000، 500، 100 یا 50 گرم باشد.'})

    def save(self, *args, **kwargs):
        self.kind = 'bar'
        self.purity = '99.99'
        super().save(*args, **kwargs)


class TurquoiseProduct(Product):
    """سنگ فیروزه — قیمت دستی، وزن آزاد، بدون عیار نقره/مس."""
    class Meta:
        proxy = True
        verbose_name = "سنگ فیروزه"
        verbose_name_plural = "سنگ‌های فیروزه"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.kind = 'turquoise'

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.weight_grams is None or Decimal(self.weight_grams) <= 0:
            raise ValidationError({'weight_grams': 'وزن باید بیشتر از صفر باشد.'})
        if not self.price or Decimal(self.price) <= 0:
            raise ValidationError({'price': 'قیمت فیروزه را دستی وارد کنید.'})

    def save(self, *args, **kwargs):
        self.kind = 'turquoise'
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


# ==================== قیمت‌ها ====================

class PriceSettings(models.Model):
    price_shot_995 = models.DecimalField(max_digits=14, decimal_places=0, default=465000, verbose_name="ساچمه عیار ۹۹۵ — قیمت هر گرم (تومان)")
    price_shot_9999 = models.DecimalField(max_digits=14, decimal_places=0, default=475000, verbose_name="ساچمه عیار ۹۹۹.۹ — قیمت هر گرم (تومان)")

    price_silver_bar_1000 = models.DecimalField(max_digits=14, decimal_places=0, default=486000000, verbose_name="شمش نقره ۱۰۰۰ گرمی (تومان)")
    price_silver_bar_500 = models.DecimalField(max_digits=14, decimal_places=0, default=243000000, verbose_name="شمش نقره ۵۰۰ گرمی (تومان)")
    price_silver_bar_100 = models.DecimalField(max_digits=14, decimal_places=0, default=48600000, verbose_name="شمش نقره ۱۰۰ گرمی (تومان)")
    price_silver_bar_50 = models.DecimalField(max_digits=14, decimal_places=0, default=24300000, verbose_name="شمش نقره ۵۰ گرمی (تومان)")

    price_copper_bar_1000 = models.DecimalField(max_digits=14, decimal_places=0, default=4500000, verbose_name="شمش مس ۱۰۰۰ گرمی (تومان)")
    price_copper_bar_500 = models.DecimalField(max_digits=14, decimal_places=0, default=2250000, verbose_name="شمش مس ۵۰۰ گرمی (تومان)")
    price_copper_bar_100 = models.DecimalField(max_digits=14, decimal_places=0, default=450000, verbose_name="شمش مس ۱۰۰ گرمی (تومان)")
    price_copper_bar_50 = models.DecimalField(max_digits=14, decimal_places=0, default=225000, verbose_name="شمش مس ۵۰ گرمی (تومان)")

    class Meta:
        verbose_name = "قیمت‌ها"
        verbose_name_plural = "قیمت‌ها"

    def save(self, *args, **kwargs):
        self.pk = 1
        self.last_updated = timezone.now()
        super().save(*args, **kwargs)
        recalculate_all_products(self)

    def __str__(self):
        return "قیمت‌ها"

    silver_usd_per_oz = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    copper_usd_per_oz = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
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
        return False


class PriceSnapshot(models.Model):
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
    total_amount = models.DecimalField(max_digits=14, decimal_places=0, verbose_name="مبلغ کل")
    discount_code = models.ForeignKey(DiscountCode, on_delete=models.SET_NULL, null=True,
                                       blank=True, verbose_name="کد تخفیف")
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=0, default=0, verbose_name="هزینه ارسال")
    final_amount = models.DecimalField(max_digits=14, decimal_places=0, verbose_name="مبلغ نهایی (با هزینه ارسال)")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft',
                               verbose_name="وضعیت")
    price_locked_until = models.DateTimeField(null=True, blank=True, editable=False)

    full_name = models.CharField(max_length=100, blank=True, verbose_name="نام و نام خانوادگی گیرنده")
    phone = models.CharField(max_length=15, blank=True, verbose_name="شماره تماس")
    address = models.TextField(blank=True, verbose_name="آدرس کامل")
    postal_code = models.CharField(max_length=20, blank=True, verbose_name="کد پستی")

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
        if self.status == 'draft':
            if not self.order_number:
                self.order_number = f"DRF-{uuid.uuid4().hex[:12].upper()}"
        elif not self.order_number or self.order_number.startswith('DRF-'):
            self.order_number = f"ORD-{timezone_now_str()}-{uuid.uuid4().hex[:8].upper()}"
        if not self.final_amount:
            base = self.discount_code.apply_discount(self.total_amount) if self.discount_code else self.total_amount
            self.final_amount = base + (self.shipping_cost or 0)
        super().save(*args, **kwargs)

    def __str__(self):
        if self.order_number:
            return f"سفارش {self.order_number} - {self.user.username}"
        return f"سفارش ناتمام {self.user.username} - {self.created_at}"

    class Meta:
        verbose_name = "سفارش"
        verbose_name_plural = "سفارشات"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items', verbose_name="سفارش")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="محصول")
    name = models.CharField(max_length=100, verbose_name="نام")
    weight_label = models.CharField(max_length=50, blank=True, verbose_name="وزن")
    unit_price = models.DecimalField(max_digits=14, decimal_places=0, verbose_name="قیمت واحد")
    quantity = models.PositiveIntegerField(default=1, verbose_name="تعداد")

    class Meta:
        verbose_name = "قلم سفارش"
        verbose_name_plural = "اقلام سفارش"

    def total_price(self):
        return self.unit_price * self.quantity

    def __str__(self):
        return f"{self.quantity} × {self.name}"


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


# ==================== تحلیل نقره ====================

class SilverAnalysis(models.Model):
    title = models.CharField(max_length=200, verbose_name="عنوان تحلیل")
    slug = models.SlugField(unique=True, blank=True, verbose_name="اسلاگ")
    intro = models.TextField(blank=True, verbose_name="خلاصه/مقدمه")
    image = models.ImageField(upload_to='silver_analysis/', blank=True, null=True, verbose_name="تصویر اصلی")
    video = models.FileField(upload_to='silver_analysis/videos/', blank=True, null=True, verbose_name="ویدیو")
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    order = models.PositiveIntegerField(default=0, verbose_name="ترتیب نمایش")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "تحلیل نقره"
        verbose_name_plural = "تحلیل‌های نقره"
        ordering = ['order', '-created_at']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title, allow_unicode=True) or 'analysis'
            s, i = base, 1
            while SilverAnalysis.objects.filter(slug=s).exists():
                s = f"{base}-{i}"
                i += 1
            self.slug = s
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('shop:silver_analysis_detail', kwargs={'slug': self.slug})


class SilverAnalysisBlock(models.Model):
    MEDIA_CHOICES = [('text', 'متن'), ('image', 'عکس'), ('video', 'ویدیو')]

    analysis = models.ForeignKey(SilverAnalysis, on_delete=models.CASCADE,
                                 related_name='blocks', verbose_name="تحلیل")
    kind = models.CharField(max_length=10, choices=MEDIA_CHOICES, default='text', verbose_name="نوع")
    text = models.TextField(blank=True, verbose_name="متن")
    file = models.FileField(upload_to='silver_analysis/blocks/', blank=True, null=True, verbose_name="فایل")
    caption = models.CharField(max_length=300, blank=True, verbose_name="زیرنویس")
    order = models.PositiveIntegerField(default=0, verbose_name="ترتیب")

    class Meta:
        ordering = ['order', 'id']
        verbose_name = "بلوک تحلیل"
        verbose_name_plural = "بلوک‌های تحلیل (متن/عکس/ویدیو — هر تعداد)"

    def __str__(self):
        return f"{self.get_kind_display()} #{self.pk}"


# ==================== محاسبه‌ی خودکار قیمت ====================

logger = logging.getLogger(__name__)
D = Decimal
TROY_OUNCE_GRAMS = D('31.1034768')


def _cfg(name, default):
    return getattr(dj_settings, name, default)


def metal_of(purity):
    return 'copper' if str(purity) == '99.99' else 'silver'


def bar_price_field(purity, weight):
    w = D(weight or 0)
    if w != w.to_integral_value():
        return None
    name = f"price_{metal_of(purity)}_bar_{int(w)}"
    return name if hasattr(PriceSettings, name) else None


def calculate_price(ps, purity, weight, shot=False):
    weight = D(weight or 0)
    if weight <= 0:
        return None
    if shot:
        gram = D(ps.price_shot_9999 if str(purity) == '999.9' else ps.price_shot_995)
        return (gram * weight).quantize(D('1'), rounding=ROUND_HALF_UP)
    field = bar_price_field(purity, weight)
    if not field:
        return None
    return D(getattr(ps, field)).quantize(D('1'), rounding=ROUND_HALF_UP)


def recalculate_all_products(ps=None):
    ps = ps or PriceSettings.get()
    changed = []
    for p in Product.objects.exclude(kind='turquoise'):
        new = calculate_price(ps, p.purity, p.weight_grams, p.kind == 'shot')
        if new is not None and new != p.price:
            p.price = new
            changed.append(p)
    if changed:
        Product.objects.bulk_update(changed, ['price'], batch_size=500)
    return len(changed)


# ---------- دریافت نرخ از زربها داده‌گستر (Web API نسخه ۲) ----------

ZARBAHA_AUTH_URL = 'https://web.zarbaha-co.ir/api/authentication'
ZARBAHA_PRICE_URL = 'https://web.zarbaha-co.ir/api/Price_V2'
ZARBAHA_MIN_MINUTES = 5          # حداقل فاصله‌ی مجاز بین دو درخواست نرخ
ZARBAHA_TOKEN_MINUTES = 50       # توکن ۱ ساعت اعتبار دارد؛ قبل از پایان تازه می‌شود
ZARBAHA_ERRORS = {
    2: 'درخواست زود ارسال شده (فاصله‌ی مجاز ۵ دقیقه است)',
    4: 'اکانت بلاک شده؛ احتمالاً IP سرور عوض شده، با پشتیبانی زربها تماس بگیرید',
    5: 'اکانت بلاک است؛ با پشتیبانی زربها تماس بگیرید',
    6: 'IP سرور با IP ثبت‌شده در زربها یکی نیست',
    8: 'سرویس دریافت نرخ برای این اکانت فعال نیست؛ با پشتیبانی زربها تماس بگیرید',
}
# فیلد قیمت در PriceSettings  ←  فیلد «نام نرخ در زربها» در SiteSettings
ZARBAHA_KEY_MAP = [
    ('price_shot_995', 'zarbaha_key_shot_995'),
    ('price_shot_9999', 'zarbaha_key_shot_9999'),
    ('price_silver_bar_1000', 'zarbaha_key_silver_bar_1000'),
    ('price_silver_bar_500', 'zarbaha_key_silver_bar_500'),
    ('price_silver_bar_100', 'zarbaha_key_silver_bar_100'),
    ('price_silver_bar_50', 'zarbaha_key_silver_bar_50'),
    ('price_copper_bar_1000', 'zarbaha_key_copper_bar_1000'),
    ('price_copper_bar_500', 'zarbaha_key_copper_bar_500'),
    ('price_copper_bar_100', 'zarbaha_key_copper_bar_100'),
    ('price_copper_bar_50', 'zarbaha_key_copper_bar_50'),
]
_ZB_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


class ZarbahaError(Exception):
    pass


def _zb_number(value):
    """'2,300,000' / '۲٬۳۰۰٬۰۰۰' → Decimal  (نامعتبر → None)"""
    s = str(value).strip().translate(_ZB_DIGITS)
    for ch in (',', '٬', '،', ' '):
        s = s.replace(ch, '')
    try:
        return D(s)
    except Exception:
        return None


def _zb_rows(data):
    """هر دو فرمت خروجی (لیست Title/Value یا شیء با فیلد ثابت) را به dict تبدیل می‌کند."""
    if isinstance(data, list):
        return {str(i.get('Title')): i.get('Value') for i in data if isinstance(i, dict) and i.get('Title')}
    if isinstance(data, dict):
        return {str(k): v for k, v in data.items()}
    return {}


def apply_zarbaha_data(ss, rows):
    """نرخ‌های دریافت‌شده را طبق نگاشت ادمین در PriceSettings می‌نویسد؛ تعداد نرخ‌های تغییرکرده را برمی‌گرداند."""
    lowered = {k.strip().lower(): v for k, v in rows.items()}
    mult = D(ss.zarbaha_multiplier or 1)
    ps = PriceSettings.get()
    changed = 0
    for price_field, key_field in ZARBAHA_KEY_MAP:
        key = (getattr(ss, key_field, '') or '').strip().lower()
        if not key or key not in lowered:
            continue
        num = _zb_number(lowered[key])
        if num is None or num <= 0:
            continue
        new = (num * mult).quantize(D('1'), rounding=ROUND_HALF_UP)
        if D(getattr(ps, price_field)) != new:
            setattr(ps, price_field, new)
            changed += 1
    if changed:
        ps.save()          # save() خودش قیمت همه‌ی محصولات را دوباره حساب می‌کند
    return changed


def _zb_token(ss, requests, fresh=False):
    now = timezone.now()
    if (not fresh and ss.zarbaha_token and ss.zarbaha_token_at
            and now - ss.zarbaha_token_at < timedelta(minutes=ZARBAHA_TOKEN_MINUTES)):
        return ss.zarbaha_token
    r = requests.post(ZARBAHA_AUTH_URL, json={'UserName': ss.zarbaha_username, 'Password': ss.zarbaha_password},
                      timeout=10)
    j = r.json()
    if j.get('StatusCode') == 200 and j.get('Value'):
        ss.zarbaha_token, ss.zarbaha_token_at = j['Value'], now
        SiteSettings.objects.filter(pk=ss.pk).update(zarbaha_token=ss.zarbaha_token, zarbaha_token_at=now)
        return ss.zarbaha_token
    if j.get('StatusCode') == 401:
        raise ZarbahaError('نام کاربری یا رمز عبور زربها اشتباه است')
    raise ZarbahaError(f"دریافت توکن ناموفق بود (کد {j.get('StatusCode')})")


def refresh_zarbaha_rates(ss=None):
    """
    اگر دریافت از زربها فعال باشد و فاصله‌ی مجاز گذشته باشد نرخ‌ها را می‌گیرد و قیمت‌ها را به‌روز می‌کند.
    خروجی: (True|False|None, پیام) — None یعنی کاری انجام نشد (غیرفعال یا هنوز زود است).
    """
    ss = ss or SiteSettings.objects.first()
    if not ss or not ss.zarbaha_enabled or not ss.zarbaha_username or not ss.zarbaha_password:
        return None, ''

    now = timezone.now()
    gap = timedelta(minutes=max(ZARBAHA_MIN_MINUTES, ss.zarbaha_interval_minutes or 0))
    # فقط یک پردازش اجازه‌ی درخواست دارد (رعایت محدودیت ۵ دقیقه‌ای حتی با چند کاربر هم‌زمان)
    claimed = SiteSettings.objects.filter(pk=ss.pk).filter(
        Q(zarbaha_last_attempt__isnull=True) | Q(zarbaha_last_attempt__lte=now - gap)
    ).update(zarbaha_last_attempt=now)
    if not claimed:
        return None, ''

    import requests
    stamp = timezone.localtime(now).strftime('%Y-%m-%d %H:%M')
    try:
        j = None
        for attempt in (0, 1):
            token = _zb_token(ss, requests, fresh=attempt == 1)
            r = requests.get(ZARBAHA_PRICE_URL, headers={'Authorization': f'Bearer {token}'}, timeout=10)
            if r.status_code == 401 and attempt == 0:
                continue                      # توکن منقضی شده؛ یک بار توکن تازه می‌گیریم
            j = r.json()
            break
        status = (j or {}).get('Status') or {}
        if status.get('code') != 1:
            code = status.get('code')
            raise ZarbahaError(ZARBAHA_ERRORS.get(code) or status.get('message') or f'خطای ناشناخته (کد {code})')
        rows = _zb_rows(j.get('Data'))
        if not rows:
            raise ZarbahaError('پاسخ زربها خالی بود')
        import json
        changed = apply_zarbaha_data(ss, rows)
        msg = f'{stamp} — موفق؛ {len(rows)} نرخ دریافت شد، {changed} قیمت تغییر کرد'
        SiteSettings.objects.filter(pk=ss.pk).update(
            zarbaha_last_status=msg, zarbaha_last_data=json.dumps(rows, ensure_ascii=False))
        return True, msg
    except (ZarbahaError, requests.RequestException, ValueError) as e:
        msg = f'{stamp} — خطا: {e}'[:300]
        SiteSettings.objects.filter(pk=ss.pk).update(zarbaha_last_status=msg)
        logging.getLogger(__name__).warning('Zarbaha: %s', e)
        return False, msg


def refresh_prices_if_stale():
    try:
        refresh_zarbaha_rates()
    except Exception:
        logging.getLogger(__name__).exception('Zarbaha refresh failed')
    return PriceSettings.get()


# ==================== شبکه‌های اجتماعی ====================

class SocialChannel(models.Model):
    PLATFORM_CHOICES = [
        ('telegram', 'تلگرام'),
        ('bale', 'بله'),
        ('eitaa', 'ایتا'),
        ('rubika', 'روبیکا'),
    ]

    platform = models.CharField(max_length=10, choices=PLATFORM_CHOICES, default='telegram', verbose_name="پیام‌رسان")
    name = models.CharField(max_length=100, verbose_name="نام کانال", help_text="فقط برای تشخیص خودتان در پنل")
    bot_token = models.CharField(max_length=300, verbose_name="توکن ربات")
    chat_id = models.CharField(max_length=120, verbose_name="شناسه کانال")
    proxy_url = models.CharField(
        max_length=200, blank=True, verbose_name="پروکسی (اختیاری)",
        help_text="مثال: socks5h://127.0.0.1:1080 — برای سروری که به API تلگرام دسترسی مستقیم ندارد. "
                  "برای socks باید بسته‌ی PySocks نصب باشد (pip install requests[socks])."
    )
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    last_check_ok = models.BooleanField(null=True, blank=True, editable=False)
    last_check_message = models.CharField(max_length=300, blank=True, editable=False)
    last_check_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "کانال شبکه اجتماعی"
        verbose_name_plural = "کانال‌های شبکه‌های اجتماعی"
        ordering = ['platform', 'name']

    def __str__(self):
        return f"{self.get_platform_display()} - {self.name}"

    @property
    def masked_token(self):
        t = self.bot_token or ''
        return f"{t[:4]}…{t[-3:]}" if len(t) > 10 else '•••'


class SocialPost(models.Model):
    STATUS_CHOICES = [
        ('draft', 'ارسال نشده'),
        ('sending', 'در حال ارسال'),
        ('sent', 'ارسال شد'),
        ('partial', 'ارسال ناقص'),
        ('failed', 'ناموفق'),
    ]

    title = models.CharField(max_length=150, blank=True, verbose_name="عنوان (فقط برای خودتان)")
    text = models.TextField(
        blank=True, verbose_name="متن پیام",
        help_text="اگر فقط یک عکس/فیلم بدون توضیح اضافه کنید، این متن زیر همان قرار می‌گیرد؛ "
                  "در غیر این صورت اول متن جدا ارسال می‌شود و بعد هر عکس/فیلم با توضیح خودش."
    )
    channels = models.ManyToManyField(
        SocialChannel, blank=True, verbose_name="کانال‌ها",
        help_text="اگر هیچ‌کدام انتخاب نشود، پیام به همه‌ی کانال‌های فعال می‌رود."
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft', verbose_name="وضعیت")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='social_posts', verbose_name="ایجادکننده")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name="آخرین ارسال")

    class Meta:
        verbose_name = "پست شبکه‌های اجتماعی"
        verbose_name_plural = "پست‌های شبکه‌های اجتماعی"
        ordering = ['-created_at']

    def __str__(self):
        return self.title or (self.text[:40] + ('…' if len(self.text) > 40 else '')) or f"پست {self.pk}"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.text and len(self.text) > TEXT_LIMIT:
            raise ValidationError({'text': f'متن پیام حداکثر {TEXT_LIMIT} نویسه می‌تواند باشد.'})

    def target_channels(self):
        if self.channels.exists():
            return list(self.channels.filter(is_active=True))
        return list(SocialChannel.objects.filter(is_active=True))


class SocialPostMedia(models.Model):
    post = models.ForeignKey(SocialPost, on_delete=models.CASCADE, related_name='media', verbose_name="پست")
    file = models.FileField(upload_to='social/%Y/%m/', verbose_name="عکس / فیلم")
    caption = models.TextField(blank=True, verbose_name="توضیح زیر این فایل")
    order = models.PositiveIntegerField(default=0, verbose_name="ترتیب")

    class Meta:
        ordering = ['order', 'id']
        verbose_name = "عکس / فیلم"
        verbose_name_plural = "عکس‌ها و فیلم‌ها (هر کدام با توضیح خودش)"

    def __str__(self):
        return self.file.name.rsplit('/', 1)[-1] if self.file else f"رسانه {self.pk}"

    @property
    def media_type(self):
        return media_kind(self.file.name)

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.caption and len(self.caption) > CAPTION_LIMIT:
            raise ValidationError({'caption': f'توضیح هر فایل حداکثر {CAPTION_LIMIT} نویسه می‌تواند باشد.'})
        if self.file:
            try:
                size = self.file.size
            except Exception:
                return
            kind = self.media_type
            if kind == 'image' and size > MAX_IMAGE_BYTES:
                raise ValidationError({'file': 'حجم عکس نباید بیشتر از ۱۰ مگابایت باشد.'})
            if kind != 'image' and size > MAX_VIDEO_BYTES:
                raise ValidationError({'file': 'حجم فیلم/فایل نباید بیشتر از ۵۰ مگابایت باشد.'})


class SocialDelivery(models.Model):
    STATUS_CHOICES = [('ok', 'موفق'), ('partial', 'ناقص'), ('failed', 'ناموفق')]

    post = models.ForeignKey(SocialPost, on_delete=models.CASCADE, related_name='deliveries')
    channel = models.ForeignKey(SocialChannel, on_delete=models.CASCADE, related_name='deliveries', verbose_name="کانال")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='failed', verbose_name="نتیجه")
    sent_count = models.PositiveIntegerField(default=0, verbose_name="ارسال‌شده")
    total_count = models.PositiveIntegerField(default=0, verbose_name="کل موارد")
    detail = models.TextField(blank=True, verbose_name="جزئیات خطا")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="زمان")

    class Meta:
        unique_together = [('post', 'channel')]
        verbose_name = "نتیجه‌ی ارسال"
        verbose_name_plural = "نتیجه‌ی ارسال به کانال‌ها"

    def __str__(self):
        return f"{self.channel} - {self.get_status_display()}"