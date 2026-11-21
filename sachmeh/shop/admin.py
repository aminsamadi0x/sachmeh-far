from datetime import timedelta
from decimal import Decimal
from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.db import models as dj_models, transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.html import format_html, format_html_join, escape
from django.utils.safestring import mark_safe
from django.urls import reverse
import logging
from .models import *
from .phone import normalize_phone, PHONE_RE
from . import social

logger = logging.getLogger(__name__)


# ==================== Inline‌ها ====================

class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'پروفایل کاربر'
    fields = ['referral_code', 'credits', 'full_name', 'phone', 'address',
              'postal_code', 'created_at', 'updated_at']
    readonly_fields = ['referral_code', 'created_at', 'updated_at']
    extra = 0


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ['product', 'quantity', 'total_price']
    can_delete = False

    def total_price(self, obj):
        return f'{obj.total_price():,} تومان'
    total_price.short_description = 'قیمت کل'


class PaymentReceiptInline(admin.StackedInline):
    model = PaymentReceipt
    extra = 0
    readonly_fields = ['receipt_image', 'payment_method', 'uploaded_at']
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 3
    verbose_name = 'عکس'
    verbose_name_plural = 'عکس‌ها (هر چند تا خواستید)'
    fields = ['image', 'order']
    ordering = ['order']


# ==================== User ====================

class PhoneUserCreationForm(forms.ModelForm):
    phone = forms.CharField(label='شماره موبایل', max_length=20,
                            help_text='مثال: 09123456789 — کاربر با همین شماره وارد می‌شود.')
    password1 = forms.CharField(label='رمز عبور', strip=False, widget=forms.PasswordInput)
    password2 = forms.CharField(label='تکرار رمز عبور', strip=False, widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email')

    def clean_phone(self):
        phone = normalize_phone(self.cleaned_data.get('phone'))
        if not PHONE_RE.match(phone):
            raise forms.ValidationError('شماره موبایل باید با ۰۹ شروع شده و ۱۱ رقم باشد.')
        if User.objects.filter(username=phone).exists() or UserProfile.objects.filter(phone=phone).exists():
            raise forms.ValidationError('این شماره قبلاً ثبت شده است.')
        return phone

    def clean_password2(self):
        p1, p2 = self.cleaned_data.get('password1'), self.cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('دو رمز عبور یکسان نیستند.')
        return p2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data['phone']
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
        return user


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    fields = ['name', 'weight_label', 'unit_price', 'quantity']
    readonly_fields = ['name', 'weight_label', 'unit_price', 'quantity']

    def has_add_permission(self, request, obj=None):
        return False


class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)
    add_form = PhoneUserCreationForm
    list_display = ['phone_display', 'full_name_display', 'email', 'is_staff', 'is_active', 'date_joined']
    list_filter = ['is_staff', 'is_superuser', 'is_active', 'groups']
    search_fields = ['username', 'profile__phone', 'email', 'first_name', 'last_name']
    ordering = ['-date_joined']
    list_select_related = ['profile']

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('اطلاعات شخصی', {'fields': ('first_name', 'last_name', 'email')}),
        ('دسترسی‌ها', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('تاریخ‌ها', {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('phone', 'first_name', 'last_name', 'email', 'password1', 'password2'),
        }),
    )

    def get_inline_instances(self, request, obj=None):
        return super().get_inline_instances(request, obj) if obj else []

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if 'username' in form.base_fields:
            form.base_fields['username'].label = 'شناسه ورود'
            form.base_fields['username'].help_text = 'برای مشتریان همان شماره‌ی موبایل است. ادمین‌ها نام کاربری دلخواه دارند.'
        return form

    def phone_display(self, obj):
        profile = getattr(obj, 'profile', None)
        return (profile.phone if profile and profile.phone else '') or obj.username
    phone_display.short_description = 'شماره موبایل'
    phone_display.admin_order_field = 'profile__phone'

    def full_name_display(self, obj):
        return obj.get_full_name() or '—'
    full_name_display.short_description = 'نام'


# ==================== SiteSettings ====================

