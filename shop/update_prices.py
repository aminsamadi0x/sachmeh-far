import time

from django.conf import settings
from django.core.management.base import BaseCommand

from shop.models import PriceSettings, recalculate_all_products, refresh_prices_if_stale


class Command(BaseCommand):
    help = 'قیمت جهانی نقره و مس را می‌گیرد و قیمت محصولات و تاریخچه‌ی چارت را به‌روز می‌کند.'

    def add_arguments(self, parser):
        parser.add_argument('--loop', action='store_true',
                            help='به‌صورت دائمی اجرا شود (هر ۳۰ ثانیه)، بدون نیاز به بازدیدکننده')

    def handle(self, *args, **opts):
        if not opts['loop']:
            ps = refresh_prices_if_stale()
            n = recalculate_all_products(ps)
            self.stdout.write(f'محصولات به‌روز شده: {n} | last_updated={ps.last_updated} | error={ps.last_error or "-"}')
            return

        self.stdout.write('شروع حلقه‌ی به‌روزرسانی قیمت (Ctrl+C برای توقف)')
        while True:
            try:
                refresh_prices_if_stale()  # خودش فاصله‌ی PRICE_REFRESH_SECONDS را رعایت می‌کند
            except Exception as e:
                self.stderr.write(f'خطا: {e}')
            time.sleep(min(5, getattr(settings, 'PRICE_REFRESH_SECONDS', 30)))