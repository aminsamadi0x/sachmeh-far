"""ارسال پست به ربات‌های تلگرام، بله، ایتا و روبیکا.

این ماژول در سطح بالا به جنگو وابسته نیست (ایمپورت‌های جنگو داخل توابع‌اند) تا جدا از پروژه هم
قابل تست باشد. مستندات هر پیام‌رسان:
  تلگرام : https://api.telegram.org/bot<TOKEN>/<method>          (sendMessage / sendPhoto / sendVideo / sendDocument)
  بله    : https://tapi.bale.ai/bot<TOKEN>/<method>              (همان ساختار تلگرام)
  ایتا   : https://eitaayar.ir/api/<TOKEN>/<method>              (sendMessage / sendFile) - توکن از eitaayar.ir
  روبیکا : https://botapi.rubika.ir/v3/<TOKEN>/<method>          (sendMessage؛ فایل: requestSendFile ← آپلود ← sendFile)
"""
import logging
import mimetypes
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

log = logging.getLogger(__name__)

CAPTION_LIMIT = 1024          # حد کپشن عکس/فیلم در تلگرام و بله
TEXT_LIMIT = 4000             # حد متن پیام (تلگرام ۴۰۹۶)
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_VIDEO_BYTES = 50 * 1024 * 1024

IMAGE_EXT = {'.jpg', '.jpeg', '.png', '.webp'}
VIDEO_EXT = {'.mp4', '.mov', '.mkv', '.webm', '.avi', '.m4v'}


def media_kind(filename):
    """'image' | 'video' | 'file' بر اساس پسوند فایل."""
    ext = os.path.splitext(str(filename or ''))[1].lower()
    if ext in IMAGE_EXT:
        return 'image'
    if ext in VIDEO_EXT:
        return 'video'
    return 'file'


class SendError(Exception):
    """خطای ارسال؛ متن آن برای نمایش به ادمین امن است (توکن در آن وجود ندارد)."""


def _mask(text, token):
    text = str(text)
    return text.replace(token, '***') if token else text


# ------------------------------------------------------------------ ارسال‌کننده‌ها

class BaseSender:
    def __init__(self, token, chat_id, proxy=''):
        self.token = (token or '').strip()
        self.chat_id = str(chat_id or '').strip()
        self.session = requests.Session()
        proxy = (proxy or '').strip()
        if proxy:
            self.session.proxies = {'http': proxy, 'https': proxy}

    def _request(self, method, url, **kw):
        try:
            return self.session.request(method, url, **kw)
        except requests.RequestException as e:
            raise SendError(_mask(f'خطای شبکه ({e.__class__.__name__}): {str(e)[:160]}', self.token))

    @staticmethod
    def _json(resp):
        try:
            return resp.json()
        except ValueError:
            raise SendError(f'پاسخ نامعتبر از سرور (HTTP {resp.status_code})')

    @staticmethod
    def _guess_mime(path):
        return mimetypes.guess_type(path)[0] or 'application/octet-stream'

    def send_text(self, text):
        raise NotImplementedError

    def send_media(self, path, kind, caption):
        raise NotImplementedError

    def check(self):
        raise NotImplementedError


class TelegramSender(BaseSender):
    api = 'https://api.telegram.org/bot{token}/{method}'
    supports_streaming = True

    def _call(self, method, data=None, files=None, timeout=(10, 60), _retry=True):
        url = self.api.format(token=self.token, method=method)
        resp = self._request('POST', url, data=data, files=files, timeout=timeout)
        js = self._json(resp)
        if js.get('ok'):
            return js
        retry_after = (js.get('parameters') or {}).get('retry_after')
        if _retry and retry_after and int(retry_after) <= 20:
            time.sleep(int(retry_after) + 1)
            for f in (files or {}).values():  # فایل را از اول بخوان
                try:
                    f[1].seek(0)
                except Exception:
                    pass
            return self._call(method, data, files, timeout, _retry=False)
        raise SendError(_mask(js.get('description') or f'خطای ناشناخته (HTTP {resp.status_code})', self.token))

    def send_text(self, text):
        self._call('sendMessage', {'chat_id': self.chat_id, 'text': text})

    def send_media(self, path, kind, caption):
        method, field = {'image': ('sendPhoto', 'photo'), 'video': ('sendVideo', 'video')}.get(
            kind, ('sendDocument', 'document'))
        data = {'chat_id': self.chat_id}
        if caption:
            data['caption'] = caption
        if kind == 'video' and self.supports_streaming:
            data['supports_streaming'] = 'true'
        with open(path, 'rb') as fh:
            files = {field: (os.path.basename(path), fh, self._guess_mime(path))}
            self._call(method, data, files, timeout=(10, 600))

    def check(self):
        js = self._call('getMe', timeout=(10, 20))
        user = (js.get('result') or {}).get('username')
        return f'ربات @{user} متصل است' if user else 'ربات متصل است'