class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = ['site_name', 'updated_at']

    fieldsets = (
        ('اطلاعات عمومی سایت', {
            'fields': ('site_name', 'site_description', 'logo_text',
                       'background_image', 'background_overlay_opacity', 'background_fixed'),
        }),
        ('عکس دسته‌بندی‌های صفحه اول', {
            'fields': ('img_shot', 'img_copper_bar', 'img_silver_bar', 'img_turquoise'),
            'description': 'برای هر کدام از چهار دسته (ساچمه، مس، شمش نقره، فیروزه) یک عکس بگذارید؛ '
                           'در صفحه اول به‌جای تصویر پیش‌فرض نمایش داده می‌شود. '
                           'اگر عکسی نگذارید، آیکون SVG پیش‌فرض نمایش داده می‌شود.',
        }),
        ('آدرس فروشگاه', {
            'fields': ('address_line1', 'address_line2', 'address_city',
                       'address_state', 'address_postal_code'),
        }),
        ('اطلاعات تماس', {
            'fields': ('phone1', 'phone2', 'mobile', 'email'),
        }),
        ('شبکه‌های اجتماعی', {
            'fields': ('instagram', 'telegram', 'discord', 'whatsapp'),
        }),
        ('تنظیمات پرداخت', {
            'fields': ('min_amount_for_shaba', 'card_number', 'card_holder_name',
                       'shaba_number', 'bank_name'),
        }),
        ('هزینه ارسال', {
            'fields': ('shipping_cost_tipax', 'shipping_cost_irex'),
            'description': 'در مرحله‌ی پرداخت به مبلغ سفارش اضافه می‌شود (تخفیف روی آن اعمال نمی‌شود). '
                           'دریافت حضوری همیشه رایگان است. ۰ یعنی هزینه‌ای اضافه نشود.',
        }),
        ('دریافت خودکار نرخ از زربها داده‌گستر', {
            'fields': ('zarbaha_enabled', 'zarbaha_username', 'zarbaha_password',
                       'zarbaha_interval_minutes', 'zarbaha_multiplier', 'zarbaha_status_display'),
            'description': 'نام کاربری و رمز را پشتیبانی زربها می‌دهد. با فعال کردن و ذخیره، نرخ‌ها گرفته می‌شود '
                           'و نام همه‌ی نرخ‌هایی که زربها برای شما می‌فرستد پایین همین بخش نشان داده می‌شود؛ '
                           'همان نام‌ها را در بخش بعدی کنار هر قیمت بنویسید.',
        }),
        ('نام نرخ در زربها برای هر قیمت', {
            'fields': ('zarbaha_key_shot_995', 'zarbaha_key_shot_9999',
                       'zarbaha_key_silver_bar_1000', 'zarbaha_key_silver_bar_500',
                       'zarbaha_key_silver_bar_100', 'zarbaha_key_silver_bar_50',
                       'zarbaha_key_copper_bar_1000', 'zarbaha_key_copper_bar_500',
                       'zarbaha_key_copper_bar_100', 'zarbaha_key_copper_bar_50',
                       'zarbaha_rates_display'),
            'description': 'برای هر قیمت، نام دقیق نرخ در زربها را بنویسید (مثلاً Gram18). '
                           'خالی بگذارید تا آن قیمت همچنان دستی در بخش «قیمت‌ها» وارد شود. '
                           'قیمتی که اینجا نام دارد با هر دریافت، جایگزین مقدار دستی می‌شود.',
        }),
    )
    readonly_fields = ('zarbaha_status_display', 'zarbaha_rates_display')

    @admin.display(description='آخرین وضعیت دریافت')
    def zarbaha_status_display(self, obj):
        return obj.zarbaha_last_status or 'هنوز دریافتی انجام نشده'

    @admin.display(description='نرخ‌هایی که زربها فرستاده')
    def zarbaha_rates_display(self, obj):
        import json
        try:
            rows = json.loads(obj.zarbaha_last_data or '{}')
        except ValueError:
            rows = {}
        if not rows:
            return 'هنوز نرخی دریافت نشده'
        return format_html_join(mark_safe('<br>'), '<code dir="ltr">{}</code> = {}', rows.items())

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == 'zarbaha_password':
            kwargs['widget'] = forms.PasswordInput(render_value=True, attrs={'autocomplete': 'new-password'})
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if {'zarbaha_username', 'zarbaha_password'} & set(form.changed_data):
            # اکانت عوض شده: توکن قبلی بی‌اعتبار است و باید همین حالا یک بار نرخ گرفته شود
            obj.zarbaha_token, obj.zarbaha_token_at, obj.zarbaha_last_attempt = '', None, None
        super().save_model(request, obj, form, change)

        if not obj.zarbaha_enabled or not any(f.startswith('zarbaha_') for f in form.changed_data):
            return
        ok, msg = refresh_zarbaha_rates(obj)
        if ok is True:
            messages.success(request, f'زربها: {msg}')
        elif ok is False:
            messages.error(request, f'زربها: {msg}')
        else:
            # هنوز زود است (حداقل ۵ دقیقه بین دو درخواست)؛ اگر فقط نگاشت عوض شده، از آخرین نرخ‌های ذخیره‌شده استفاده می‌کنیم
            import json
            try:
                rows = json.loads(obj.zarbaha_last_data or '{}')
            except ValueError:
                rows = {}
            if rows:
                n = apply_zarbaha_data(obj, rows)
                messages.info(request, f'نرخ جدید از زربها گرفته نشد (فاصله‌ی ۵ دقیقه)، '
                                       f'ولی با آخرین نرخ‌های دریافتی {n} قیمت به‌روز شد.')
            else:
                messages.info(request, 'دریافت نرخ در نوبت بعدی (حداکثر ۵ دقیقه دیگر) انجام می‌شود.')

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()


# ==================== ساچمه / شمش نقره / شمش مس / سنگ فیروزه ====================

def _norm(d):
    return format(Decimal(d).normalize(), 'f')


class ShotForm(forms.ModelForm):
    purity = forms.ChoiceField(
        label='عیار',
        choices=[('999.9', 'عیار 999.9'), ('995', 'عیار 995')],
    )

    class Meta:
        model = ShotProduct
        fields = ['name', 'description', 'weight_grams', 'purity', 'stock', 'is_available', 'is_new', 'video']


class BarFormMixin:
    weight_choices = BAR_WEIGHTS

    def _setup_bar(self):
        self.fields['weight_grams'] = forms.TypedChoiceField(
            label='وزن (گرم)', choices=self.weight_choices, coerce=Decimal)
        self.fields['name'].required = False
        self.fields['name'].help_text = 'اگر خالی بگذارید خودکار از نوع و وزن ساخته می‌شود.'
        if self.instance and self.instance.pk:
            self.initial['weight_grams'] = _norm(self.instance.weight_grams)


class SilverBarForm(BarFormMixin, forms.ModelForm):
    weight_choices = SILVER_BAR_WEIGHTS

    class Meta:
        model = SilverBarProduct
        fields = ['name', 'description', 'weight_grams', 'stock', 'is_available', 'is_new', 'video']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_bar()


class CopperBarForm(BarFormMixin, forms.ModelForm):
    weight_choices = COPPER_BAR_WEIGHTS

    class Meta:
        model = CopperBarProduct
        fields = ['name', 'description', 'weight_grams', 'stock', 'is_available', 'is_new', 'video']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_bar()


