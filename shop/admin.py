from decimal import Decimal
from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.utils.safestring import mark_safe
from django.urls import reverse
from .models import *


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

class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)
    list_display = ['username', 'email', 'first_name', 'last_name', 'is_staff', 'date_joined']
    list_filter = ['is_staff', 'is_superuser', 'is_active', 'groups']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering = ['-date_joined']

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('اطلاعات شخصی', {'fields': ('first_name', 'last_name', 'email')}),
        ('دسترسی‌ها', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('تاریخ‌ها', {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'password1', 'password2'),
        }),
    )


# ==================== SiteSettings ====================

class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = ['site_name', 'updated_at']

    fieldsets = (
        ('اطلاعات عمومی سایت', {
            'fields': ('site_name', 'site_description', 'logo_text',
                       'background_image', 'background_overlay_opacity', 'background_fixed'),
        }),
        ('عکس دسته‌بندی‌های صفحه اول', {
            'fields': ('img_shot', 'img_copper_bar', 'img_silver_bar'),
            'description': 'برای هر کدام از سه دسته یک عکس بگذارید؛ در صفحه اول به‌جای تصویر پیش‌فرض نمایش داده می‌شود.',
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
    )

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()


# ==================== ساچمه / شمش نقره / شمش مس ====================

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


class SilverBarForm(forms.ModelForm):
    weight_grams = forms.TypedChoiceField(
        label='وزن (گرم)', choices=SILVER_BAR_WEIGHTS, coerce=Decimal,
    )

    class Meta:
        model = SilverBarProduct
        fields = ['name', 'description', 'weight_grams', 'stock', 'is_available', 'is_new', 'video']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.initial['weight_grams'] = _norm(self.instance.weight_grams)


class CopperBarForm(forms.ModelForm):
    class Meta:
        model = CopperBarProduct
        fields = ['name', 'description', 'weight_grams', 'stock', 'is_available', 'is_new', 'video']


class SectionAdminBase(admin.ModelAdmin):
    section = None          # کلید بخش در SECTION_FILTERS
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
                'description': 'قیمت خودکار از قیمت لحظه‌ای انس جهانی حساب می‌شود و هر ۳۰ ثانیه به‌روز است.',
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
        return {'silver-bar': 'عیار 995 (نقره)', 'copper-bar': 'خلوص 99.99 (مس)'}.get(self.section, '—')
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
    list_display = ['order_number', 'user', 'full_name', 'delivery_method', 'show_amount', 'status_colored', 'created_at']
    list_filter = ['status', 'delivery_method', 'created_at']
    search_fields = ['user__username', 'order_number', 'full_name', 'phone']
    readonly_fields = ['order_number', 'total_amount', 'final_amount', 'created_at', 'updated_at']
    inlines = [PaymentReceiptInline]

    fieldsets = (
        ('اطلاعات سفارش', {'fields': ('order_number', 'user', 'status', 'discount_code')}),
        ('مبالغ', {'fields': ('total_amount', 'final_amount')}),
        ('روش دریافت و خریدار', {'fields': ('delivery_method', 'send_to_other', 'buyer_name', 'buyer_phone')}),
        ('اطلاعات گیرنده', {'fields': ('full_name', 'phone', 'address', 'postal_code')}),
        ('تاریخ‌ها', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    def show_amount(self, obj):
        return f'{obj.final_amount:,} تومان'
    show_amount.short_description = 'مبلغ'

    def status_colored(self, obj):
        colors = {'draft': '#888', 'pending': '#FFA500', 'paid': '#00FFFF',
                  'completed': '#00FF00', 'cancelled': '#FF0000'}
        texts = {'draft': 'پیش‌نویس', 'pending': 'در انتظار پرداخت', 'paid': 'پرداخت شده',
                 'completed': 'تکمیل شده', 'cancelled': 'لغو شده'}
        return mark_safe(
            f'<span style="color:{colors.get(obj.status, "#fff")};background:rgba(0,0,0,.5);'
            f'padding:3px 8px;border-radius:12px;">{texts.get(obj.status, obj.status)}</span>'
        )
    status_colored.short_description = 'وضعیت'

    actions = ['mark_as_paid', 'mark_as_completed', 'mark_as_cancelled']

    def mark_as_paid(self, request, queryset):
        n = queryset.update(status='paid')
        self.message_user(request, f'{n} سفارش به پرداخت شده تغییر یافت.')
    mark_as_paid.short_description = 'تغییر به پرداخت شده'

    def mark_as_completed(self, request, queryset):
        n = queryset.update(status='completed')
        self.message_user(request, f'{n} سفارش به تکمیل شده تغییر یافت.')
    mark_as_completed.short_description = 'تغییر به تکمیل شده'

    def mark_as_cancelled(self, request, queryset):
        n = queryset.update(status='cancelled')
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
        return mark_safe(f'<a href="{url}">{obj.order.order_number}</a>')
    order_link.short_description = 'سفارش'

    def image_preview(self, obj):
        if obj.receipt_image:
            return mark_safe(f'<img src="{obj.receipt_image.url}" style="width:50px;height:50px;border-radius:5px;" />')
        return 'ندارد'
    image_preview.short_description = 'پیش‌نمایش'

    def image_preview_large(self, obj):
        if obj.receipt_image:
            return mark_safe(f'<img src="{obj.receipt_image.url}" style="max-width:400px;max-height:400px;border-radius:10px;" />')
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
            return mark_safe('<span style="color:#FF0000;">استفاده شده</span>')
        return mark_safe('<span style="color:#00FF00;">فعال</span>')
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
            parts.append(
                '<div style="margin-bottom:10px;padding:10px;background:#333;border-radius:5px;color:#fff;">'
                f'<strong>متن:</strong><br>{obj.message}</div>'
            )
        if obj.image:
            parts.append(
                '<div><strong>تصویر:</strong><br>'
                f'<img src="{obj.image.url}" style="max-width:300px;border-radius:5px;" /></div>'
            )
        if obj.video:
            parts.append(
                '<div><strong>ویدیو:</strong><br>'
                f'<video src="{obj.video.url}" controls style="max-width:300px;border-radius:5px;"></video></div>'
            )
        return mark_safe(''.join(parts) or 'محتوا وجود ندارد')
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
            return mark_safe(f'<img src="{obj.image.url}" style="width:60px;height:60px;border-radius:5px;" />')
        if obj.item_type == 'video' and obj.video_file:
            return mark_safe(f'<video src="{obj.video_file.url}" style="width:60px;height:60px;border-radius:5px;"></video>')
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
            return mark_safe(f'<img src="{obj.image.url}" style="width:50px;height:50px;border-radius:5px;" />')
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
            return mark_safe(f'<img src="{obj.image.url}" style="width:50px;height:50px;border-radius:5px;" />')
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
            return mark_safe(f'<a href="{url}">{obj.discount_code.code}</a>')
        return '—'
    discount_code_link.short_description = 'کد تخفیف'

    def has_add_permission(self, request):
        return False


# ==================== AboutUs ====================

class AboutUsAdmin(admin.ModelAdmin):
    list_display = ['title', 'is_active', 'updated_at']
    list_filter = ['is_active']

    def has_add_permission(self, request):
        return not AboutUs.objects.exists()


# ==================== ثبت‌ها ====================

admin.site.unregister(User)
admin.site.register(User, UserAdmin)

admin.site.register(SiteSettings, SiteSettingsAdmin)
admin.site.register(ShotProduct, ShotAdmin)
admin.site.register(SilverBarProduct, SilverBarAdmin)
admin.site.register(CopperBarProduct, CopperBarAdmin)
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

admin.site.site_header = 'پنل مدیریت ساچمه فر'
admin.site.site_title = 'مدیریت ساچمه فر'
admin.site.index_title = 'داشبورد مدیریت'
admin.site.site_url = '/'