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

# ─── ML Auto-Retrain Scheduler ────────────────────────────────────────────────
# مُجَدوِل خلفيّ يُشَغِّل إعادة تدريب نموذج ML تلقائياً
# Background scheduler that runs ML retraining on a schedule
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler(daemon=True)


def init_scheduler(app):
    """
    Initialize the background scheduler with two jobs:

      1. Weekly retrain — every Sunday at 2 AM (light load)
      2. Threshold check — every hour, retrain if >100 new properties

    Both run inside Flask app_context so DB queries work.
    """
    import logging
    log = logging.getLogger('scheduler')

    if scheduler.running:
        log.info("[Scheduler] Already running, skipping init")
        return

    def _run_retrain(trigger_source: str):
        """Wrapper that runs retrain inside app context."""
        with app.app_context():
            try:
                from scripts.ml_pipeline import run
                result = run(trigger=trigger_source)
                log.info(f"[Scheduler] {trigger_source} retrain: {result.get('status')}")
            except Exception as e:
                log.error(f"[Scheduler] {trigger_source} retrain failed: {e}")

    # Job 1: Weekly cron — Sunday 2 AM
    scheduler.add_job(
        func=lambda: _run_retrain('scheduled'),
        trigger='cron', day_of_week='sun', hour=2, minute=0,
        id='weekly_retrain',
        replace_existing=True,
        misfire_grace_time=3600,   # 1h grace period if app was down
    )

    # Job 2: Threshold check — every hour
    scheduler.add_job(
        func=lambda: _run_retrain('threshold'),
        trigger='interval', hours=1,
        id='threshold_check',
        replace_existing=True,
    )

    # Job 3: Daily backup of model registry — 3 AM (after weekly retrain finishes)
    def _run_backup():
        with app.app_context():
            try:
                from scripts.backup_models import run as backup_run
                result = backup_run()
                log.info(f"[Scheduler] Backup: {result}")
            except Exception as e:
                log.error(f"[Scheduler] Backup failed: {e}")

    scheduler.add_job(
        func=_run_backup,
        trigger='cron', hour=3, minute=0,
        id='daily_backup',
        replace_existing=True,
    )

    scheduler.start()
    log.info("[Scheduler] Started: weekly_retrain (Sun 2am) + "
             "threshold_check (hourly) + daily_backup (3am)")
