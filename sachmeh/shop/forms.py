from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.utils import timezone
from .models import (
    UserProfile, ReferralSettings, DiscountCode, ChatMessage,
    GalleryItem, Festival, Order
)
import re

from .phone import normalize_phone, normalize_digits, PHONE_RE


# ==================== ثبت‌نام ====================

class RegisterForm(forms.Form):
    """ثبت‌نام با شماره موبایل (نام کاربری وجود ندارد؛ شماره‌ی موبایل همان شناسه‌ی ورود است)."""
    phone = forms.CharField(
        label='شماره موبایل', required=True, max_length=20,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '09123456789',
                                      'inputmode': 'tel', 'dir': 'ltr', 'autocomplete': 'tel'})
    )
    first_name = forms.CharField(
        label='نام', required=True, max_length=30,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'نام'})
    )
    last_name = forms.CharField(
        label='نام خانوادگی', required=True, max_length=30,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'نام خانوادگی'})
    )
    email = forms.EmailField(
        label='ایمیل', required=True,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'ایمیل خود را وارد کنید'})
    )
    password1 = forms.CharField(
        label='رمز عبور', strip=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'new-password'}),
        help_text=password_validation.password_validators_help_text_html(),
    )
    password2 = forms.CharField(
        label='تکرار رمز عبور', strip=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'new-password'}),
    )
    referral_code = forms.CharField(
        label='کد معرف', required=False, max_length=7,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'کد معرف (اختیاری)'})
    )

    field_order = ['phone', 'first_name', 'last_name', 'email', 'password1', 'password2', 'referral_code']

    def clean_phone(self):
        phone = normalize_phone(self.cleaned_data.get('phone'))
        if not PHONE_RE.match(phone):
            raise forms.ValidationError('شماره موبایل باید با ۰۹ شروع شده و ۱۱ رقم باشد.')
        if User.objects.filter(username=phone).exists() or UserProfile.objects.filter(phone=phone).exists():
            raise forms.ValidationError('با این شماره قبلاً ثبت‌نام شده است. وارد شوید.')
        return phone

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('این ایمیل قبلاً ثبت شده است.')
        return email

    def clean_referral_code(self):
        referral_code = (self.cleaned_data.get('referral_code') or '').strip().upper()
        settings = ReferralSettings.objects.first()
        if settings and not settings.is_active:
            return None
        if referral_code:
            if not UserProfile.objects.filter(referral_code=referral_code).exists():
                raise forms.ValidationError('کد معرف معتبر نیست.')
        return referral_code

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get('password1'), cleaned.get('password2')
        if p1 and p2:
            if p1 != p2:
                self.add_error('password2', 'دو رمز عبور یکسان نیستند.')
            else:
                candidate = User(username=cleaned.get('phone') or '', first_name=cleaned.get('first_name') or '',
                                 last_name=cleaned.get('last_name') or '', email=cleaned.get('email') or '')
                try:
                    password_validation.validate_password(p2, candidate)
                except forms.ValidationError as e:
                    self.add_error('password2', e)
        return cleaned

    def save(self):
        cd = self.cleaned_data
        user = User.objects.create_user(
            username=cd['phone'], email=cd['email'], password=cd['password1'],
            first_name=cd['first_name'], last_name=cd['last_name'],
        )
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.phone = cd['phone']
        profile.full_name = f"{cd['first_name']} {cd['last_name']}".strip()
        profile.save()
        return user


class PhoneLoginForm(AuthenticationForm):
    """ورود با شماره موبایل + رمز عبور. ادمین‌ها هنوز می‌توانند با نام کاربری خودشان وارد شوند."""
    username = forms.CharField(
        label='شماره موبایل',
        widget=forms.TextInput(attrs={'autofocus': True, 'placeholder': '09123456789', 'inputmode': 'tel',
                                      'dir': 'ltr', 'autocomplete': 'username'})
    )
    error_messages = {
        'invalid_login': 'شماره موبایل یا رمز عبور اشتباه است.',
        'inactive': 'این حساب غیرفعال است.',
    }

    def clean_username(self):
        value = (self.cleaned_data.get('username') or '').strip()
        phone = normalize_phone(value)
        return phone if PHONE_RE.match(phone) else value


# ==================== تسویه حساب ====================

