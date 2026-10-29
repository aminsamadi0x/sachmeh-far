from django.views.generic import ListView, DetailView
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse, Http404
from django.db.models import Q
from django.views.decorators.http import require_GET, require_POST
from datetime import timedelta
from .models import *
from .forms import *
from .utils import send_order_telegram_message
from django.conf import settings as dj_settings
import json
import uuid
from decimal import Decimal, ROUND_HALF_UP


def price_rates(ps):
    """نرخ لحظه‌ای هر گرم (تومان) و قیمت جهانی هر اونس (دلار) برای نوار قیمت صفحه اول."""
    def gram(purity):
        try:
            return int(base_gram_price(ps, purity).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        except Exception:
            return None

    return {
        'silver_9999': gram('999.9'),
        'silver_995': gram('995'),
        'copper': gram('99.99'),
        'silver_oz': float(ps.silver_usd_per_oz) if ps.silver_usd_per_oz else None,
        'copper_oz': float(ps.copper_usd_per_oz) if ps.copper_usd_per_oz else None,
    }


# ==================== احراز هویت ====================

def custom_logout_view(request):
    logout(request)
    messages.success(request, 'شما با موفقیت از حساب کاربری خود خارج شدید.')
    return redirect('shop:home')


def register_view(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            try:
                user = form.save()
                settings_obj = ReferralSettings.objects.first()

                referral_code = form.cleaned_data.get('referral_code')
                if referral_code and settings_obj and settings_obj.is_active:
                    try:
                        referrer_profile = UserProfile.objects.get(referral_code=referral_code)

                        discount_code = None
                        if settings_obj.referrer_discount_amount > 0:
                            discount_code = DiscountCode.objects.create(
                                user=referrer_profile.user,
                                code=f"REF-{referral_code}-{user.id}-{timezone.now().strftime('%Y%m%d%H%M%S')}",
                                discount_type=settings_obj.referrer_discount_type,
                                amount=settings_obj.referrer_discount_amount,
                                expires_at=timezone.now() + timedelta(days=settings_obj.discount_expiry_days)
                            )

                        if settings_obj.referrer_credit_amount > 0:
                            referrer_profile.credits += settings_obj.referrer_credit_amount
                            referrer_profile.save()

                        if settings_obj.new_user_discount_amount > 0:
                            DiscountCode.objects.create(
                                user=user,
                                code=f"WELCOME-{user.id}-{timezone.now().strftime('%Y%m%d%H%M%S')}",
                                discount_type=settings_obj.new_user_discount_type,
                                amount=settings_obj.new_user_discount_amount,
                                expires_at=timezone.now() + timedelta(days=settings_obj.discount_expiry_days)
                            )
                            messages.success(request, 'یک کد تخفیف خوش‌آمدگویی برای شما ایجاد شد!')

                        ReferralLog.objects.create(
                            referrer=referrer_profile.user,
                            new_user=user,
                            discount_code=discount_code
                        )

                    except UserProfile.DoesNotExist:
                        messages.warning(request, 'کد معرف معتبر نیست!')

                username = form.cleaned_data.get('username')
                password = form.cleaned_data.get('password1')
                user_auth = authenticate(username=username, password=password)
                if user_auth is not None:
                    login(request, user_auth)
                    messages.success(request, 'حساب کاربری شما با موفقیت ایجاد شد!')
                    return redirect('shop:home')
                else:
                    return redirect('shop:login')

            except Exception as e:
                messages.error(request, f'خطا در ایجاد حساب کاربری: {str(e)}')
                return render(request, 'shop/register.html', {'form': form})
    else:
        ref_code = request.GET.get('ref', '')
        form = RegisterForm(initial={'referral_code': ref_code})

    return render(request, 'shop/register.html', {'form': form})


def custom_login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f'خوش آمدید {user.get_full_name() or user.username}!')
            return redirect('shop:home')
        else:
            messages.error(request, 'نام کاربری یا رمز عبور اشتباه است!')
    else:
        form = AuthenticationForm()
    return render(request, 'shop/login.html', {'form': form})


# ==================== صفحات اصلی ====================

def home(request):
    slider_items = Slider.objects.filter(is_active=True).order_by('-created_at')
    products = Product.objects.filter(is_available=True).prefetch_related('images').order_by('-created_at')[:8]
    festivals = Festival.objects.filter(is_active=True).order_by('-created_at')[:4]
    gallery_items = GalleryItem.objects.filter(is_active=True).order_by('-created_at')[:6]

    context = {
        'sections': [{'key': k, 'name': n} for k, n in PRODUCT_SECTIONS],
        'slider_items': slider_items,
        'products': products,
        'festivals': festivals,
        'gallery_items': gallery_items,
        'rates': price_rates(PriceSettings.get()),
    }
    return render(request, 'shop/home.html', context)


def about(request):
    about_content = AboutUs.objects.filter(is_active=True).first()
    if not about_content:
        about_content = AboutUs.objects.create(
            title="درباره ما",
            content="لطفاً محتوای درباره ما را از پنل ادمین وارد کنید."
        )
    return render(request, 'shop/about.html', {'about': about_content})


def terms_view(request):
    return render(request, 'shop/terms.html')


def faq_list(request):
    query = request.GET.get('q', '').strip()
    faqs = FAQ.objects.filter(is_active=True)
    if query:
        faqs = faqs.filter(Q(question__icontains=query) | Q(answer__icontains=query))
    return render(request, 'shop/faq_list.html', {
        'faqs': faqs,
        'query': query,
    })


# ==================== بخش‌ها و محصولات ====================

def product_section(request, section):
    if section not in SECTION_FILTERS:
        raise Http404
    products = (Product.objects.filter(SECTION_FILTERS[section], is_available=True)
                .prefetch_related('images').order_by('weight_grams'))
    return render(request, 'shop/section_detail.html', {
        'section': {'key': section, 'name': SECTION_LABELS[section]},
        'products': products,
    })


def product_detail(request, id):
    product = get_object_or_404(Product, id=id, is_available=True)
    related_products = Product.objects.filter(
        SECTION_FILTERS[product.section_key], is_available=True
    ).exclude(id=id).prefetch_related('images')[:4]
    return render(request, 'shop/product_detail.html', {
        'product': product,
        'images': product.images.all(),
        'related_products': related_products,
    })


# ==================== پروفایل ====================

@login_required
def profile_view(request):
    user_profile, _ = UserProfile.objects.get_or_create(user=request.user)
    discount_codes = DiscountCode.objects.filter(user=request.user)
    referral_settings = ReferralSettings.objects.first()
    referral_logs = ReferralLog.objects.filter(referrer=request.user)

    if request.method == 'POST':
        user_profile.full_name = request.POST.get('full_name', '')
        user_profile.phone = request.POST.get('phone', '')
        user_profile.address = request.POST.get('address', '')
        user_profile.postal_code = request.POST.get('postal_code', '')
        user_profile.save()

        if request.POST.get('full_name'):
            name_parts = request.POST.get('full_name', '').strip().split(' ', 1)
            request.user.first_name = name_parts[0]
            request.user.last_name = name_parts[1] if len(name_parts) > 1 else ''
            request.user.save()

        messages.success(request, 'اطلاعات پروفایل با موفقیت به‌روزرسانی شد.')
        return redirect('shop:profile')

    return render(request, 'shop/profile.html', {
        'profile': user_profile,
        'discount_codes': discount_codes,
        'referral_settings': referral_settings,
        'referral_logs': referral_logs,
    })


# ==================== سبد خرید ====================

@login_required
def add_to_cart(request, product_id):
    product = get_object_or_404(Product, id=product_id, is_available=True)

    try:
        quantity = int(request.POST.get('quantity', 1))
        if quantity < 1:
            quantity = 1
    except (ValueError, TypeError):
        quantity = 1

    if product.stock <= 0:
        messages.error(request, f'محصول {product.name} موجود نیست.')
        return redirect('shop:cart')

    cart, _ = Cart.objects.get_or_create(user=request.user)

    try:
        cart_item = CartItem.objects.get(cart=cart, product=product)
        new_quantity = cart_item.quantity + quantity
        if new_quantity > product.stock:
            messages.warning(
                request,
                f'موجودی {product.name} فقط {product.stock} عدد است.'
            )
            new_quantity = product.stock
        cart_item.quantity = new_quantity
        cart_item.save()
        message = f'تعداد {product.name} در سبد خرید به‌روزرسانی شد'
    except CartItem.DoesNotExist:
        if quantity > product.stock:
            quantity = product.stock
        CartItem.objects.create(cart=cart, product=product, quantity=quantity)
        message = f'{product.name} به سبد خرید اضافه شد'

    Order.objects.filter(user=request.user, status='draft').update(price_locked_until=None)
    messages.success(request, message)
    return redirect('shop:cart')


@login_required
def cart_view(request):
    cart, _ = Cart.objects.get_or_create(user=request.user)
    return render(request, 'shop/cart.html', {'cart': cart})


@login_required
def update_cart_item(request, item_id):
    cart_item = get_object_or_404(CartItem, id=item_id, cart__user=request.user)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'increase':
            if cart_item.quantity < cart_item.product.stock:
                cart_item.quantity += 1
                cart_item.save()
            else:
                messages.warning(
                    request,
                    f'موجودی {cart_item.product.name} فقط {cart_item.product.stock} عدد است.'
                )
        elif action == 'decrease' and cart_item.quantity > 1:
            cart_item.quantity -= 1
            cart_item.save()
        elif action == 'remove':
            cart_item.delete()
            messages.success(request, 'محصول از سبد خرید حذف شد')

        Order.objects.filter(user=request.user, status='draft').update(price_locked_until=None)

    return redirect('shop:cart')



# ==================== قفل قیمت در تسویه حساب ====================

PRICE_LOCK_MINUTES = getattr(dj_settings, 'PRICE_LOCK_MINUTES', 15)


def _lock_is_valid(order):
    return bool(order.price_locked_until and order.price_locked_until > timezone.now())


def _lock_prices(order, cart):
    """مبلغ سفارش را با قیمت همین لحظه ثابت می‌کند تا بین مرحله ۲ و ارسال رسید عوض نشود."""
    refresh = refresh_prices_if_stale()  # noqa: F841 (قیمت‌ها را تازه می‌کند)
    order.total_amount = cart.total_price()
    order.final_amount = order.total_amount
    order.price_locked_until = timezone.now() + timedelta(minutes=PRICE_LOCK_MINUTES)
    order.save()

# ==================== تسویه حساب چندمرحله‌ای ====================

@login_required
def checkout_step1(request):
    cart = get_object_or_404(Cart, user=request.user)

    if cart.items.count() == 0:
        messages.warning(request, 'سبد خرید شما خالی است')
        return redirect('shop:cart')

    draft_order = Order.objects.filter(user=request.user, status='draft', cart=cart).first()

    initial_data = {'delivery_method': 'pickup'}
    if draft_order and draft_order.full_name:
        initial_data = {
            'delivery_method': draft_order.delivery_method,
            'full_name': draft_order.buyer_name or draft_order.full_name,
            'phone': draft_order.buyer_phone or draft_order.phone,
            'send_to_other': draft_order.send_to_other,
            'recipient_name': draft_order.full_name if draft_order.send_to_other else '',
            'recipient_phone': draft_order.phone if draft_order.send_to_other else '',
            'address': draft_order.address,
            'postal_code': draft_order.postal_code,
        }
    else:
        try:
            profile = request.user.profile
            initial_data.update({
                'full_name': profile.full_name,
                'phone': profile.phone,
                'address': profile.address,
                'postal_code': profile.postal_code,
            })
        except Exception:
            pass

    if request.method == 'POST':
        form = CheckoutStep1Form(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            if not draft_order:
                draft_order = Order.objects.create(
                    user=request.user,
                    cart=cart,
                    total_amount=cart.total_price(),
                    final_amount=cart.total_price(),
                    status='draft'
                )

            draft_order.delivery_method = cd['delivery_method']
            draft_order.send_to_other = bool(cd.get('send_to_other'))
            draft_order.buyer_name = cd['full_name']
            draft_order.buyer_phone = cd['phone']
            if draft_order.send_to_other:
                # گیرنده شخص دیگری است
                draft_order.full_name = cd['recipient_name']
                draft_order.phone = cd['recipient_phone']
            else:
                draft_order.full_name = cd['full_name']
                draft_order.phone = cd['phone']
            draft_order.address = cd.get('address', '')
            draft_order.postal_code = cd.get('postal_code', '')
            draft_order.save()

            return redirect('shop:checkout_step2')
    else:
        form = CheckoutStep1Form(initial=initial_data)

    return render(request, 'shop/checkout_step1.html', {
        'cart': cart,
        'form': form,
        'order': draft_order,
    })


@login_required
def checkout_step2(request):
    cart = get_object_or_404(Cart, user=request.user)
    draft_order = Order.objects.filter(user=request.user, status='draft', cart=cart).first()

    if not draft_order:
        messages.warning(request, 'لطفاً ابتدا اطلاعات گیرنده را وارد کنید.')
        return redirect('shop:checkout_step1')

    if cart.items.count() == 0:
        messages.warning(request, 'سبد خرید شما خالی است')
        return redirect('shop:cart')

    if request.method == 'GET' or not _lock_is_valid(draft_order):
        _lock_prices(draft_order, cart)

    initial_total = draft_order.total_amount
    discount_amount = 0

    if draft_order.discount_code:
        if draft_order.discount_code.discount_type == 'percentage':
            discount_amount = (initial_total * draft_order.discount_code.amount) / 100
        else:
            discount_amount = draft_order.discount_code.amount
        final_amount = max(initial_total - discount_amount, 0)
    else:
        final_amount = initial_total

    if request.method == 'POST':
        form = CheckoutStep2Form(request.POST, user=request.user)
        if form.is_valid():
            discount_code = form.cleaned_data.get('discount_code')

            if discount_code:
                draft_order.discount_code = discount_code
                if discount_code.discount_type == 'percentage':
                    discount_amount = (initial_total * discount_code.amount) / 100
                else:
                    discount_amount = discount_code.amount
                final_amount = max(initial_total - discount_amount, 0)
                draft_order.final_amount = final_amount
                draft_order.save()
                messages.success(request, 'کد تخفیف با موفقیت اعمال شد.')
            else:
                draft_order.discount_code = None
                draft_order.final_amount = initial_total
                draft_order.save()

            return redirect('shop:checkout_step3')
    else:
        form = CheckoutStep2Form(user=request.user, initial={
            'discount_code': draft_order.discount_code.code if draft_order.discount_code else ''
        })

    site_settings = SiteSettings.objects.first()
    min_amount_for_shaba = site_settings.min_amount_for_shaba if site_settings else 10000000
    payment_method = 'shaba' if final_amount >= min_amount_for_shaba else 'card'

    return render(request, 'shop/checkout_step2.html', {
        'cart': cart,
        'form': form,
        'order': draft_order,
        'initial_total': initial_total,
        'final_amount': final_amount,
        'discount_amount': discount_amount,
        'payment_method': payment_method,
        'site_settings': site_settings,
        'min_amount_for_shaba': min_amount_for_shaba,
    })


@login_required
def checkout_step3(request):
    cart = get_object_or_404(Cart, user=request.user)
    draft_order = Order.objects.filter(user=request.user, status='draft', cart=cart).first()

    if not draft_order:
        messages.warning(request, 'لطفاً ابتدا اطلاعات گیرنده را وارد کنید.')
        return redirect('shop:checkout_step1')

    if not draft_order.full_name or not draft_order.phone:
        messages.warning(request, 'لطفاً اطلاعات گیرنده را کامل کنید.')
        return redirect('shop:checkout_step1')

    if cart.items.count() == 0:
        messages.warning(request, 'سبد خرید شما خالی است')
        return redirect('shop:cart')

    if not _lock_is_valid(draft_order):
        messages.warning(request, 'قیمت‌ها به‌روز شده‌اند. لطفاً مبلغ جدید را بررسی و تأیید کنید.')
        return redirect('shop:checkout_step2')

    initial_total = draft_order.total_amount
    discount_amount = 0

    if draft_order.discount_code:
        if draft_order.discount_code.discount_type == 'percentage':
            discount_amount = (initial_total * draft_order.discount_code.amount) / 100
        else:
            discount_amount = draft_order.discount_code.amount

    final_amount = max(initial_total - discount_amount, 0)
    draft_order.final_amount = final_amount
    draft_order.save()

    site_settings = SiteSettings.objects.first()
    min_amount_for_shaba = site_settings.min_amount_for_shaba if site_settings else 10000000
    payment_method = 'shaba' if final_amount >= min_amount_for_shaba else 'card'

    if request.method == 'POST':
        form = CheckoutStep3Form(request.POST, request.FILES)
        if form.is_valid():
            draft_order.status = 'pending'
            draft_order.save()

            if not draft_order.order_number:
                draft_order.order_number = f"ORD-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
                draft_order.save()

            PaymentReceipt.objects.create(
                order=draft_order,
                receipt_image=form.cleaned_data['receipt_image'],
                payment_method=payment_method
            )

            if draft_order.discount_code:
                draft_order.discount_code.is_used = True
                draft_order.discount_code.save()

            try:
                send_order_telegram_message(draft_order)
                messages.info(request, 'اطلاعات سفارش به پشتیبانی ارسال شد.')
            except Exception as e:
                print(f"خطا در ارسال به تلگرام: {e}")

            cart.items.all().delete()

            messages.success(request, f'سفارش شما با شماره {draft_order.order_number} ثبت شد.')
            return redirect('shop:order_detail', order_id=draft_order.id)
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{error}")
    else:
        form = CheckoutStep3Form()

    return render(request, 'shop/checkout_step3.html', {
        'cart': cart,
        'form': form,
        'order': draft_order,
        'initial_total': initial_total,
        'final_amount': final_amount,
        'discount_amount': discount_amount,
        'payment_method': payment_method,
        'site_settings': site_settings,
        'min_amount_for_shaba': min_amount_for_shaba,
    })


@login_required
def checkout_cancel(request):
    cart = get_object_or_404(Cart, user=request.user)
    draft_order = Order.objects.filter(user=request.user, status='draft', cart=cart).first()
    if draft_order:
        draft_order.delete()
        messages.info(request, 'فرآیند ثبت سفارش لغو شد.')
    return redirect('shop:cart')


@login_required
def validate_discount_code(request):
    if request.method == 'POST':
        try:
            if request.headers.get('Content-Type') == 'application/json':
                data = json.loads(request.body)
                code = data.get('code')
            else:
                code = request.POST.get('code')

            if not code:
                return JsonResponse({'valid': False, 'message': 'کد تخفیف را وارد کنید'})

            try:
                discount = DiscountCode.objects.get(
                    code=code,
                    is_used=False,
                    expires_at__gte=timezone.now(),
                    user=request.user
                )
                return JsonResponse({
                    'valid': True,
                    'discount_type': discount.discount_type,
                    'amount': float(discount.amount),
                    'message': 'کد تخفیف معتبر است'
                })
            except DiscountCode.DoesNotExist:
                return JsonResponse({
                    'valid': False,
                    'message': 'کد تخفیف معتبر نیست یا منقضی شده است'
                })
        except Exception as e:
            return JsonResponse({'valid': False, 'message': str(e)})

    return JsonResponse({'valid': False, 'message': 'درخواست نامعتبر'})


# ==================== سفارشات ====================

@login_required
def order_detail(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)

    if request.method == 'POST' and request.FILES.get('receipt_image'):
        PaymentReceipt.objects.create(
            order=order,
            receipt_image=request.FILES['receipt_image']
        )
        order.status = 'paid'
        order.save()
        try:
            send_order_telegram_message(order)
            messages.info(request, 'رسید پرداخت به پشتیبانی ارسال شد.')
        except Exception as e:
            print(f"خطا در ارسال به تلگرام: {e}")
        messages.success(request, 'رسید پرداخت با موفقیت آپلود شد')
        return redirect('shop:order_detail', order_id=order.id)

    return render(request, 'shop/order_detail.html', {'order': order})


@login_required
def order_history(request):
    orders = Order.objects.filter(user=request.user).exclude(status='draft').order_by('-created_at')
    draft_orders = Order.objects.filter(user=request.user, status='draft')
    return render(request, 'shop/order_history.html', {
        'orders': orders,
        'draft_orders': draft_orders,
    })


@login_required
def continue_order(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user, status='draft')
    return redirect('shop:checkout_step1')




# ==================== قیمت لحظه‌ای (AJAX) ====================

@require_GET
def live_prices_api(request):
    """
    هر ۳۰ ثانیه توسط JS صدا زده می‌شود. اگر قیمت جهانی کهنه باشد همین‌جا تازه می‌شود
    (با قفل دیتابیس؛ فقط یک درخواست به API خارجی در هر ۳۰ ثانیه).
    ?ids=1,2,3  → قیمت همان محصولات.   اگر کاربر وارد شده باشد قیمت سبد هم برمی‌گردد.
    """
    ps = refresh_prices_if_stale()

    ids = [int(x) for x in request.GET.get('ids', '').split(',')[:200] if x.strip().isdigit()]
    products = {}
    if ids:
        products = {str(pid): int(price) for pid, price in
                    Product.objects.filter(id__in=ids).values_list('id', 'price')}

    data = {
        'products': products,
        'rates': price_rates(ps),
        'updated_at': ps.last_updated.isoformat() if ps.last_updated else None,
        'stale': ps.is_stale,
    }

    if request.user.is_authenticated:
        cart = Cart.objects.filter(user=request.user).first()
        if cart:
            items = {str(i.id): int(i.total_price()) for i in cart.items.select_related('product')}
            data['cart'] = {'items': items, 'total': sum(items.values())}

    resp = JsonResponse(data)
    resp['Cache-Control'] = 'no-store'
    return resp

# ==================== جستجو ====================

def search_view(request):
    query = request.GET.get('q', '').strip()
    if not query:
        return JsonResponse({'products': []})

    qs = Product.objects.filter(
        Q(name__icontains=query) | Q(description__icontains=query),
        is_available=True
    )
    products = [{'id': p.id, 'name': p.name, 'price': int(p.price),
                 'section_name': p.section_label} for p in qs]
    return JsonResponse({'products': products})


def search_results_view(request):
    query = request.GET.get('q', '').strip()
    if not query:
        return redirect('shop:home')

    products = Product.objects.filter(
        Q(name__icontains=query) | Q(description__icontains=query),
        is_available=True
    ).prefetch_related('images')

    return render(request, 'shop/search_results.html', {
        'query': query,
        'products': products,
    })


# ==================== چت ====================

@login_required
def chat_view(request):
    if request.user.is_staff:
        return redirect('shop:admin_chat')

    chat_messages = ChatMessage.objects.filter(user=request.user).order_by('created_at')

    return render(request, 'shop/chat.html', {'chat_messages': chat_messages})


@login_required
@require_GET
def chat_messages_api(request):
    last_id = request.GET.get('last_id', 0)
    try:
        last_id = int(last_id)
    except (ValueError, TypeError):
        last_id = 0

    messages_qs = ChatMessage.objects.filter(
        user=request.user, id__gt=last_id
    ).order_by('created_at')

    ChatMessage.objects.filter(
        user=request.user, is_admin=True, is_read=False
    ).update(is_read=True)

    messages_data = []
    for msg in messages_qs:
        messages_data.append({
            'id': msg.id,
            'message': msg.message or '',
            'is_admin': msg.is_admin,
            'image_url': msg.image.url if msg.image else None,
            'video_url': msg.video.url if msg.video else None,
            'created_at': timezone.localtime(msg.created_at).strftime('%H:%M'),
        })

    return JsonResponse({'messages': messages_data})


@login_required
@require_POST
def chat_send_api(request):
    message_text = request.POST.get('message', '').strip()
    file = request.FILES.get('file')

    if not message_text and not file:
        return JsonResponse({'success': False, 'error': 'پیام خالی است'}, status=400)

    chat_message = ChatMessage(user=request.user, message=message_text or None, is_admin=False)

    if file:
        if file.content_type.startswith('image/'):
            chat_message.image = file
        elif file.content_type.startswith('video/'):
            chat_message.video = file

    chat_message.save()

    return JsonResponse({
        'success': True,
        'message': {
            'id': chat_message.id,
            'message': chat_message.message or '',
            'is_admin': False,
            'image_url': chat_message.image.url if chat_message.image else None,
            'video_url': chat_message.video.url if chat_message.video else None,
            'created_at': timezone.localtime(chat_message.created_at).strftime('%H:%M'),
        }
    })


@login_required
def admin_chat_view(request):
    if not request.user.is_staff:
        messages.error(request, 'شما دسترسی به این صفحه را ندارید.')
        return redirect('shop:home')

    users_with_messages = User.objects.filter(
        chat_messages__isnull=False, is_staff=False
    ).distinct().order_by('-date_joined')

    if not users_with_messages.exists():
        users_with_messages = User.objects.filter(is_staff=False).order_by('-date_joined')

    users_list = []
    for user in users_with_messages:
        try:
            profile = user.profile
            phone = profile.phone if profile and profile.phone else 'ثبت نشده'
        except Exception:
            phone = 'ثبت نشده'

        last_message = ChatMessage.objects.filter(user=user).order_by('-created_at').first()
        unread_count = ChatMessage.objects.filter(
            user=user, is_admin=False, is_read=False
        ).count()

        users_list.append({
            'user': user,
            'phone': phone,
            'last_message': last_message,
            'unread_count': unread_count,
        })

    selected_user_id = request.GET.get('user_id')
    selected_user = None
    user_messages = []

    if selected_user_id:
        try:
            selected_user = User.objects.get(id=selected_user_id)
            user_messages = ChatMessage.objects.filter(user=selected_user).order_by('created_at')
            ChatMessage.objects.filter(
                user=selected_user, is_admin=False, is_read=False
            ).update(is_read=True)
        except User.DoesNotExist:
            messages.error(request, 'کاربر مورد نظر یافت نشد.')
            return redirect('shop:admin_chat')

    return render(request, 'shop/admin_chat.html', {
        'users': users_list,
        'selected_user': selected_user,
        'user_messages': user_messages,
    })


@login_required
def admin_chat_messages_api(request):
    if not request.user.is_staff:
        return JsonResponse({'error': 'دسترسی ندارید'}, status=403)

    user_id = request.GET.get('user_id')
    last_id = request.GET.get('last_id', 0)

    if not user_id:
        return JsonResponse({'messages': []})

    try:
        last_id = int(last_id)
    except (ValueError, TypeError):
        last_id = 0

    target_user = get_object_or_404(User, id=user_id)

    messages_qs = ChatMessage.objects.filter(
        user=target_user, id__gt=last_id
    ).order_by('created_at')

    ChatMessage.objects.filter(
        user=target_user, is_admin=False, is_read=False
    ).update(is_read=True)

    messages_data = []
    for msg in messages_qs:
        messages_data.append({
            'id': msg.id,
            'message': msg.message or '',
            'is_admin': msg.is_admin,
            'image_url': msg.image.url if msg.image else None,
            'video_url': msg.video.url if msg.video else None,
            'created_at': timezone.localtime(msg.created_at).strftime('%H:%M'),
        })

    return JsonResponse({'messages': messages_data})


@login_required
@require_POST
def admin_chat_send_api(request):
    if not request.user.is_staff:
        return JsonResponse({'success': False, 'error': 'دسترسی ندارید'}, status=403)

    user_id = request.POST.get('user_id')
    message_text = request.POST.get('message', '').strip()
    file = request.FILES.get('file')

    if not user_id:
        return JsonResponse({'success': False, 'error': 'کاربر انتخاب نشده'}, status=400)

    if not message_text and not file:
        return JsonResponse({'success': False, 'error': 'پیام خالی است'}, status=400)

    target_user = get_object_or_404(User, id=user_id)

    chat_message = ChatMessage(user=target_user, message=message_text or None, is_admin=True)

    if file:
        if file.content_type.startswith('image/'):
            chat_message.image = file
        elif file.content_type.startswith('video/'):
            chat_message.video = file

    chat_message.save()

    return JsonResponse({
        'success': True,
        'message': {
            'id': chat_message.id,
            'message': chat_message.message or '',
            'is_admin': True,
            'image_url': chat_message.image.url if chat_message.image else None,
            'video_url': chat_message.video.url if chat_message.video else None,
            'created_at': timezone.localtime(chat_message.created_at).strftime('%H:%M'),
        }
    })


# ==================== گالری ====================

class GalleryListView(ListView):
    model = GalleryItem
    template_name = 'shop/gallery_list.html'
    context_object_name = 'items'
    paginate_by = 12

    def get_queryset(self):
        return GalleryItem.objects.filter(is_active=True).order_by('-created_at')


class GalleryDetailView(DetailView):
    model = GalleryItem
    template_name = 'shop/gallery_detail.html'
    context_object_name = 'item'

    def get_queryset(self):
        return GalleryItem.objects.filter(is_active=True)


# ==================== جشنواره‌ها ====================

class FestivalListView(ListView):
    model = Festival
    template_name = 'shop/festival_list.html'
    context_object_name = 'festivals'
    paginate_by = 10

    def get_queryset(self):
        return Festival.objects.filter(is_active=True).order_by('-created_at')


class FestivalDetailView(DetailView):
    model = Festival
    template_name = 'shop/festival_detail.html'
    context_object_name = 'festival'
    slug_url_kwarg = 'slug'

    def get_queryset(self):
        return Festival.objects.filter(is_active=True)

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        obj.views += 1
        obj.save(update_fields=['views'])
        return obj


# ==================== تنظیمات دعوت ====================

@login_required
@user_passes_test(lambda u: u.is_staff)
def referral_settings_view(request):
    settings_obj = ReferralSettings.objects.first()
    if not settings_obj:
        settings_obj = ReferralSettings.objects.create()

    if request.method == 'POST':
        settings_obj.is_active = request.POST.get('is_active') == 'on'
        settings_obj.referrer_discount_type = request.POST.get('referrer_discount_type')
        settings_obj.referrer_discount_amount = request.POST.get('referrer_discount_amount')
        settings_obj.referrer_credit_amount = request.POST.get('referrer_credit_amount')
        settings_obj.new_user_discount_type = request.POST.get('new_user_discount_type')
        settings_obj.new_user_discount_amount = request.POST.get('new_user_discount_amount')
        settings_obj.discount_expiry_days = request.POST.get('discount_expiry_days')
        settings_obj.save()

        messages.success(request, 'تنظیمات با موفقیت به‌روزرسانی شد.')
        return redirect('shop:referral_settings')

    return render(request, 'shop/referral_settings.html', {'settings': settings_obj})