class TurquoiseForm(forms.ModelForm):
    class Meta:
        model = TurquoiseProduct
        fields = ['name', 'description', 'weight_grams', 'price',
                  'stock', 'is_available', 'is_new', 'video']
        widgets = {'price': forms.NumberInput(attrs={'step': '1'})}


class SectionAdminBase(admin.ModelAdmin):
    section = None
    inlines = [ProductImageInline]
    list_display = ['name', 'weight_display', 'purity_display', 'price_display',
                    'stock', 'is_available', 'is_new']
    list_editable = ['stock', 'is_available', 'is_new']
    list_filter = ['is_available', 'is_new']
    search_fields = ['name', 'description']
    readonly_fields = ['purity_display', 'price_display']
    ordering = ['weight_grams']

    def get_queryset(self, request):
        return super().get_queryset(request).filter(SECTION_FILTERS[self.section])

    def get_fieldsets(self, request, obj=None):
        fixed = [] if self.section == 'shot' else ['purity_display']
        return (
            ('مشخصات', {'fields': ['name', 'description', 'weight_grams'] +
                                  (['purity'] if self.section == 'shot' else []) + fixed}),
            ('قیمت و موجودی', {
                'fields': ['price_display', 'stock', 'is_available', 'is_new'],
                'description': 'قیمت خودکار است: ساچمه = وزن × قیمت هر گرم، شمش = قیمت همان وزن. نرخ‌ها را در «قیمت‌ها» تغییر دهید.',
            }),
            ('ویدیو (فقط یکی)', {'fields': ['video']}),
        )

    def price_display(self, obj):
        return f'{obj.price:,} تومان' if obj and obj.pk else 'پس از ذخیره حساب می‌شود'
    price_display.short_description = 'قیمت'
    price_display.admin_order_field = 'price'

    def weight_display(self, obj):
        return obj.weight_display()
    weight_display.short_description = 'وزن'
    weight_display.admin_order_field = 'weight_grams'

    def purity_display(self, obj):
        if obj and obj.pk:
            return obj.purity_display()
        return {'silver-bar': 'عیار 999.9 (نقره)', 'copper-bar': 'خلوص 99.99 (مس)'}.get(self.section, '—')
    purity_display.short_description = 'عیار'
    purity_display.admin_order_field = 'purity'


class ShotAdmin(SectionAdminBase):
    section = 'shot'
    form = ShotForm


class SilverBarAdmin(SectionAdminBase):
    section = 'silver-bar'
    form = SilverBarForm


class CopperBarAdmin(SectionAdminBase):
    section = 'copper-bar'
    form = CopperBarForm


class TurquoiseAdmin(SectionAdminBase):
    section = 'turquoise'
    form = TurquoiseForm
    readonly_fields = []

    def get_fieldsets(self, request, obj=None):
        return (
            ('مشخصات', {'fields': ['name', 'description', 'weight_grams']}),
            ('قیمت و موجودی', {
                'fields': ['price', 'stock', 'is_available', 'is_new'],
                'description': 'قیمت فیروزه دستی است و از «قیمت‌ها» حساب نمی‌شود.',
            }),
            ('ویدیو (فقط یکی)', {'fields': ['video']}),
        )

    def price_display(self, obj):
        return f'{obj.price:,} تومان' if obj and obj.pk else '—'
    price_display.short_description = 'قیمت'

    def purity_display(self, obj):
        return '—'
    purity_display.short_description = 'عیار'


# ==================== Cart ====================

class CartAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'total_price_display', 'total_quantity', 'created_at']
    search_fields = ['user__username']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [CartItemInline]

    def total_price_display(self, obj):
        return f'{obj.total_price():,} تومان'
    total_price_display.short_description = 'قیمت کل'

    def total_quantity(self, obj):
        return obj.total_quantity()
    total_quantity.short_description = 'تعداد اقلام'

    def has_add_permission(self, request):
        return False


class CartItemAdmin(admin.ModelAdmin):
    list_display = ['id', 'cart', 'product', 'quantity', 'total_price_display']
    search_fields = ['cart__user__username', 'product__name']
    autocomplete_fields = ['cart']
    raw_id_fields = ['product']

    def total_price_display(self, obj):
        return f'{obj.total_price():,} تومان'
    total_price_display.short_description = 'قیمت کل'


# ==================== Order ====================