class CheckoutStep1Form(forms.Form):
    delivery_method = forms.ChoiceField(
        label='روش دریافت',
        choices=Order.DELIVERY_CHOICES,
        initial='pickup',
        widget=forms.RadioSelect,
    )
    # مشخصات خریدار (خود شما)
    full_name = forms.CharField(
        label='نام و نام خانوادگی شما',
        max_length=100, required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'نام و نام خانوادگی'})
    )
    phone = forms.CharField(
        label='شماره تماس شما',
        max_length=15, required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '۰۹۱۲۳۴۵۶۷۸۹'})
    )

    # ارسال برای شخص دیگر
    send_to_other = forms.BooleanField(label='این سفارش را برای شخص دیگری می‌فرستم', required=False)
    recipient_name = forms.CharField(
        label='نام و نام خانوادگی گیرنده', max_length=100, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'نام گیرنده'})
    )
    recipient_phone = forms.CharField(
        label='شماره تماس گیرنده', max_length=15, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '۰۹۱۲۳۴۵۶۷۸۹'})
    )

    # فقط برای ارسال با تیپاکس / ایرکس
    address = forms.CharField(
        label='آدرس کامل', required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3,
                                     'placeholder': 'استان، شهر، خیابان، کوچه، پلاک'})
    )
    postal_code = forms.CharField(
        label='کد پستی', max_length=20, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'کد پستی ۱۰ رقمی'})
    )

    @staticmethod
    def _norm_phone(value):
        return normalize_phone(value)

    def clean_phone(self):
        phone = self._norm_phone(self.cleaned_data.get('phone'))
        if not re.match(r'^09\d{9}$', phone):
            raise forms.ValidationError('شماره تماس باید با ۰۹ شروع شده و ۱۱ رقم باشد.')
        return phone

    def clean_postal_code(self):
        return normalize_digits(self.cleaned_data.get('postal_code'))

    def clean(self):
        data = super().clean()
        method = data.get('delivery_method')

        # ارسال برای شخص دیگر → مشخصات گیرنده الزامی است
        if data.get('send_to_other'):
            name = (data.get('recipient_name') or '').strip()
            phone = self._norm_phone(data.get('recipient_phone'))
            if not name:
                self.add_error('recipient_name', 'نام گیرنده را وارد کنید.')
            if not re.match(r'^09\d{9}$', phone):
                self.add_error('recipient_phone', 'شماره تماس گیرنده باید با ۰۹ شروع شده و ۱۱ رقم باشد.')
            data['recipient_name'] = name
            data['recipient_phone'] = phone

        # ارسال با تیپاکس / ایرکس → آدرس و کد پستی الزامی است
        if method in ('tipax', 'irex'):
            if not (data.get('address') or '').strip():
                self.add_error('address', 'آدرس کامل را وارد کنید.')
            postal = data.get('postal_code') or ''
            if not re.match(r'^\d{10}$', postal):
                self.add_error('postal_code', 'کد پستی باید ۱۰ رقم باشد.')
        else:
            data['address'] = ''
            data['postal_code'] = ''
        return data


class CheckoutStep2Form(forms.Form):
    discount_code = forms.CharField(
        label='کد تخفیف',
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'کد تخفیف (اختیاری)'})
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

    def clean_discount_code(self):
        code = self.cleaned_data.get('discount_code')
        if code and self.user:
            try:
                discount = DiscountCode.objects.get(
                    code=code,
                    is_used=False,
                    expires_at__gte=timezone.now(),
                    user=self.user
                )
                return discount
            except DiscountCode.DoesNotExist:
                raise forms.ValidationError('کد تخفیف معتبر نیست یا منقضی شده است.')
        return None


class CheckoutStep3Form(forms.Form):
    receipt_image = forms.ImageField(
        label='تصویر رسید پرداخت',
        required=True,
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'})
    )

    def clean_receipt_image(self):
        img = self.cleaned_data['receipt_image']
        if img.size > 10 * 1024 * 1024:
            raise forms.ValidationError('حجم رسید نباید بیشتر از ۱۰ مگابایت باشد.')
        return img


# ==================== چت ====================

class ChatMessageForm(forms.ModelForm):
    class Meta:
        model = ChatMessage
        fields = ['message', 'image', 'video']
        widgets = {
            'message': forms.Textarea(attrs={'class': 'form-control', 'rows': 3,
                                             'placeholder': 'پیام خود را وارد کنید...'}),
            'image': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'video': forms.FileInput(attrs={'class': 'form-control', 'accept': 'video/*'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        message = cleaned_data.get('message')
        image = cleaned_data.get('image')
        video = cleaned_data.get('video')
        if not message and not image and not video:
            raise forms.ValidationError('حداقل یکی از فیلدهای پیام، عکس یا ویدیو باید پر شود.')
        return cleaned_data


# ==================== گالری ====================

class GalleryItemForm(forms.ModelForm):
    class Meta:
        model = GalleryItem
        fields = ['title', 'item_type', 'image', 'video_file', 'thumbnail', 'description', 'is_active']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'item_type': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'image': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'video_file': forms.FileInput(attrs={'class': 'form-control', 'accept': 'video/*'}),
            'thumbnail': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


# ==================== جشنواره ====================

class FestivalForm(forms.ModelForm):
    class Meta:
        model = Festival
        fields = ['title', 'content', 'image', 'is_active']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 6}),
            'image': forms.FileInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