class BaleSender(TelegramSender):
    api = 'https://tapi.bale.ai/bot{token}/{method}'
    supports_streaming = False


class EitaaSender(BaseSender):
    api = 'https://eitaayar.ir/api/{token}/{method}'

    def _parse(self, resp):
        js = self._json(resp)
        ok = js.get('ok')
        if ok is None:
            ok = str(js.get('status', '')).upper() == 'OK' or (resp.status_code == 200 and 'error' not in js)
        if ok in (True, 1, 'true', 'True'):
            return js
        raise SendError(_mask(js.get('description') or js.get('message') or js.get('error')
                              or f'خطای ناشناخته (HTTP {resp.status_code})', self.token))

    def send_text(self, text):
        url = self.api.format(token=self.token, method='sendMessage')
        self._parse(self._request('POST', url, data={'chat_id': self.chat_id, 'text': text}, timeout=(10, 60)))

    def send_media(self, path, kind, caption):
        # ایتایار همه‌ی رسانه‌ها را با sendFile می‌گیرد (عکس/فیلم بر اساس پسوند فایل نمایش داده می‌شود)
        url = self.api.format(token=self.token, method='sendFile')
        data = {'chat_id': self.chat_id}
        if caption:
            data['caption'] = caption
        with open(path, 'rb') as fh:
            files = {'file': (os.path.basename(path), fh, self._guess_mime(path))}
            self._parse(self._request('POST', url, data=data, files=files, timeout=(10, 600)))

    def check(self):
        url = self.api.format(token=self.token, method='getMe')
        self._parse(self._request('GET', url, timeout=(10, 20)))
        return 'ربات ایتا متصل است'


class RubikaSender(BaseSender):
    api = 'https://botapi.rubika.ir/v3/{token}/{method}'
    _TYPES = {'image': 'Image', 'video': 'Video', 'file': 'File'}

    def _call(self, method, payload=None, timeout=(10, 60)):
        url = self.api.format(token=self.token, method=method)
        js = self._json(self._request('POST', url, json=payload or {}, timeout=timeout))
        if str(js.get('status', '')).upper() != 'OK':
            raise SendError(_mask(f"روبیکا: {js.get('status') or js.get('message') or 'خطای ناشناخته'}", self.token))
        return js

    def send_text(self, text):
        self._call('sendMessage', {'chat_id': self.chat_id, 'text': text})

    def send_media(self, path, kind, caption):
        ftype = self._TYPES.get(kind, 'File')
        try:
            up = self._call('requestSendFile', {'type': ftype})
        except SendError:
            if ftype != 'Video':
                raise
            up = self._call('requestSendFile', {'type': 'File'})  # اگر نوع Video پذیرفته نشد، به‌صورت فایل
        upload_url = (up.get('data') or {}).get('upload_url')
        if not upload_url:
            raise SendError('روبیکا آدرس آپلود نداد')
        with open(path, 'rb') as fh:
            files = {'file': (os.path.basename(path), fh, self._guess_mime(path))}
            resp = self._request('POST', upload_url, files=files, timeout=(10, 600))
        js = self._json(resp)
        file_id = (js.get('data') or {}).get('file_id') or js.get('file_id')
        if not file_id:
            raise SendError('آپلود فایل در روبیکا ناموفق بود')
        payload = {'chat_id': self.chat_id, 'file_id': file_id}
        if caption:
            payload['text'] = caption
        self._call('sendFile', payload)

    def check(self):
        js = self._call('getMe', {}, timeout=(10, 20))
        data = js.get('data') or {}
        bot = data.get('bot') or data
        name = bot.get('username') or bot.get('bot_title')
        return f'ربات روبیکا ({name}) متصل است' if name else 'ربات روبیکا متصل است'


SENDERS = {
    'telegram': TelegramSender,
    'bale': BaleSender,
    'eitaa': EitaaSender,
    'rubika': RubikaSender,
}


def make_sender(platform, token, chat_id, proxy=''):
    return SENDERS[platform](token, chat_id, proxy)


# ------------------------------------------------------------------ ساخت آیتم‌های ارسال

def build_items(text, media):
    """text: متن اصلی پست. media: لیست آبجکت‌هایی با path / media_type / caption.

    قاعده: اگر فقط یک رسانه‌ی بدون توضیح داریم و متن اصلی هم هست (و کوتاه است)، متن همان توضیح رسانه می‌شود
    (مثل خود پیام‌رسان‌ها). در غیر این صورت متن اصلی اول جداگانه می‌رود و هر رسانه با توضیح خودش."""
    text = (text or '').strip()
    items = []
    if not media:
        if text:
            items.append({'kind': 'text', 'text': text})
        return items
    if text and len(media) == 1 and not (media[0].caption or '').strip() and len(text) <= CAPTION_LIMIT:
        m = media[0]
        return [{'kind': 'media', 'path': m.path, 'media_type': m.media_type, 'caption': text}]
    if text:
        items.append({'kind': 'text', 'text': text})
    for m in media:
        items.append({'kind': 'media', 'path': m.path, 'media_type': m.media_type,
                      'caption': (m.caption or '').strip()})
    return items


