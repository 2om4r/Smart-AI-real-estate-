# extensions.py — Shared Flask extensions (db, login, rate limiter)
# امتدادات Flask المشتركة: قاعدة البيانات، تسجيل الدخول، تحديد معدل الطلبات

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# ─── Database ────────────────────────────────────────────────────────────────
# قاعدة البيانات والهجرات
db = SQLAlchemy()
migrate = Migrate()

# ─── Authentication ───────────────────────────────────────────────────────────
# مدير تسجيل الدخول — يعيد توجيه المستخدم غير المسجل إلى صفحة الدخول
login_manager = LoginManager()
login_manager.login_view = 'main.login'
login_manager.login_message_category = 'info'

# ─── Rate Limiter ─────────────────────────────────────────────────────────────
# تحديد معدل الطلبات بناءً على عنوان IP للحماية من الإساءة
# get_remote_address: يستخدم IP العميل كمفتاح للتتبع
# default_limits: الحد الافتراضي لجميع المسارات (يمكن تجاوزه لكل مسار)
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",   # في الإنتاج استبدلها بـ redis://localhost:6379
)
