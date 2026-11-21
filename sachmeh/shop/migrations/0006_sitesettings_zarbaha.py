from django.db import migrations, models


def _key(name, label):
    return migrations.AddField(
        model_name='sitesettings', name=name,
        field=models.CharField(blank=True, default='', max_length=60, verbose_name=label),
    )


class Migration(migrations.Migration):

    dependencies = [
        ('shop', '0005_sitesettings_img_turquoise'),
    ]

    operations = [
        migrations.AddField(
            model_name='sitesettings', name='zarbaha_enabled',
            field=models.BooleanField(default=False, verbose_name='دریافت خودکار نرخ از زربها فعال باشد'),
        ),
        migrations.AddField(
            model_name='sitesettings', name='zarbaha_username',
            field=models.CharField(blank=True, default='', max_length=100, verbose_name='نام کاربری زربها'),
        ),
        migrations.AddField(
            model_name='sitesettings', name='zarbaha_password',
            field=models.CharField(blank=True, default='', max_length=100, verbose_name='رمز عبور زربها'),
        ),
        migrations.AddField(
            model_name='sitesettings', name='zarbaha_interval_minutes',
            field=models.PositiveIntegerField(default=5, help_text='طبق قوانین زربها کمتر از ۵ دقیقه مجاز نیست؛ عدد کمتر از ۵ خودکار ۵ حساب می‌شود.', verbose_name='فاصله‌ی دریافت نرخ (دقیقه)'),
        ),
        migrations.AddField(
            model_name='sitesettings', name='zarbaha_multiplier',
            field=models.DecimalField(decimal_places=4, default=1, help_text='اگر زربها نرخ را به\u200cصورت «هزار تومان» می\u200cدهد ۱۰۰۰ بگذارید؛ اگر تومان می\u200cدهد ۱.', max_digits=10, verbose_name='ضریب تبدیل نرخ به تومان'),
        ),
        _key('zarbaha_key_shot_995', 'ساچمه ۹۹۵ — هر گرم'),
        _key('zarbaha_key_shot_9999', 'ساچمه ۹۹۹.۹ — هر گرم'),
        _key('zarbaha_key_silver_bar_1000', 'شمش نقره ۱۰۰۰ گرمی'),
        _key('zarbaha_key_silver_bar_500', 'شمش نقره ۵۰۰ گرمی'),
        _key('zarbaha_key_silver_bar_100', 'شمش نقره ۱۰۰ گرمی'),
        _key('zarbaha_key_silver_bar_50', 'شمش نقره ۵۰ گرمی'),
        _key('zarbaha_key_copper_bar_1000', 'شمش مس ۱۰۰۰ گرمی'),
        _key('zarbaha_key_copper_bar_500', 'شمش مس ۵۰۰ گرمی'),
        _key('zarbaha_key_copper_bar_100', 'شمش مس ۱۰۰ گرمی'),
        _key('zarbaha_key_copper_bar_50', 'شمش مس ۵۰ گرمی'),
        migrations.AddField(
            model_name='sitesettings', name='zarbaha_token',
            field=models.TextField(blank=True, default='', editable=False),
        ),
        migrations.AddField(
            model_name='sitesettings', name='zarbaha_token_at',
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='sitesettings', name='zarbaha_last_attempt',
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='sitesettings', name='zarbaha_last_status',
            field=models.CharField(blank=True, default='', editable=False, max_length=300),
        ),
        migrations.AddField(
            model_name='sitesettings', name='zarbaha_last_data',
            field=models.TextField(blank=True, default='', editable=False),
        ),
    ]
