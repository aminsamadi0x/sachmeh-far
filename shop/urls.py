from django.urls import path
from . import views

app_name = 'shop'

urlpatterns = [
    # صفحات اصلی
    path('', views.home, name='home'),
    path('about/', views.about, name='about'),
    path('terms/', views.terms_view, name='terms'),
    path('faq/', views.faq_list, name='faq_list'),

    # بخش‌های فروشگاه: shot / silver-bar / copper-bar
    path('section/<slug:section>/', views.product_section, name='product_section'),

    # محصولات
    path('product/<int:id>/', views.product_detail, name='product_detail'),

    # احراز هویت
    path('register/', views.register_view, name='register'),
    path('login/', views.custom_login_view, name='login'),
    path('logout/', views.custom_logout_view, name='logout'),

    # پروفایل
    path('profile/', views.profile_view, name='profile'),

    # سبد خرید
    path('cart/', views.cart_view, name='cart'),
    path('cart/add/<int:product_id>/', views.add_to_cart, name='add_to_cart'),
    path('cart/update/<int:item_id>/', views.update_cart_item, name='update_cart_item'),

    # تسویه حساب
    path('checkout/', views.checkout_step1, name='checkout'),
    path('checkout/step1/', views.checkout_step1, name='checkout_step1'),
    path('checkout/step2/', views.checkout_step2, name='checkout_step2'),
    path('checkout/step3/', views.checkout_step3, name='checkout_step3'),
    path('checkout/cancel/', views.checkout_cancel, name='checkout_cancel'),

    # سفارشات
    path('order/<int:order_id>/', views.order_detail, name='order_detail'),
    path('orders/', views.order_history, name='order_history'),
    path('order/continue/<int:order_id>/', views.continue_order, name='continue_order'),
    path('validate-discount/', views.validate_discount_code, name='validate_discount'),

    # چت
    path('chat/', views.chat_view, name='chat'),
    path('admin-panel/chat/', views.admin_chat_view, name='admin_chat'),
    path('api/chat/messages/', views.chat_messages_api, name='chat_messages_api'),
    path('api/chat/send/', views.chat_send_api, name='chat_send_api'),
    path('api/admin-chat/messages/', views.admin_chat_messages_api, name='admin_chat_messages_api'),
    path('api/admin-chat/send/', views.admin_chat_send_api, name='admin_chat_send_api'),

    # قیمت لحظه‌ای
    path('api/live-prices/', views.live_prices_api, name='live_prices_api'),

    # جستجو
    path('search/', views.search_results_view, name='search_results'),
    path('search/ajax/', views.search_view, name='search_ajax'),

    # گالری
    path('gallery/', views.GalleryListView.as_view(), name='gallery_list'),
    path('gallery/<int:pk>/', views.GalleryDetailView.as_view(), name='gallery_detail'),

    # جشنواره‌ها
    path('festivals/', views.FestivalListView.as_view(), name='festival_list'),
    path('festivals/<slug:slug>/', views.FestivalDetailView.as_view(), name='festival_detail'),

    # تنظیمات دعوت
    path('admin-panel/referral-settings/', views.referral_settings_view, name='referral_settings'),
]