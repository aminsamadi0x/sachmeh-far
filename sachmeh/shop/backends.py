from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

from .phone import normalize_phone, PHONE_RE


class PhoneBackend(ModelBackend):
    """ورود با شماره موبایل.

    - کاربران جدید: username همان شماره‌ی موبایل است.
    - کاربران قدیمی که username دیگری دارند ولی شماره در پروفایلشان ثبت است هم با شماره وارد می‌شوند.
    - ادمین‌ها هنوز می‌توانند با username خودشان وارد شوند.
    اگر یک شماره به بیش از یک حساب برسد، ورود رد می‌شود (برای امنیت)."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(get_user_model().USERNAME_FIELD)
        if username is None or password is None:
            return None
        User = get_user_model()
        raw = str(username).strip()
        if not raw:
            return None
        phone = normalize_phone(raw)
        cond = Q(username__in={raw, phone})
        if PHONE_RE.match(phone):  # شماره‌ی خالی/نامعتبر نباید با پروفایل‌های بدون شماره یکی شود
            cond |= Q(profile__phone=phone)
        users = list(User.objects.filter(cond).distinct()[:2])
        if len(users) != 1:
            User().set_password(password)  # زمان پاسخ را برای حساب نامعتبر هم‌اندازه می‌کند
            return None
        user = users[0]
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
