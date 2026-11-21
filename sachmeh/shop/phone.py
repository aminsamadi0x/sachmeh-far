"""نرمال‌سازی و اعتبارسنجی شماره موبایل (بدون وابستگی به جنگو)."""
import re

# ارقام فارسی (۰-۹) و عربی (٠-٩) → انگلیسی
_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
PHONE_RE = re.compile(r'^09\d{9}$')


def normalize_digits(value):
    """فقط ارقام فارسی/عربی را انگلیسی می‌کند و فاصله‌ها را برمی‌دارد (برای کد پستی و ...)."""
    return re.sub(r'\s+', '', str(value or '').translate(_DIGITS))


def normalize_phone(value):
    """۰۹۱۲… / +98912… / 0098912… / 912… همه به 09123456789 تبدیل می‌شوند.
    اگر ورودی شبیه شماره نبود، همان رشته‌ی تمیزشده برمی‌گردد."""
    s = str(value or '').translate(_DIGITS)
    s = re.sub(r'[\s\-().]', '', s)
    if s.startswith('+98'):
        s = '0' + s[3:]
    elif s.startswith('0098'):
        s = '0' + s[4:]
    elif s.startswith('98') and len(s) == 12:
        s = '0' + s[2:]
    elif len(s) == 10 and s.startswith('9'):
        s = '0' + s
    return s


def is_valid_phone(value):
    return bool(PHONE_RE.match(normalize_phone(value)))
