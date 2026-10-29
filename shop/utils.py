import requests

TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID_HERE"


def send_order_telegram_message(order):
    try:
        from .models import PaymentReceipt

        message = "🎮 **سفارش جدید ثبت شد!**\n"
        message += f"📦 شماره سفارش: {order.order_number or '—'}\n"
        message += f"👤 کاربر: {order.user.username}\n"
        message += f"💰 مبلغ اولیه: {order.total_amount:,} تومان\n"

        if order.final_amount != order.total_amount:
            message += f"💵 مبلغ نهایی: {order.final_amount:,} تومان\n"

        if order.discount_code:
            message += f"🏷 کد تخفیف: {order.discount_code.code}\n"

        message += f"📊 وضعیت: {order.get_status_display()}\n\n"
        message += f"🚚 روش دریافت: {order.get_delivery_method_display()}\n\n"
        if order.send_to_other:
            message += "🙋 **خریدار:**\n"
            message += f"نام: {order.buyer_name}\n"
            message += f"📞 تلفن: {order.buyer_phone}\n\n"
        message += "👤 **اطلاعات گیرنده:**\n"
        message += f"نام: {order.full_name}\n"
        message += f"📞 تلفن: {order.phone}\n"
        if order.is_shipping:
            message += f"📍 آدرس: {order.address}\n"
            message += f"📮 کد پستی: {order.postal_code}\n"
        message += "\n"

        message += "🛒 **محصولات:**\n"
        for item in order.cart.items.all():
            message += f"• {item.product.name} × {item.quantity} = {item.total_price():,} تومان\n"

        receipt = PaymentReceipt.objects.filter(order=order).first()

        if receipt and receipt.receipt_image:
            try:
                photo_url = receipt.receipt_image.url
                if photo_url.startswith('/'):
                    photo_url = f"http://localhost:8000{photo_url}"

                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
                data = {
                    "chat_id": TELEGRAM_CHAT_ID,
                    "caption": message,
                    "parse_mode": "Markdown",
                    "photo": photo_url,
                }
                return requests.post(url, data=data, timeout=15).status_code == 200
            except Exception:
                pass

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown",
        }
        return requests.post(url, data=data, timeout=15).status_code == 200

    except Exception as e:
        print(f"خطا در ارسال تلگرام: {e}")
        return False