def _deliver(cfg, items):
    """کار شبکه‌ای برای یک کانال (بدون دسترسی به دیتابیس). خروجی: (تعداد موفق، لیست خطاها)."""
    sender = make_sender(cfg['platform'], cfg['token'], cfg['chat_id'], cfg.get('proxy', ''))
    sent, errors = 0, []
    for i, it in enumerate(items):
        try:
            if it['kind'] == 'text':
                sender.send_text(it['text'])
            else:
                sender.send_media(it['path'], it['media_type'], it['caption'])
            sent += 1
        except SendError as e:
            errors.append(f'مورد {i + 1}: {e}')
        except FileNotFoundError:
            errors.append(f'مورد {i + 1}: فایل روی سرور پیدا نشد')
        except Exception as e:  # خطای پیش‌بینی‌نشده نباید بقیه‌ی کانال‌ها را متوقف کند
            log.exception('social send failed')
            errors.append(_mask(f'مورد {i + 1}: {e.__class__.__name__}: {str(e)[:150]}', cfg['token']))
        if i < len(items) - 1:
            time.sleep(0.6)
    return sent, errors


# ------------------------------------------------------------------ ارسال یک پست (با دیتابیس)

class _MediaView:
    def __init__(self, m):
        self.path = m.file.path
        self.media_type = m.media_type
        self.caption = m.caption


def send_post(post_id, only_failed=False):
    """پست را به کانال‌های هدف می‌فرستد و نتیجه را در SocialDelivery می‌نویسد."""
    from django.utils import timezone
    from .models import SocialPost, SocialDelivery

    post = SocialPost.objects.get(pk=post_id)
    channels = post.target_channels()
    if only_failed:
        done = set(post.deliveries.filter(status='ok').values_list('channel_id', flat=True))
        channels = [c for c in channels if c.pk not in done]

    items = build_items(post.text, [_MediaView(m) for m in post.media.all()])
    if not items or not channels:
        post.status = 'failed'
        post.save(update_fields=['status'])
        return

    cfgs = [{'pk': c.pk, 'platform': c.platform, 'token': c.bot_token, 'chat_id': c.chat_id,
             'proxy': c.proxy_url} for c in channels]
    with ThreadPoolExecutor(max_workers=min(4, len(cfgs))) as pool:
        results = list(pool.map(lambda cfg: _deliver(cfg, items), cfgs))

    for cfg, (sent, errors) in zip(cfgs, results):
        status = 'ok' if sent == len(items) else ('partial' if sent else 'failed')
        SocialDelivery.objects.update_or_create(
            post=post, channel_id=cfg['pk'],
            defaults={'status': status, 'sent_count': sent, 'total_count': len(items),
                      'detail': '\n'.join(errors)[:2000]})

    statuses = set(post.deliveries.values_list('status', flat=True))
    if statuses == {'ok'}:
        post.status = 'sent'
    elif statuses & {'ok', 'partial'}:
        post.status = 'partial'
    else:
        post.status = 'failed'
    post.sent_at = timezone.now()
    post.save(update_fields=['status', 'sent_at'])


def send_post_async(post_id, only_failed=False):
    """ارسال در پس‌زمینه تا صفحه‌ی ادمین برای آپلود فیلم‌های سنگین منتظر نماند."""
    def run():
        from django.db import connection
        try:
            send_post(post_id, only_failed)
        except Exception:
            log.exception('send_post crashed')
            try:
                from .models import SocialPost
                SocialPost.objects.filter(pk=post_id).update(status='failed')
            except Exception:
                pass
        finally:
            connection.close()

    threading.Thread(target=run, daemon=True).start()


# ------------------------------------------------------------------ تست کانال

def check_channel(channel):
    """فقط اتصال و اعتبار توکن را بررسی می‌کند. خروجی: (ok, پیام)."""
    try:
        sender = make_sender(channel.platform, channel.bot_token, channel.chat_id, channel.proxy_url)
        return True, sender.check()
    except SendError as e:
        return False, str(e)
    except Exception as e:
        return False, _mask(f'{e.__class__.__name__}: {str(e)[:150]}', channel.bot_token)


def send_test_message(channel):
    """یک پیام آزمایشی به خود کانال می‌فرستد (شناسه‌ی کانال و دسترسی ربات هم تست می‌شود)."""
    try:
        sender = make_sender(channel.platform, channel.bot_token, channel.chat_id, channel.proxy_url)
        sender.send_text('✅ پیام آزمایشی از پنل مدیریت فروشگاه')
        return True, 'پیام آزمایشی ارسال شد'
    except SendError as e:
        return False, str(e)
    except Exception as e:
        return False, _mask(f'{e.__class__.__name__}: {str(e)[:150]}', channel.bot_token)