class OrderAdmin(admin.ModelAdmin):
    list_display = ['order_number', 'full_name', 'phone', 'delivery_method', 'show_amount', 'status_colored', 'created_at']
    list_filter = ['status', 'delivery_method', 'created_at']
    search_fields = ['user__username', 'order_number', 'full_name', 'phone', 'buyer_phone']
    readonly_fields = ['order_number', 'total_amount', 'shipping_cost', 'final_amount', 'created_at', 'updated_at']
    inlines = [OrderItemInline, PaymentReceiptInline]

    fieldsets = (
        ('اطلاعات سفارش', {'fields': ('order_number', 'user', 'status', 'discount_code')}),
        ('مبالغ', {'fields': ('total_amount', 'shipping_cost', 'final_amount')}),
        ('روش دریافت و خریدار', {'fields': ('delivery_method', 'send_to_other', 'buyer_name', 'buyer_phone')}),
        ('اطلاعات گیرنده', {'fields': ('full_name', 'phone', 'address', 'postal_code')}),
        ('تاریخ‌ها', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    def show_amount(self, obj):
        return f'{obj.final_amount:,} تومان'
    show_amount.short_description = 'مبلغ'

    def status_colored(self, obj):
        kinds = {'draft': 'mute', 'pending': 'warn', 'paid': 'info', 'completed': 'ok', 'cancelled': 'bad'}
        return format_html('<span class="sm-badge sm-{}">{}</span>', kinds.get(obj.status, 'mute'),
                           obj.get_status_display())
    status_colored.short_description = 'وضعیت'

    actions = ['mark_as_paid', 'mark_as_completed', 'mark_as_cancelled']

    def mark_as_paid(self, request, queryset):
        n = queryset.exclude(status='draft').update(status='paid')
        self.message_user(request, f'{n} سفارش به پرداخت شده تغییر یافت.')
    mark_as_paid.short_description = 'تغییر به پرداخت شده'

    def mark_as_completed(self, request, queryset):
        n = queryset.exclude(status='draft').update(status='completed')
        self.message_user(request, f'{n} سفارش به تکمیل شده تغییر یافت.')
    mark_as_completed.short_description = 'تغییر به تکمیل شده'

    def mark_as_cancelled(self, request, queryset):
        n = queryset.exclude(status='draft').update(status='cancelled')
        self.message_user(request, f'{n} سفارش به لغو شده تغییر یافت.')
    mark_as_cancelled.short_description = 'تغییر به لغو شده'


# ==================== PaymentReceipt ====================

class PaymentReceiptAdmin(admin.ModelAdmin):
    list_display = ['order_link', 'payment_method', 'image_preview', 'uploaded_at']
    list_filter = ['payment_method', 'uploaded_at']
    search_fields = ['order__order_number']
    readonly_fields = ['order', 'receipt_image', 'payment_method', 'uploaded_at', 'image_preview_large']

    def order_link(self, obj):
        url = reverse('admin:shop_order_change', args=[obj.order.id])
        return format_html('<a href="{}">{}</a>', url, obj.order.order_number)
    order_link.short_description = 'سفارش'

    def image_preview(self, obj):
        if obj.receipt_image:
            return format_html('<img src="{}" style="width:50px;height:50px;border-radius:5px;" />', obj.receipt_image.url)
        return 'ندارد'
    image_preview.short_description = 'پیش‌نمایش'

    def image_preview_large(self, obj):
        if obj.receipt_image:
            return format_html('<img src="{}" style="max-width:400px;max-height:400px;border-radius:10px;" />', obj.receipt_image.url)
        return 'تصویری وجود ندارد'
    image_preview_large.short_description = 'پیش‌نمایش بزرگ'

    def has_add_permission(self, request):
        return False


# ==================== DiscountCode ====================

class DiscountCodeAdmin(admin.ModelAdmin):
    list_display = ['code', 'user', 'discount_display', 'show_status', 'expires_at', 'created_at']
    list_filter = ['is_used', 'discount_type', 'expires_at']
    search_fields = ['code', 'user__username']
    autocomplete_fields = ['user']

    def discount_display(self, obj):
        if obj.discount_type == 'percentage':
            return f'{obj.amount}%'
        return f'{obj.amount:,.0f} تومان'
    discount_display.short_description = 'مقدار'

    def show_status(self, obj):
        if obj.is_used:
            return format_html('<span class="sm-badge sm-bad">{}</span>', 'استفاده شده')
        return format_html('<span class="sm-badge sm-ok">{}</span>', 'فعال')
    show_status.short_description = 'وضعیت'


# ==================== Chat ====================

class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ['user', 'message_short', 'get_sender', 'get_read', 'created_at']
    list_filter = ['is_admin', 'is_read', 'created_at']
    search_fields = ['user__username', 'message']
    readonly_fields = ['created_at', 'full_message_display']

    fieldsets = (
        ('اطلاعات پیام', {'fields': ('user', 'is_admin', 'is_read', 'created_at')}),
        ('محتوا', {'fields': ('message', 'image', 'video', 'full_message_display')}),
    )

    def message_short(self, obj):
        if obj.message:
            return obj.message[:50] + ('...' if len(obj.message) > 50 else '')
        if obj.image:
            return '[عکس]'
        if obj.video:
            return '[فیلم]'
        return '[بدون متن]'
    message_short.short_description = 'پیام'

    def full_message_display(self, obj):
        parts = []
        if obj.message:
            parts.append(format_html('<div class="sm-quote"><strong>متن:</strong><br>{}</div>', obj.message))
        if obj.image:
            parts.append(format_html('<div><strong>تصویر:</strong><br><img src="{}" style="max-width:300px;border-radius:12px;" /></div>',
                                     obj.image.url))
        if obj.video:
            parts.append(format_html('<div><strong>ویدیو:</strong><br><video src="{}" controls style="max-width:300px;border-radius:12px;"></video></div>',
                                     obj.video.url))
        return mark_safe(''.join(parts)) if parts else 'محتوا وجود ندارد'
    full_message_display.short_description = 'مشاهده کامل'

    def get_sender(self, obj):
        return 'ادمین' if obj.is_admin else 'کاربر'
    get_sender.short_description = 'فرستنده'

    def get_read(self, obj):
        return 'خوانده شده' if obj.is_read else 'خوانده نشده'
    get_read.short_description = 'وضعیت'


# ==================== Gallery ====================

class GalleryItemAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'item_type', 'preview', 'is_active', 'created_at']
    list_filter = ['item_type', 'is_active', 'created_at']
    search_fields = ['title', 'description']
    list_editable = ['is_active']

    fieldsets = (
        ('اطلاعات', {'fields': ('title', 'item_type', 'description', 'is_active')}),
        ('رسانه', {'fields': ('image', 'video_file', 'thumbnail')}),
    )

    def preview(self, obj):
        if obj.item_type == 'image' and obj.image:
            return format_html('<img src="{}" style="width:60px;height:60px;border-radius:5px;" />', obj.image.url)
        if obj.item_type == 'video' and obj.video_file:
            return format_html('<video src="{}" style="width:60px;height:60px;border-radius:5px;"></video>', obj.video_file.url)
        return '—'
    preview.short_description = 'پیش‌نمایش'


# ==================== Festival ====================

class FestivalAdmin(admin.ModelAdmin):
    list_display = ['title', 'image_preview', 'views', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['title', 'content']
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ['views', 'created_at', 'updated_at']
    list_editable = ['is_active']

    fieldsets = (
        ('عنوان و محتوا', {'fields': ('title', 'content')}),
        ('تصویر و اسلاگ', {'fields': ('image', 'slug')}),
        ('وضعیت', {'fields': ('is_active', 'views')}),
        ('تاریخ‌ها', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="width:50px;height:50px;border-radius:5px;" />', obj.image.url)
        return 'ندارد'
    image_preview.short_description = 'تصویر'


# ==================== FAQ ====================

class FAQAdmin(admin.ModelAdmin):
    list_display = ['question_short', 'order', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['question', 'answer']
    list_editable = ['order', 'is_active']

    fieldsets = (
        ('سوال و پاسخ', {'fields': ('question', 'answer')}),
        ('تنظیمات', {'fields': ('order', 'is_active')}),
    )

    def question_short(self, obj):
        return obj.question[:80] + ('...' if len(obj.question) > 80 else '')
    question_short.short_description = 'سوال'


# ==================== Slider ====================

class SliderAdmin(admin.ModelAdmin):
    list_display = ['id', 'image_preview', 'is_active', 'created_at']
    list_filter = ['is_active']
    list_editable = ['is_active']

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="width:50px;height:50px;border-radius:5px;" />', obj.image.url)
        return 'ندارد'
    image_preview.short_description = 'تصویر'


# ==================== Referral ====================

class ReferralSettingsAdmin(admin.ModelAdmin):
    list_display = ['id', 'is_active', 'updated_at']
    list_editable = ['is_active']

    fieldsets = (
        ('وضعیت', {'fields': ('is_active',)}),
        ('جایزه معرف', {'fields': ('referrer_discount_type', 'referrer_discount_amount', 'referrer_credit_amount')}),
        ('جایزه کاربر جدید', {'fields': ('new_user_discount_type', 'new_user_discount_amount')}),
        ('عمومی', {'fields': ('discount_expiry_days',)}),
    )

    def has_add_permission(self, request):
        return not ReferralSettings.objects.exists()


class ReferralLogAdmin(admin.ModelAdmin):
    list_display = ['referrer', 'new_user', 'discount_code_link', 'created_at']
    readonly_fields = ['referrer', 'new_user', 'discount_code', 'created_at']

    def discount_code_link(self, obj):
        if obj.discount_code:
            url = reverse('admin:shop_discountcode_change', args=[obj.discount_code.id])
            return format_html('<a href="{}">{}</a>', url, obj.discount_code.code)
        return '—'
    discount_code_link.short_description = 'کد تخفیف'

    def has_add_permission(self, request):
        return False


# ==================== AboutUs ====================

class AboutUsAdmin(admin.ModelAdmin):
    list_display = ['title', 'is_active', 'updated_at']
    list_filter = ['is_active']


# ==================== تحلیل نقره ====================

class SilverAnalysisBlockInline(admin.StackedInline):
    model = SilverAnalysisBlock
    extra = 1
    fields = ['order', 'kind', 'text', 'file', 'caption']
    verbose_name = 'بلوک'
    verbose_name_plural = 'بلوک‌های مقاله (متن/عکس/ویدیو — هر تعداد)'


class SilverAnalysisAdmin(admin.ModelAdmin):
    list_display = ['title', 'image_preview', 'is_active', 'order', 'updated_at']
    list_editable = ['is_active', 'order']
    list_filter = ['is_active']
    search_fields = ['title', 'intro']
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ['created_at', 'updated_at', 'image_preview']
    inlines = [SilverAnalysisBlockInline]

    fieldsets = (
        ('محتوا', {'fields': ('title', 'slug', 'intro')}),
        ('رسانه‌ی اصلی', {'fields': ('image', 'video')}),
        ('وضعیت', {'fields': ('is_active', 'order')}),
        ('تاریخ‌ها', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="width:60px;height:60px;border-radius:6px;" />',
                               obj.image.url)
        return '—'
    image_preview.short_description = 'تصویر'


# ==================== شبکه‌های اجتماعی ====================

PLATFORM_GUIDE = [
    ('تلگرام', 'از @BotFather ربات بسازید و توکن را اینجا بگذارید. ربات را به کانال اضافه و ادمین کنید (با اجازه‌ی ارسال پیام). '
               'شناسه‌ی کانال: @username کانال یا عددی مثل -100123…. اگر سرور به تلگرام دسترسی ندارد، پروکسی بگذارید.'),
    ('بله', 'از @botfather بله ربات بسازید و توکن را بگذارید. ربات را ادمین کانال کنید. شناسه‌ی کانال: @username کانال.'),
    ('ایتا', 'توکن را از eitaayar.ir بگیرید و ربات/حساب ارسال‌کننده را طبق راهنمای ایتایار مدیر کانال کنید. '
             'شناسه‌ی کانال: عدد یا نام کاربری کانال، همان‌طور که در ایتایار نمایش داده می‌شود.'),
    ('روبیکا', 'از ربات BotFather روبیکا ربات بسازید و توکن را بگذارید. ربات را ادمین کانال کنید و شناسه‌ی چت کانال را بنویسید '
               '(معمولاً با c0 شروع می‌شود).'),
]


class SocialChannelForm(forms.ModelForm):
    class Meta:
        model = SocialChannel
        fields = ['platform', 'name', 'chat_id', 'bot_token', 'proxy_url', 'is_active']
        widgets = {
            'bot_token': forms.TextInput(attrs={'dir': 'ltr', 'autocomplete': 'off', 'size': 60}),
            'chat_id': forms.TextInput(attrs={'dir': 'ltr', 'size': 40}),
            'proxy_url': forms.TextInput(attrs={'dir': 'ltr', 'size': 40}),
        }


class SocialChannelAdmin(admin.ModelAdmin):
    form = SocialChannelForm
    list_display = ['name', 'platform_badge', 'chat_id', 'token_display', 'is_active', 'check_status']
    list_editable = ['is_active']
    list_filter = ['platform', 'is_active']
    search_fields = ['name', 'chat_id']
    readonly_fields = ['platform_guide', 'check_status']
    actions = ['test_connection', 'send_test']

    fieldsets = (
        ('اطلاعات کانال', {'fields': ('platform', 'name', 'chat_id', 'bot_token', 'is_active')}),
        ('راهنمای اتصال هر پیام‌رسان', {'fields': ('platform_guide',)}),
        ('پیشرفته', {'fields': ('proxy_url',), 'classes': ('collapse',)}),
        ('آخرین تست', {'fields': ('check_status',)}),
    )

    def platform_badge(self, obj):
        return format_html('<span class="sm-badge sm-plat-{}">{}</span>', obj.platform, obj.get_platform_display())
    platform_badge.short_description = 'پیام‌رسان'
    platform_badge.admin_order_field = 'platform'

    def token_display(self, obj):
        return format_html('<code dir="ltr">{}</code>', obj.masked_token)
    token_display.short_description = 'توکن'

    def check_status(self, obj):
        if obj.last_check_ok is None:
            return mark_safe('<span class="sm-badge sm-mute">تست نشده</span>')
        kind = 'ok' if obj.last_check_ok else 'bad'
        return format_html('<span class="sm-badge sm-{}">{}</span>', kind, obj.last_check_message or '—')
    check_status.short_description = 'وضعیت اتصال'

    def platform_guide(self, obj):
        rows = ''.join(format_html('<p><b>{}:</b> {}</p>', n, t) for n, t in PLATFORM_GUIDE)
        return mark_safe(f'<div class="sm-guide">{rows}</div>')
    platform_guide.short_description = 'راهنما'

    def _run(self, request, queryset, fn):
        for ch in queryset:
            ok, msg = fn(ch)
            ch.last_check_ok, ch.last_check_message, ch.last_check_at = ok, msg[:290], timezone.now()
            ch.save(update_fields=['last_check_ok', 'last_check_message', 'last_check_at'])
            self.message_user(request, f'{ch}: {msg}', messages.SUCCESS if ok else messages.ERROR)

    def test_connection(self, request, queryset):
        self._run(request, queryset, social.check_channel)
    test_connection.short_description = 'تست اتصال و توکن (چیزی در کانال ارسال نمی‌شود)'

    def send_test(self, request, queryset):
        self._run(request, queryset, social.send_test_message)
    send_test.short_description = 'ارسال پیام آزمایشی به کانال'


class SocialPostMediaInline(admin.TabularInline):
    model = SocialPostMedia
    extra = 1
    fields = ['file', 'caption', 'order']
    verbose_name = 'عکس / فیلم'
    formfield_overrides = {
        dj_models.TextField: {'widget': forms.Textarea(attrs={'rows': 2, 'cols': 46,
                                                              'placeholder': 'توضیح زیر این عکس/فیلم (اختیاری)'})},
    }


class SocialDeliveryInline(admin.TabularInline):
    model = SocialDelivery
    extra = 0
    can_delete = False
    verbose_name_plural = 'نتیجه‌ی ارسال به هر کانال'
    fields = ['channel', 'result', 'sent', 'detail', 'updated_at']
    readonly_fields = ['channel', 'result', 'sent', 'detail', 'updated_at']

    def has_add_permission(self, request, obj=None):
        return False

    def result(self, obj):
        kind = {'ok': 'ok', 'partial': 'warn', 'failed': 'bad'}.get(obj.status, 'mute')
        return format_html('<span class="sm-badge sm-{}">{}</span>', kind, obj.get_status_display())
    result.short_description = 'نتیجه'

    def sent(self, obj):
        return f'{obj.sent_count} از {obj.total_count}'
    sent.short_description = 'ارسال‌شده'


class SocialPostAdminForm(forms.ModelForm):
    send_now = forms.BooleanField(
        required=False, label='بعد از ذخیره همین حالا ارسال شود',
        help_text='ارسال در پس‌زمینه انجام می‌شود؛ بعد از چند لحظه صفحه را تازه کنید تا نتیجه‌ی هر کانال را ببینید.'
    )

    class Meta:
        model = SocialPost
        fields = ['title', 'text', 'channels']
        widgets = {
            'text': forms.Textarea(attrs={'rows': 6, 'placeholder': 'متن پیام را اینجا بنویسید…'}),
            'channels': forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields['send_now'].initial = True


class SocialPostAdmin(admin.ModelAdmin):
    form = SocialPostAdminForm
    inlines = [SocialPostMediaInline, SocialDeliveryInline]
    list_display = ['post_title', 'status_badge', 'media_count', 'channels_display', 'created_by', 'created_at', 'sent_at']
    list_filter = ['status', 'created_at']
    search_fields = ['title', 'text']
    readonly_fields = ['status_badge', 'created_by', 'created_at', 'sent_at']
    actions = ['send_selected', 'resend_failed']

    fieldsets = (
        ('پیام', {'fields': ('title', 'text')}),
        ('ارسال به', {'fields': ('channels', 'send_now')}),
        ('وضعیت', {'fields': ('status_badge', 'created_by', 'created_at', 'sent_at')}),
    )

    def get_fieldsets(self, request, obj=None):
        return self.fieldsets if obj else self.fieldsets[:2]

    def post_title(self, obj):
        return str(obj)
    post_title.short_description = 'پست'

    def status_badge(self, obj):
        if not obj or not obj.pk:
            return '—'
        kind = {'sent': 'ok', 'sending': 'info', 'partial': 'warn', 'failed': 'bad'}.get(obj.status, 'mute')
        return format_html('<span class="sm-badge sm-{}">{}</span>', kind, obj.get_status_display())
    status_badge.short_description = 'وضعیت'
    status_badge.admin_order_field = 'status'

    def media_count(self, obj):
        return obj.media.count()
    media_count.short_description = 'تعداد عکس/فیلم'

    def channels_display(self, obj):
        names = [c.name for c in obj.channels.all()]
        return '، '.join(names) if names else 'همه‌ی کانال‌های فعال'
    channels_display.short_description = 'کانال‌ها'

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        if form.cleaned_data.get('send_now'):
            self._start(request, form.instance)

    def _start(self, request, post, only_failed=False):
        if not (post.text or '').strip() and not post.media.exists():
            self.message_user(request, f'«{post}»: متن یا حداقل یک عکس/فیلم لازم است.', messages.ERROR)
            return
        if not post.target_channels():
            self.message_user(request, 'هیچ کانال فعالی وجود ندارد. اول از «کانال‌های شبکه‌های اجتماعی» یک کانال اضافه کنید.',
                              messages.ERROR)
            return
        SocialPost.objects.filter(pk=post.pk).update(status='sending')
        pk = post.pk
        transaction.on_commit(lambda: social.send_post_async(pk, only_failed))
        self.message_user(request, f'ارسال «{post}» شروع شد. چند لحظه بعد صفحه را تازه کنید.', messages.SUCCESS)

    def send_selected(self, request, queryset):
        for post in queryset:
            self._start(request, post)
    send_selected.short_description = 'ارسال / ارسال مجدد به همه‌ی کانال‌های هدف'

    def resend_failed(self, request, queryset):
        for post in queryset:
            self._start(request, post, only_failed=True)
    resend_failed.short_description = 'ارسال مجدد فقط به کانال‌هایی که موفق نبودند'


# ==================== داشبورد ====================

_FA = str.maketrans('0123456789,', '۰۱۲۳۴۵۶۷۸۹٬')


def _fa(n):
    return f'{int(n or 0):,}'.translate(_FA)


def build_dashboard():
    today = timezone.localdate()
    real = Order.objects.exclude(status='draft')
    sold = real.filter(status__in=['paid', 'completed'])
    order_list = reverse('admin:shop_order_changelist')
    ps = PriceSettings.get()
    price_url = reverse('admin:shop_pricesettings_change', args=[ps.pk])

    prices = [
        {'label': 'ساچمه ۹۹۵', 'value': _fa(ps.price_shot_995), 'tone': 'silver', 'url': price_url},
        {'label': 'ساچمه ۹۹۹.۹', 'value': _fa(ps.price_shot_9999), 'tone': 'bright', 'url': price_url},
        {'label': 'شمش نقره ۱۰۰۰ گرمی', 'value': _fa(ps.price_silver_bar_1000), 'tone': 'steel', 'url': price_url},
        {'label': 'شمش مس ۱۰۰۰ گرمی', 'value': _fa(ps.price_copper_bar_1000), 'tone': 'copper', 'url': price_url},
    ]

    week_ago = timezone.now() - timedelta(days=7)
    tiles = [
        {'label': 'منتظر بررسی پرداخت', 'value': _fa(real.filter(status='pending').count()),
         'url': f'{order_list}?status__exact=pending', 'tone': 'gold'},
        {'label': 'پرداخت‌شده، آماده‌ی تحویل', 'value': _fa(real.filter(status='paid').count()),
         'url': f'{order_list}?status__exact=paid', 'tone': 'blue'},
        {'label': 'سفارش‌های امروز', 'value': _fa(real.filter(created_at__date=today).count()),
         'url': order_list, 'tone': 'silver'},
        {'label': 'فروش امروز (تومان)',
         'value': _fa(sold.filter(created_at__date=today).aggregate(s=Sum('final_amount'))['s']), 'tone': 'green'},
        {'label': 'پیام‌های خوانده‌نشده',
         'value': _fa(ChatMessage.objects.filter(is_admin=False, is_read=False).count()),
         'url': reverse('shop:admin_chat'), 'tone': 'cyan'},
        {'label': 'مشتریان', 'value': _fa(User.objects.filter(is_staff=False).count()),
         'hint': f"{_fa(User.objects.filter(is_staff=False, date_joined__gte=week_ago).count())} عضو جدید در هفته‌ی اخیر",
         'url': reverse('admin:auth_user_changelist'), 'tone': 'silver'},
        {'label': 'موجودی کم (۳ عدد یا کمتر)',
         'value': _fa(Product.objects.filter(is_available=True, stock__lte=3).count()), 'tone': 'red'},
    ]

    kinds = {'draft': 'mute', 'pending': 'warn', 'paid': 'info', 'completed': 'ok', 'cancelled': 'bad'}
    recent = [{
        'number': o.order_number or f'#{o.pk}',
        'name': o.full_name or o.user.get_full_name() or o.user.username,
        'amount': _fa(o.final_amount),
        'status': o.get_status_display(),
        'kind': kinds.get(o.status, 'mute'),
        'url': reverse('admin:shop_order_change', args=[o.pk]),
    } for o in real.select_related('user').order_by('-created_at')[:6]]

    channels = [{
        'name': c.name, 'platform': c.get_platform_display(), 'key': c.platform,
        'active': c.is_active, 'ok': c.last_check_ok,
    } for c in SocialChannel.objects.all()[:8]]

    quick = [
        {'label': 'ارسال پست به کانال‌ها', 'url': reverse('admin:shop_socialpost_add'), 'primary': True},
        {'label': 'ویرایش قیمت‌ها', 'url': price_url},
        {'label': 'افزودن ساچمه', 'url': reverse('admin:shop_shotproduct_add')},
        {'label': 'افزودن شمش نقره', 'url': reverse('admin:shop_silverbarproduct_add')},
        {'label': 'افزودن شمش مس', 'url': reverse('admin:shop_copperbarproduct_add')},
        {'label': 'افزودن سنگ فیروزه', 'url': reverse('admin:shop_turquoiseproduct_add')},
        {'label': 'افزودن تحلیل نقره', 'url': reverse('admin:shop_silveranalysis_add')},
        {'label': 'مشاهده‌ی سایت', 'url': '/'},
    ]
    return {'prices': prices, 'tiles': tiles, 'recent': recent, 'channels': channels, 'quick': quick,
            'channel_add_url': reverse('admin:shop_socialchannel_add'),
            'social_list_url': reverse('admin:shop_socialpost_changelist')}


# ==================== ثبت‌ها ====================

admin.site.unregister(User)
admin.site.register(User, UserAdmin)


class PriceSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        ('ساچمه — قیمت هر گرم', {'fields': ('price_shot_995', 'price_shot_9999'),
                                  'description': 'قیمت ساچمه = وزن × قیمت هر گرمِ همان عیار.'}),
        ('شمش نقره (عیار ۹۹۹.۹) — قیمت هر وزن', {
            'fields': ('price_silver_bar_1000', 'price_silver_bar_500', 'price_silver_bar_100', 'price_silver_bar_50')}),
        ('شمش مس — قیمت هر وزن', {
            'fields': ('price_copper_bar_1000', 'price_copper_bar_500', 'price_copper_bar_100', 'price_copper_bar_50')}),
    )
    list_display = ('__str__', 'price_shot_995', 'price_shot_9999', 'price_silver_bar_1000', 'price_copper_bar_1000', 'last_updated')

    def has_add_permission(self, request):
        return not PriceSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(SiteSettings, SiteSettingsAdmin)
admin.site.register(PriceSettings, PriceSettingsAdmin)
admin.site.register(ShotProduct, ShotAdmin)
admin.site.register(SilverBarProduct, SilverBarAdmin)
admin.site.register(CopperBarProduct, CopperBarAdmin)
admin.site.register(TurquoiseProduct, TurquoiseAdmin)
admin.site.register(Cart, CartAdmin)
admin.site.register(CartItem, CartItemAdmin)
admin.site.register(Order, OrderAdmin)
admin.site.register(PaymentReceipt, PaymentReceiptAdmin)
admin.site.register(DiscountCode, DiscountCodeAdmin)
admin.site.register(ChatMessage, ChatMessageAdmin)
admin.site.register(GalleryItem, GalleryItemAdmin)
admin.site.register(Festival, FestivalAdmin)
admin.site.register(FAQ, FAQAdmin)
admin.site.register(Slider, SliderAdmin)
admin.site.register(ReferralSettings, ReferralSettingsAdmin)
admin.site.register(ReferralLog, ReferralLogAdmin)
admin.site.register(AboutUs, AboutUsAdmin)
admin.site.register(SilverAnalysis, SilverAnalysisAdmin)
admin.site.register(SocialChannel, SocialChannelAdmin)
admin.site.register(SocialPost, SocialPostAdmin)

admin.site.site_header = 'پنل مدیریت ساچمه فر'
admin.site.site_title = 'مدیریت ساچمه فر'
admin.site.index_title = 'داشبورد مدیریت'
admin.site.site_url = '/'


# ==================== منوی گروه‌بندی‌شده و داشبورد ====================

_SECTIONS = [
    ('فروشگاه و قیمت‌ها', 'store', ['ShotProduct', 'SilverBarProduct', 'CopperBarProduct',
                                   'TurquoiseProduct', 'PriceSettings']),
    ('سفارش‌ها و پرداخت', 'orders', ['Order', 'PaymentReceipt', 'Cart', 'CartItem', 'DiscountCode']),
    ('مشتریان و ارتباط', 'customers', ['User', 'Group', 'ChatMessage', 'ReferralLog', 'ReferralSettings']),
    ('شبکه‌های اجتماعی', 'social', ['SocialPost', 'SocialChannel']),
    ('محتوا و تنظیمات سایت', 'content', ['Slider', 'GalleryItem', 'Festival', 'SilverAnalysis',
                                       'FAQ', 'AboutUs', 'SiteSettings']),
]

_orig_get_app_list = admin.site.get_app_list
_orig_index = admin.site.index


def _grouped_app_list(request, app_label=None):
    apps = _orig_get_app_list(request, app_label)
    if app_label:
        return apps
    by_name = {m['object_name']: m for app in apps for m in app['models']}
    result, used = [], set()
    for title, key, names in _SECTIONS:
        items = [by_name[n] for n in names if n in by_name]
        used.update(n for n in names if n in by_name)
        if items:
            result.append({'name': title, 'app_label': key, 'app_url': f'#{key}',
                           'has_module_perms': True, 'models': items})
    rest = [m for n, m in by_name.items() if n not in used]
    if rest:
        result.append({'name': 'سایر', 'app_label': 'other', 'app_url': '#other',
                       'has_module_perms': True, 'models': rest})
    return result


def _dashboard_index(request, extra_context=None):
    extra_context = dict(extra_context or {})
    try:
        extra_context['dashboard'] = build_dashboard()
    except Exception:
        logger.exception('admin dashboard failed')
        extra_context['dashboard'] = None
    return _orig_index(request, extra_context)


admin.site.get_app_list = _grouped_app_list
admin.site.index = _dashboard_index