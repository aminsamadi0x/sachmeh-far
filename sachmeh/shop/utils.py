import logging

import requests
from django.conf import settings

log = logging.getLogger(__name__)


def _cfg():
    token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '') or ''
    chat = str(getattr(settings, 'TELEGRAM_CHAT_ID', '') or '')
    if not token or not chat or 'YOUR_' in token or 'YOUR_' in chat:
        return None, None
    return token, chat


def _order_lines(order):
    items = list(order.items.all())
    if items:
        return [f"• {i.name} × {i.quantity} = {i.total_price():,} تومان" for i in items]
    return [f"• {i.product.name} × {i.quantity} = {i.total_price():,} تومان" for i in order.cart.items.all()]


def build_order_message(order):
    lines = [
        "سفارش جدید ثبت شد",
        f"شماره سفارش: {order.order_number or '—'}",
        f"کاربر: {order.user.get_full_name() or '—'} ({order.user.username})",
        f"مبلغ کالاها: {order.total_amount:,} تومان",
    ]
    if order.shipping_cost:
        lines.append(f"هزینه ارسال: {order.shipping_cost:,} تومان")
    if order.final_amount != order.total_amount:
        lines.append(f"مبلغ نهایی: {order.final_amount:,} تومان")
    if order.discount_code:
        lines.append(f"کد تخفیف: {order.discount_code.code}")
    lines += [f"وضعیت: {order.get_status_display()}", f"روش دریافت: {order.get_delivery_method_display()}", ""]
    if order.send_to_other:
        lines += ["خریدار:", f"نام: {order.buyer_name}", f"تلفن: {order.buyer_phone}", ""]
    lines += ["گیرنده:" if order.send_to_other else "مشخصات:", f"نام: {order.full_name}", f"تلفن: {order.phone}"]
    if order.is_shipping:
        lines += [f"آدرس: {order.address}", f"کد پستی: {order.postal_code}"]
    lines += ["", "محصولات:"] + _order_lines(order)
    return "\n".join(lines)


def send_order_telegram_message(order):
    """پیام سفارش (متن ساده، بدون Markdown تا نام‌ها پیام را خراب نکنند) و عکس رسید را می‌فرستد.
    توکن و شناسه‌ی چت از settings.py: TELEGRAM_BOT_TOKEN و TELEGRAM_CHAT_ID."""
    token, chat = _cfg()
    if not token:
        log.warning('TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID در settings.py تنظیم نشده است.')
        return False
    base = f"https://api.telegram.org/bot{token}"
    try:
        ok = requests.post(f"{base}/sendMessage", data={"chat_id": chat, "text": build_order_message(order)[:4000]},
                           timeout=15).status_code == 200
        receipt = getattr(order, 'receipt', None)
        if receipt and receipt.receipt_image:
            try:
                with receipt.receipt_image.open('rb') as fh:
                    requests.post(f"{base}/sendPhoto", data={"chat_id": chat, "caption": f"رسید سفارش {order.order_number}"},
                                  files={"photo": fh}, timeout=60)
            except Exception:
                log.exception('ارسال عکس رسید به تلگرام ناموفق بود')
        return ok
    except Exception:
        log.exception('خطا در ارسال سفارش به تلگرام')
        return False
