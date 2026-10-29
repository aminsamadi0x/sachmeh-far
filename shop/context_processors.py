from .models import SiteSettings, PRODUCT_SECTIONS


def site_settings(request):
    try:
        settings = SiteSettings.objects.first()
        if not settings:
            settings = SiteSettings.objects.create()
    except Exception:
        settings = None
    return {'site_settings': settings}


def sections_menu(request):
    """سه بخش فروشگاه برای منوی بالا: ساچمه، شمش نقره، شمش مس."""
    return {'menu_sections': [{'key': k, 'name': n} for k, n in PRODUCT_SECTIONS]}