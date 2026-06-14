
from flask import (Blueprint, render_template, url_for, flash,
                   redirect, request, jsonify, current_app, session)
from flask_login import login_user, current_user, logout_user, login_required
from sqlalchemy import func
from datetime import datetime, timedelta

from extensions import db, limiter
from models import (User, Property, Favorite, Area, PropertyImage,
                    Message, Inquiry, RecentlyViewed, Notification,
                    ChatLog, ChatFeedback, Conversation, InvestmentRequest)
from forms import (RegistrationForm, LoginForm, PropertyForm,
                   SettingsProfileForm, SettingsSecurityForm,
                   SettingsPreferencesForm, ProjectForm, UnitForm)
from ai_utils import (get_ai_response, recommend_investment,
                      portfolio_summary, calculate_score, get_roi_assumption)
import os
import uuid
from ml_engine import ml
from ml_engine import get_future_multiplier, get_ml_investment_score
from firebase import db as firebase_db
import pyotp
import qrcode
import base64
import io

from firebase import db as firebase_db

main = Blueprint('main', __name__)

def _rag_update(property_id: int) -> None:
    
    try:
        from rag_engine import update_property_in_rag
        update_property_in_rag(property_id)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[RAG] update skipped for property {property_id}: {e}")

def _rag_delete(property_id: int) -> None:
    
    try:
        from rag_engine import delete_property_from_rag
        delete_property_from_rag(property_id)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[RAG] delete skipped for property {property_id}: {e}")

@main.route("/api/chat", methods=["POST"])
@limiter.limit("10 per minute")   
def chat_api():
    
    data            = request.get_json()
    message         = data.get("message", "")
    conversation_id = data.get("conversation_id")   

    user_id = current_user.id if current_user.is_authenticated else None

    try:
        
        reply = get_ai_response(message,
                                user_id=user_id,
                                conversation_id=conversation_id)
        return jsonify(reply)

    except Exception as e:
        current_app.logger.error(f"[chat_api] {e}")
        is_arabic = any('؀' <= c <= 'ۿ' for c in message)
        return jsonify({
            "text": "صار خطأ في السيرفر، حاول مجددًا." if is_arabic
                    else "Server error — please try again.",
            "properties": [],
            "conversation_id": conversation_id
        }), 500

@main.route("/api/chat/feedback", methods=["POST"])
def chat_feedback():
    
    data        = request.get_json()
    chat_log_id = data.get("chat_log_id")
    rating      = data.get("rating")
    comment     = data.get("comment", "")

    if chat_log_id is None or rating not in (0, 1):
        return jsonify({"error": "chat_log_id and rating (0 or 1) are required"}), 400

    log = ChatLog.query.get(chat_log_id)
    if not log:
        return jsonify({"error": "Chat log not found"}), 404

    if log.feedback:
        log.feedback.rating  = rating
        log.feedback.comment = comment
        log.feedback.timestamp = datetime.utcnow()
    else:
        feedback = ChatFeedback(
            chat_log_id=chat_log_id,
            rating=rating,
            comment=comment
        )
        db.session.add(feedback)

    db.session.commit()
    return jsonify({"status": "saved", "chat_log_id": chat_log_id, "rating": rating})

@main.route("/api/admin/chat-analytics")
@login_required
def chat_analytics():
    
    if current_user.role != 'admin':
        return jsonify({"error": "Admin access required"}), 403

    since = datetime.utcnow() - timedelta(hours=24)
    logs  = ChatLog.query.filter(ChatLog.timestamp >= since).all()

    total_chats = len(logs)

    rt_values = [l.response_time for l in logs if l.response_time is not None]
    avg_response_time = round(sum(rt_values) / len(rt_values), 2) if rt_values else 0

    tk_values = [l.tokens_used for l in logs if l.tokens_used is not None]
    avg_tokens = round(sum(tk_values) / len(tk_values), 1) if tk_values else 0

    total_tokens = sum(tk_values)
    daily_cost   = round(total_tokens * 0.000002, 4)

    intent_counts = {}
    for log in logs:
        key = log.intent or "unknown"
        intent_counts[key] = intent_counts.get(key, 0) + 1

    location_keywords = [
        "muscat", "مسقط", "salalah", "صلالة", "barka", "بركاء",
        "sohar", "صحار", "nizwa", "نزوى", "sur", "صور",
        "duqm", "دقم", "rustaq", "الرستاق"
    ]
    location_map = {   
        "muscat": "Muscat", "مسقط": "Muscat",
        "salalah": "Salalah", "صلالة": "Salalah",
        "barka": "Barka", "بركاء": "Barka",
        "sohar": "Sohar", "صحار": "Sohar",
        "nizwa": "Nizwa", "نزوى": "Nizwa",
        "sur": "Sur", "صور": "Sur",
        "duqm": "Duqm", "دقم": "Duqm",
        "rustaq": "Rustaq", "الرستاق": "Rustaq",
    }
    loc_counts = {}
    for log in logs:
        msg_lower = (log.user_message or "").lower()
        for kw in location_keywords:
            if kw in msg_lower:
                canonical = location_map.get(kw, kw.title())
                loc_counts[canonical] = loc_counts.get(canonical, 0) + 1

    top_locations = sorted(
        [{"location": k, "count": v} for k, v in loc_counts.items()],
        key=lambda x: x["count"], reverse=True
    )[:5]

    all_feedback = ChatFeedback.query.filter(
        ChatFeedback.timestamp >= since
    ).all()
    positive       = sum(1 for f in all_feedback if f.rating == 1)
    satisfaction   = round((positive / len(all_feedback)) * 100, 1) if all_feedback else None

    return jsonify({
        "period":            "last_24h",
        "total_chats":       total_chats,
        "avg_response_time": avg_response_time,   
        "avg_tokens":        avg_tokens,
        "daily_cost_usd":    daily_cost,
        "intent_breakdown":  intent_counts,
        "top_locations":     top_locations,
        "satisfaction_rate": satisfaction,         
        "total_feedback":    len(all_feedback),
    })

@main.route("/api/areas")
def api_areas():
    areas = Area.query.all()
    return jsonify([a.to_dict() for a in areas])

@main.route("/api/surooh_projects")
def api_surooh_projects():
    props = Property.query.filter_by(is_surooh=True).all()
    return jsonify([p.to_dict() for p in props])

@main.route("/api/omran_properties")
def api_omran_properties():
    props = Property.query.filter_by(is_omran=True).all()
    return jsonify([p.to_dict() for p in props])

@main.route("/healthz")
def healthz():
    
    checks = {}
    degraded = False
    unhealthy = False

    try:
        db.session.execute(db.text("SELECT 1"))
        checks['db'] = {'status': 'ok'}
    except Exception as e:
        checks['db'] = {'status': 'error', 'error': str(e)[:100]}
        unhealthy = True   

    try:
        from ml_engine import ml
        status = ml.status()
        if status.get('loaded'):
            checks['ml'] = {
                'status':       'ok',
                'version':      status.get('version'),
                'trees':        status.get('trees'),
                'cache_size':   status.get('cache_size'),
                'hit_rate_pct': status.get('cache_hit_rate'),
            }
        else:
            checks['ml'] = {'status': 'degraded', 'reason': 'model not loaded'}
            degraded = True
    except Exception as e:
        checks['ml'] = {'status': 'error', 'error': str(e)[:100]}
        degraded = True

    try:
        from rag_engine import search_knowledge_base
        
        checks['rag'] = {'status': 'ok'}
    except Exception as e:
        checks['rag'] = {'status': 'unknown', 'error': str(e)[:100]}

    try:
        from extensions import scheduler
        if scheduler.running:
            jobs = scheduler.get_jobs()
            checks['scheduler'] = {
                'status': 'ok',
                'jobs':   [j.id for j in jobs],
            }
        else:
            checks['scheduler'] = {'status': 'degraded', 'reason': 'not running'}
            degraded = True
    except Exception as e:
        checks['scheduler'] = {'status': 'unknown', 'error': str(e)[:100]}

    if unhealthy:    overall = 'unhealthy'
    elif degraded:   overall = 'degraded'
    else:            overall = 'healthy'

    import time as _t
    uptime = _t.time() - current_app.config.get('APP_START_TS', _t.time())

    resp = {
        'status':     overall,
        'checks':     checks,
        'uptime_s':   round(uptime, 1),
        'timestamp':  datetime.utcnow().isoformat(),
    }
    code = 200 if overall != 'unhealthy' else 503
    return jsonify(resp), code

@main.route("/admin/ml-monitor")
@login_required
def admin_ml_monitor():
    
    if current_user.role != 'admin':
        flash('Admin access required.', 'danger')
        return redirect(url_for('main.dashboard'))
    return render_template('ml_monitor.html')

@main.route("/api/ml/history")
@login_required
def api_ml_history():
    
    if current_user.role != 'admin':
        return jsonify({'error': 'admin only'}), 403

    from models import TrainingHistory
    history = (TrainingHistory.query
               .order_by(TrainingHistory.trained_at.desc())
               .limit(50)
               .all())
    return jsonify([h.to_dict() for h in history])

@main.route("/api/ml/retrain", methods=['POST'])
@login_required
@limiter.limit("3 per hour")
def api_ml_retrain():
    
    if current_user.role != 'admin':
        return jsonify({'error': 'admin only'}), 403

    data = request.get_json() or {}
    try:
        from scripts.ml_pipeline import run
        result = run(
            force    = bool(data.get('force', True)),    
            dry_run  = bool(data.get('dry_run', False)),
            min_new  = int(data.get('min_new', 100)),
            min_days = int(data.get('min_days', 7)),
            trigger  = 'manual',
        )
        return jsonify(result)
    except Exception as e:
        logger.error(f"[ML] Manual retrain failed: {e}")
        return jsonify({'error': str(e), 'status': 'failed'}), 500

@main.route("/api/ml/rollback", methods=['POST'])
@login_required
@limiter.limit("10 per hour")
def api_ml_rollback():
    
    if current_user.role != 'admin':
        return jsonify({'error': 'admin only'}), 403

    from models import TrainingHistory
    from extensions import db as _db
    from ml_engine import ml
    import os

    data = request.get_json() or {}

    target = None
    if 'history_id' in data:
        target = TrainingHistory.query.get(int(data['history_id']))
    elif 'version' in data:
        target = TrainingHistory.query.filter_by(
            version=data['version']
        ).first()

    if not target:
        return jsonify({'error': 'version not found'}), 404
    if not target.model_path or not os.path.exists(target.model_path):
        return jsonify({
            'error': f'pickle file missing: {target.model_path}'
        }), 404

    success = ml.hot_swap(target.model_path)
    if not success:
        return jsonify({'error': 'hot_swap_failed'}), 500

    TrainingHistory.query.update({'is_active': False})
    target.is_active = True
    _db.session.commit()

    return jsonify({
        'status':       'rolled_back',
        'now_active':   target.to_dict(),
        'engine_status': ml.status(),
    })

@main.route("/api/ml/status")
def api_ml_status():
    
    try:
        from ml_engine import ml
        return jsonify(ml.status())
    except Exception as e:
        return jsonify({'error': str(e), 'loaded': False}), 500

@main.route("/api/ml/predict", methods=['POST'])
@limiter.limit("30 per minute")
def api_ml_predict():
    
    try:
        from ml_engine import ml
        data = request.get_json() or {}
        years = data.pop('years', None)

        if years:
            return jsonify(ml.predict_growth(data, years=int(years)))
        return jsonify(ml.predict_price(data))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@main.route("/api/properties")
def api_properties():
    query = Property.query
    if request.args.get('flagged') == '1':
        query = query.filter_by(flagged_anomaly=True)
    properties = query.all()
    
    return jsonify([{
        'id': p.id,
        'title': p.title,
        'location': p.location,
        'price': p.price,
        'flagged_anomaly': p.flagged_anomaly,
        'anomaly_severity': getattr(p, 'anomaly_severity', 'low'),
        'anomaly_reason': getattr(p, 'anomaly_reason', '')
    } for p in properties])

@main.route("/api/projects")
def api_projects():
    
    projects = Property.query.filter_by(is_project=True).all()

    out = []
    for p in projects:
        
        units_count = Property.query.filter_by(parent_project_id=p.id).count()

        try:
            from ml_model import get_future_multiplier
            mult_5y = get_future_multiplier(p.location, 5)
            growth_pct = round((mult_5y - 1) * 100, 1)
        except Exception:
            growth_pct = None

        out.append({
            'id':              p.id,
            'title':           p.title,
            'location':        p.location,
            'city':            p.city,
            'developer':       p.developer,
            'completion_date': p.completion_date,
            'starting_price':  p.price,
            'total_units':     p.total_units,
            'units_added':     units_count,
            'status':          p.status,
            'description':     p.description[:200] if p.description else '',
            'lat':             p.latitude,
            'lng':             p.longitude,
            'is_project':      True,
            'projected_5y_growth_pct': growth_pct,    
            'agent':           p.agent.username if p.agent else 'unknown',
            'detail_url':      url_for('main.project_detail', project_id=p.id),
        })
    return jsonify(out)

@main.route("/")
@main.route("/home")
def home():
    properties = Property.query.order_by(Property.created_at.desc()).limit(6).all()
    return render_template('home.html', title='Home', properties=properties)

@main.route("/about")
def about():
    return render_template('about.html', title='About')

@main.route("/investment-map")
def investment_map():
    return render_template("investment_map.html")

@main.route("/ahmed-chat")
def ahmed_chat():
    return render_template("ahmed_chat.html", title="Ahmed 2.0 — AI Advisor")

@main.route("/analytics")
def analytics():
    from sqlalchemy import func as sqlfunc
    total_properties = Property.query.count()
    total_users      = User.query.count()
    total_agents     = User.query.filter_by(role='agent').count()

    type_counts = db.session.query(
        Property.type, sqlfunc.count(Property.id)
    ).group_by(Property.type).all()
    type_labels = [t[0] for t in type_counts]
    type_values = [t[1] for t in type_counts]

    city_counts = db.session.query(
        Property.city, sqlfunc.count(Property.id)
    ).filter(Property.city.isnot(None)).group_by(Property.city)     .order_by(sqlfunc.count(Property.id).desc()).limit(6).all()
    city_labels = [c[0] or 'Unknown' for c in city_counts]
    city_values = [c[1] for c in city_counts]

    avg_price = db.session.query(sqlfunc.avg(Property.price)).scalar() or 0

    recent = Property.query.order_by(Property.created_at.desc()).limit(6).all()

    return render_template(
        "analytics.html",
        title="Analytics",
        total_properties=total_properties,
        total_users=total_users,
        total_agents=total_agents,
        type_labels=type_labels,
        type_values=type_values,
        city_labels=city_labels,
        city_values=city_values,
        avg_price=avg_price,
        recent=recent,
    )

@main.route("/register", methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))

    form = RegistrationForm()

    if request.method == 'POST' and form.validate_on_submit():
        user = User(
            username=form.username.data,
            email=form.email.data,
            role=form.role.data
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()

        firebase_db.collection("users").add({
            "username": user.username,
            "email":    user.email,
            "role":     user.role
        })

        flash('Account created!', 'success')
        return redirect(url_for('main.login'))

    return render_template('register.html', title='Register', form=form)

@main.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))

    form = LoginForm()

    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        
        if user:
            if user.lockout_until and user.lockout_until > datetime.utcnow():
                remaining = (user.lockout_until - datetime.utcnow()).total_seconds() // 60
                flash(f'Account locked due to too many failed attempts. Try again in {int(remaining)} minutes.', 'danger')
                return render_template('login.html', title='Login', form=form)

        if user and user.check_password(form.password.data):
            user.failed_logins = 0
            user.lockout_until = None
            db.session.commit()

            if getattr(user, 'mfa_enabled', False):
                session['mfa_user_id'] = user.id
                return redirect(url_for('main.verify_mfa'))

            login_user(user)
            return redirect(url_for('main.home'))
        else:
            if user:
                user.failed_logins = getattr(user, 'failed_logins', 0) + 1
                if user.failed_logins >= 5:
                    user.lockout_until = datetime.utcnow() + timedelta(minutes=30)
                    flash('Account locked due to too many failed attempts. Try again in 30 minutes.', 'danger')
                else:
                    flash(f'Login failed. {5 - user.failed_logins} attempts remaining.', 'danger')
                db.session.commit()
            else:
                flash('Login failed', 'danger')

    return render_template('login.html', title='Login', form=form)


@main.route("/verify_mfa", methods=['GET', 'POST'])
def verify_mfa():
    from forms import MFAVerifyForm
    user_id = session.get('mfa_user_id')
    if not user_id:
        return redirect(url_for('main.login'))

    user = User.query.get(user_id)
    if not user:
        return redirect(url_for('main.login'))

    form = MFAVerifyForm()
    if form.validate_on_submit():
        totp = pyotp.TOTP(user.mfa_secret)
        if totp.verify(form.token.data):
            login_user(user)
            session.pop('mfa_user_id', None)
            flash('Login successful', 'success')
            return redirect(url_for('main.home'))
        else:
            flash('Invalid 6-digit token.', 'danger')

    return render_template('verify_mfa.html', title='Verify MFA', form=form)

@main.route("/settings/mfa/setup", methods=['GET', 'POST'])
@login_required
def setup_mfa():
    from forms import MFAVerifyForm
    if current_user.mfa_enabled:
        flash('MFA is already enabled.', 'info')
        return redirect(url_for('main.settings'))
        
    if 'mfa_temp_secret' not in session:
        session['mfa_temp_secret'] = pyotp.random_base32()
        
    secret = session['mfa_temp_secret']
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(name=current_user.email, issuer_name="SmartRealEstate")
    
    # Generate QR Code
    qr = qrcode.make(provisioning_uri)
    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    
    form = MFAVerifyForm()
    if form.validate_on_submit():
        if totp.verify(form.token.data):
            current_user.mfa_secret = secret
            current_user.mfa_enabled = True
            db.session.commit()
            session.pop('mfa_temp_secret', None)
            flash('MFA has been successfully enabled!', 'success')
            return redirect(url_for('main.settings'))
        else:
            flash('Invalid 6-digit token.', 'danger')
            
    return render_template('setup_mfa.html', form=form, qr_b64=qr_b64, secret=secret)

@main.route("/settings/mfa/disable", methods=['POST'])
@login_required
def disable_mfa():
    current_user.mfa_enabled = False
    current_user.mfa_secret = None
    db.session.commit()
    flash('MFA has been disabled.', 'success')
    return redirect(url_for('main.settings'))


@main.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('main.home'))

@main.route("/settings", methods=['GET', 'POST'])
@login_required
def settings():
    profile_form     = SettingsProfileForm()
    security_form    = SettingsSecurityForm()
    preferences_form = SettingsPreferencesForm()

    if request.method == 'POST':
        if 'submit_profile' in request.form and profile_form.validate_on_submit():
            current_user.full_name = profile_form.full_name.data
            current_user.phone     = profile_form.phone.data

            if profile_form.profile_image.data:
                img      = profile_form.profile_image.data
                ext      = img.filename.rsplit('.', 1)[-1].lower()
                filename = f"user_{current_user.id}_{uuid.uuid4().hex[:8]}.{ext}"
                upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'profiles')
                os.makedirs(upload_dir, exist_ok=True)
                img.save(os.path.join(upload_dir, filename))
                current_user.profile_image = filename

            db.session.commit()
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('main.settings'))

        elif 'submit_security' in request.form and security_form.validate_on_submit():
            if current_user.check_password(security_form.current_password.data):
                current_user.set_password(security_form.new_password.data)
                db.session.commit()
                flash('Password updated successfully!', 'success')
            else:
                flash('Incorrect current password.', 'danger')
            return redirect(url_for('main.settings'))

        elif 'submit_preferences' in request.form and preferences_form.validate_on_submit():
            current_user.preferred_language = preferences_form.preferred_language.data
            current_user.theme_mode         = preferences_form.theme_mode.data
            db.session.commit()
            flash('Preferences updated successfully!', 'success')
            return redirect(url_for('main.settings'))

    if request.method == 'GET':
        profile_form.full_name.data             = current_user.full_name
        profile_form.phone.data                 = current_user.phone
        preferences_form.preferred_language.data = current_user.preferred_language or 'en'
        preferences_form.theme_mode.data         = current_user.theme_mode or 'light'

    return render_template('settings.html',
                           title='Settings',
                           profile_form=profile_form,
                           security_form=security_form,
                           preferences_form=preferences_form)

@main.route("/set_language/<lang>")
def set_language(lang):
    if lang in ['en', 'ar']:
        if current_user.is_authenticated:
            current_user.preferred_language = lang
            db.session.commit()
        else:
            session['language'] = lang
    return redirect(request.referrer or url_for('main.home'))

@main.route("/set_theme/<theme>")
def set_theme(theme):
    if theme in ['light', 'dark']:
        if current_user.is_authenticated:
            current_user.theme_mode = theme
            db.session.commit()
        else:
            session['theme'] = theme
    return redirect(request.referrer or url_for('main.home'))

@main.route("/property/<int:property_id>/delete", methods=["POST"])
@login_required
def delete_property(property_id):
    prop = Property.query.get_or_404(property_id)

    if prop.agent_id != current_user.id and current_user.role != 'admin':
        flash("You are not authorized to delete this property.", "danger")
        return redirect(url_for('main.dashboard'))

    try:
        upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'properties')
        for img in prop.images:
            filepath = os.path.join(upload_dir, img.image_filename)
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except Exception:
                    pass

        RecentlyViewed.query.filter_by(property_id=prop.id).delete()
        Message.query.filter_by(property_id=prop.id).update({'property_id': None})

        _rag_delete(prop.id)

        db.session.delete(prop)
        db.session.commit()
        flash("Property deleted successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting property: {str(e)}", "danger")

    return redirect(url_for('main.dashboard'))

@main.route("/dashboard")
@login_required
def dashboard():

    if current_user.role == 'agent':
        props = Property.query.filter_by(
            agent_id=current_user.id
        ).order_by(Property.created_at.desc()).all()

        prop_dicts = [{
            'title': p.title, 'type': p.type,
            'price': p.price, 'location': p.location
        } for p in props]

        ai_rec   = recommend_investment(prop_dicts)
        pf_stats = portfolio_summary(prop_dicts)

        for p in props:
            p.predicted_price = p.price
            p.ml_score        = 60

        all_agent_msgs = Message.query.filter(
            (Message.sender_id == current_user.id) |
            (Message.receiver_id == current_user.id)
        ).order_by(Message.timestamp.asc()).all()

        agent_threads = {}
        for m in all_agent_msgs:
            other_id = m.receiver_id if m.sender_id == current_user.id else m.sender_id
            if other_id == current_user.id:
                continue
            if other_id not in agent_threads:
                other_user = User.query.get(other_id)
                agent_threads[other_id] = {
                    'user': other_user, 'messages': [],
                    'last_msg': None, 'unread': 0
                }
            agent_threads[other_id]['messages'].append(m)

        for uid, thread in agent_threads.items():
            thread['last_msg'] = thread['messages'][-1]
            thread['unread']   = sum(
                1 for m in thread['messages']
                if not m.is_read and m.receiver_id == current_user.id
            )

        agent_threads_list = sorted(
            agent_threads.values(),
            key=lambda t: t['last_msg'].timestamp, reverse=True
        )

        return render_template('dashboard_agent.html',
                               properties=props,
                               ai_rec=ai_rec,
                               pf_stats=pf_stats,
                               agent_messages=all_agent_msgs,
                               threads=agent_threads_list)

    elif current_user.role == 'admin':
        users      = User.query.order_by(User.id.desc()).limit(50).all()
        properties = Property.query.order_by(Property.created_at.desc()).limit(50).all()

        if properties:
            for p in properties:
                safe_price = p.price or 0
                p.score = calculate_score({
                    'type': p.type, 'price': safe_price, 'location': p.location
                })
                
                p.predicted_price = p.ml_predicted_at_listing or safe_price
                p.ml_score        = get_ml_investment_score(p.predicted_price, safe_price)

        return render_template('dashboard_admin.html',
                               users=users,
                               properties=properties)

    else:
        
        favorites       = Favorite.query.filter_by(user_id=current_user.id).all()
        recently_viewed = RecentlyViewed.query.filter_by(
            user_id=current_user.id
        ).order_by(RecentlyViewed.timestamp.desc()).limit(5).all()

        all_msgs = Message.query.filter(
            (Message.sender_id == current_user.id) |
            (Message.receiver_id == current_user.id)
        ).order_by(Message.timestamp.asc()).all()

        threads = {}
        for m in all_msgs:
            other_id = m.receiver_id if m.sender_id == current_user.id else m.sender_id
            if other_id not in threads:
                other_user = User.query.get(other_id)
                threads[other_id] = {
                    'user': other_user, 'messages': [],
                    'last_msg': None, 'unread': 0
                }
            threads[other_id]['messages'].append(m)

        for uid, thread in threads.items():
            thread['last_msg'] = thread['messages'][-1]
            thread['unread']   = sum(
                1 for m in thread['messages']
                if not m.is_read and m.receiver_id == current_user.id
            )

        threads_list = sorted(
            threads.values(),
            key=lambda t: t['last_msg'].timestamp, reverse=True
        )
        flat_messages = all_msgs

        pref_locs  = set()
        pref_types = set()
        for f in favorites:
            pref_locs.add(f.property.location)
            pref_types.add(f.property.type)
        for rv in recently_viewed:
            pref_locs.add(rv.property.location)
            pref_types.add(rv.property.type)

        all_props = Property.query.order_by(Property.created_at.desc()).limit(100).all()
        prices    = [float(p.price) for p in all_props if p.price]
        avg       = sum(prices) / len(prices) if prices else 100000
        for p in all_props:
            base_score = calculate_score(
                {'price': p.price, 'type': p.type, 'location': p.location}, avg
            )
            if p.location in pref_locs:  base_score += 15
            if p.type in pref_types:      base_score += 10
            p._score = base_score

        all_props.sort(key=lambda x: x._score, reverse=True)
        recommended = all_props[:6]

        for p in recommended:
            t = (p.type or '').lower()
            if 'villa'     in t: p.roi = 6.0
            elif 'apartment' in t: p.roi = 7.0
            elif 'land'      in t: p.roi = 8.0
            else:                  p.roi = 5.0
            if getattr(p, 'status', 'available') == 'under_construction':
                p.roi += 1.5
            p.yearly_income = float(p.price or 0) * (p.roi / 100.0)

        return render_template('dashboard_customer.html',
                               favorites=favorites,
                               recently_viewed=recently_viewed,
                               messages=flat_messages,
                               threads=threads_list,
                               recommended=recommended)

@main.route("/api/reply_message", methods=["POST"])
@login_required
def reply_message():
    data        = request.get_json()
    receiver_id = data.get("receiver_id")
    content     = data.get("content", "").strip()

    if not receiver_id or not content:
        return jsonify({"error": "receiver_id and content required"}), 400

    msg = Message(sender_id=current_user.id, receiver_id=receiver_id, content=content)
    db.session.add(msg)

    role_name = "المشرف" if current_user.role == 'admin' else "الوكيل" if current_user.role == 'agent' else "العميل"
    notif = Notification(
        user_id=receiver_id,
        message=f"لديك رسالة جديدة من {role_name} {current_user.username}"
    )
    db.session.add(notif)
    db.session.commit()

    return jsonify({
        "status":    "sent",
        "id":        msg.id,
        "from":      current_user.username,
        "content":   msg.content,
        "timestamp": msg.timestamp.strftime("%H:%M")
    })

@main.route("/admin/delete_user/<int:user_id>", methods=["POST"])
@login_required
def admin_delete_user(user_id):
    if current_user.role != 'admin':
        abort(403)
    user_to_delete = User.query.get_or_404(user_id)
    if user_to_delete.id == current_user.id:
        flash("You cannot delete yourself.", "danger")
        return redirect(url_for('main.dashboard'))
    
    db.session.delete(user_to_delete)
    db.session.commit()
    flash(f"User {user_to_delete.username} deleted successfully.", "success")
    return redirect(url_for('main.dashboard'))

@main.route("/admin/edit_role/<int:user_id>", methods=["POST"])
@login_required
def admin_edit_role(user_id):
    if current_user.role != 'admin':
        abort(403)
    user = User.query.get_or_404(user_id)
    new_role = request.form.get('role')
    if new_role in ['customer', 'agent', 'admin']:
        user.role = new_role
        db.session.commit()
        flash(f"Role updated successfully for {user.username}.", "success")
    return redirect(url_for('main.dashboard'))

@main.route("/property/new", methods=['GET', 'POST'])
@login_required
def new_property():
    form = PropertyForm()
    if form.validate_on_submit():
        is_surooh = ('surooh' in form.title.data.lower() or
                     'surooh' in form.location.data.lower() or
                     current_user.username == 'surooh_agent')
        is_omran  = ('omran' in form.title.data.lower() or
                     'omran' in form.location.data.lower() or
                     current_user.username == 'omran_agent')

        prop = Property(
            title=form.title.data,
            description=form.description.data,
            price=form.price.data,
            location=form.location.data,
            type=form.type.data,
            size=form.size.data,
            bedrooms=form.bedrooms.data,
            bathrooms=form.bathrooms.data,
            city=form.city.data,
            address=form.address.data,
            latitude=form.latitude.data,
            longitude=form.longitude.data,
            is_surooh=is_surooh,
            is_omran=is_omran,
            agent_id=current_user.id
        )

        # Cache ML Prediction
        feats = {
            'type': prop.type or 'Unknown',
            'governorate': prop.city or 'Muscat',
            'area': prop.location or 'Unknown',
            'sqm': prop.size or 0,
            'bedrooms': prop.bedrooms or 2,
            'bathrooms': prop.bathrooms or 2,
            'floor': 0,
            'year': 2026
        }
        try:
            pred_res = ml.predict_price(feats)
            prop.ml_predicted_at_listing = pred_res.get('price', prop.price)
        except Exception as e:
            current_app.logger.error(f"ML Prediction failed during property creation: {e}")
            prop.ml_predicted_at_listing = prop.price

        db.session.add(prop)
        db.session.flush()

        upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'properties')
        os.makedirs(upload_dir, exist_ok=True)

        images   = request.files.getlist(form.images.name)
        is_first = True
        for img in images:
            if img and img.filename:
                ext             = img.filename.rsplit('.', 1)[-1].lower()
                unique_filename = f"{uuid.uuid4().hex}.{ext}"
                img.save(os.path.join(upload_dir, unique_filename))
                db.session.add(PropertyImage(
                    image_filename=unique_filename,
                    is_main=is_first,
                    property_id=prop.id
                ))
                is_first = False

        db.session.commit()

        try:
            import sys
            import os
            scripts_dir = os.path.join(current_app.root_path, 'scripts')
            if scripts_dir not in sys.path:
                sys.path.append(scripts_dir)
            from zone_discovery import scan_and_update_zones
            from models import Property, Area
            scan_and_update_zones(db.session, Property, Area)
        except Exception as e:
            current_app.logger.error(f"Error running auto zone discovery: {e}")
        try:
            from ml_engine import ml
            check = ml.detect_anomaly({
                'type':      prop.type,
                'area':      prop.location,
                'sqm':       float(prop.size or 100),
                'bedrooms':  float(prop.bedrooms or 2),
                'bathrooms': float(prop.bathrooms or 2),
                'floor':     1.0,
            }, listed_price=float(prop.price))

            if check['predicted'] > 0:
                prop.ml_predicted_at_listing = check['predicted']
            if check['is_anomaly']:
                prop.flagged_anomaly  = True
                prop.anomaly_severity = check['severity']
                prop.anomaly_reason   = check['reason']
                db.session.commit()

                if check['severity'] == 'high':
                    flash(f"⚠️ {check['reason']}", 'warning')
                elif check['severity'] == 'medium':
                    flash(f"ℹ️ {check['reason']}", 'info')

            from models import PredictionLog
            import json as _json
            db.session.add(PredictionLog(
                property_id     = prop.id,
                predicted_price = check.get('predicted') or 0,
                confidence      = check.get('confidence', 0),
                model_version   = ml.metadata.get('version'),
                listing_price   = float(prop.price),
                features_json   = _json.dumps({
                    'type': prop.type, 'area': prop.location,
                    'sqm': prop.size, 'bedrooms': prop.bedrooms,
                }),
            ))
            db.session.commit()
        except Exception as e:
            logger.warning(f"[ML] Anomaly check skipped: {e}")

        _rag_update(prop.id)

        flash('Property added with images!', 'success')
        return redirect(url_for('main.dashboard'))

    return render_template('create_property.html', form=form)

@main.route("/project/new", methods=['GET', 'POST'])
@login_required
def new_project():
    
    if current_user.role != 'agent':
        flash('Only agents can create projects.', 'danger')
        return redirect(url_for('main.dashboard'))

    form = ProjectForm()
    if form.validate_on_submit():
        project = Property(
            title       = form.name.data,
            description = form.description.data,
            price       = form.starting_price.data,  
            location    = form.location.data,
            type        = 'Project',                  
            size        = 0,                          
            city        = form.city.data,
            address     = form.address.data,
            agent_id    = current_user.id,
            latitude    = form.latitude.data,
            longitude   = form.longitude.data,
            developer   = form.developer.data,
            completion_date = form.completion_date.data,
            total_units = form.total_units.data,
            investment_omr = form.investment_omr.data,
            status      = form.status.data,
            is_project  = True,                       
        )
        db.session.add(project)
        db.session.commit()

        if form.images.data and form.images.data[0]:
            for img_file in form.images.data:
                if img_file and img_file.filename:
                    filename = f"{uuid.uuid4().hex}_{img_file.filename}"
                    img_file.save(os.path.join(
                        current_app.config['UPLOAD_FOLDER'], filename
                    ))
                    img = PropertyImage(
                        property_id=project.id,
                        image_filename=filename,
                        is_main=(len(project.images) == 0),
                    )
                    db.session.add(img)
            db.session.commit()

        _rag_update(project.id)

        flash(f"✅ Project '{project.title}' created! Now add units.", 'success')
        return redirect(url_for('main.project_detail', project_id=project.id))

    return render_template('new_project.html', form=form)

@main.route("/project/<int:project_id>")
def project_detail(project_id):
    
    project = Property.query.get_or_404(project_id)
    if not project.is_project:
        
        return redirect(url_for('main.property_detail', property_id=project_id))

    units = project.units.all()

    if units:
        prices = [u.price for u in units if u.price]
        unit_types = {}
        for u in units:
            unit_types[u.type] = unit_types.get(u.type, 0) + 1
        stats = {
            'unit_count':   len(units),
            'min_price':    min(prices) if prices else 0,
            'max_price':    max(prices) if prices else 0,
            'avg_price':    sum(prices) / len(prices) if prices else 0,
            'unit_types':   unit_types,
            'sold_count':   sum(1 for u in units if u.status == 'sold'),
        }
    else:
        stats = {'unit_count': 0, 'min_price': 0, 'max_price': 0,
                 'avg_price': 0, 'unit_types': {}, 'sold_count': 0}

    return render_template('project_detail.html',
                          project=project, units=units, stats=stats)

@main.route("/project/<int:project_id>/add_unit", methods=['GET', 'POST'])
@login_required
def add_unit(project_id):
    
    project = Property.query.get_or_404(project_id)
    if not project.is_project:
        flash('This is not a project.', 'warning')
        return redirect(url_for('main.dashboard'))
    if project.agent_id != current_user.id and current_user.role != 'admin':
        flash('You are not authorized.', 'danger')
        return redirect(url_for('main.dashboard'))

    form = UnitForm()
    if form.validate_on_submit():
        
        qty = max(1, min(form.quantity.data or 1, 200))
        created = []
        for i in range(qty):
            
            title = (f"{form.title.data} #{i+1}" if qty > 1 else form.title.data)

            unit = Property(
                title       = title,
                description = form.description.data,
                price       = form.price.data,
                location    = project.location,       
                city        = project.city,
                address     = project.address,
                type        = form.type.data,
                size        = form.size.data,
                bedrooms    = form.bedrooms.data,
                bathrooms   = form.bathrooms.data,
                agent_id    = current_user.id,
                latitude    = project.latitude,
                longitude   = project.longitude,
                status      = project.status,
                is_project  = False,
                parent_project_id = project.id,       
                developer   = project.developer,
                is_surooh   = project.is_surooh,
                is_omran    = project.is_omran,
            )
            db.session.add(unit)
            created.append(unit)
        db.session.commit()

        if form.images.data and form.images.data[0] and created:
            first_unit = created[0]
            for img_file in form.images.data:
                if img_file and img_file.filename:
                    filename = f"{uuid.uuid4().hex}_{img_file.filename}"
                    img_file.save(os.path.join(
                        current_app.config['UPLOAD_FOLDER'], filename
                    ))
                    img = PropertyImage(
                        property_id=first_unit.id,
                        image_filename=filename,
                        is_main=(len(first_unit.images) == 0),
                    )
                    db.session.add(img)
            db.session.commit()

        for u in created:
            _rag_update(u.id)

        flash(f"✅ Added {qty} unit{'s' if qty > 1 else ''} to '{project.title}'.",
              'success')
        return redirect(url_for('main.project_detail', project_id=project.id))

    return render_template('add_unit.html', form=form, project=project)

@main.route("/project/<int:project_id>/delete", methods=['POST'])
@login_required
def delete_project(project_id):
    
    project = Property.query.get_or_404(project_id)
    if not project.is_project:
        flash('Not a project.', 'warning')
        return redirect(url_for('main.dashboard'))
    if project.agent_id != current_user.id and current_user.role != 'admin':
        flash('Not authorized.', 'danger')
        return redirect(url_for('main.dashboard'))

    units_count = project.units.count()

    for unit in project.units.all():
        _rag_delete(unit.id)
        db.session.delete(unit)

    _rag_delete(project.id)
    db.session.delete(project)
    db.session.commit()

    flash(f"✅ Project deleted with all {units_count} unit(s).", 'success')
    return redirect(url_for('main.dashboard'))

@main.route("/property/<int:property_id>/edit", methods=['GET', 'POST'])
@login_required
def edit_property(property_id):
    prop = Property.query.get_or_404(property_id)
    if prop.agent_id != current_user.id and current_user.role != 'admin':
        flash('You are not authorized to edit this property.', 'danger')
        return redirect(url_for('main.dashboard'))

    form = PropertyForm()
    if form.validate_on_submit():
        prop.title       = form.title.data
        prop.description = form.description.data
        prop.price       = form.price.data
        prop.location    = form.location.data
        prop.type        = form.type.data
        prop.size        = form.size.data
        prop.bedrooms    = form.bedrooms.data
        prop.bathrooms   = form.bathrooms.data
        prop.city        = form.city.data
        prop.address     = form.address.data
        prop.latitude    = form.latitude.data
        prop.longitude   = form.longitude.data

        images = request.files.getlist(form.images.name)
        if images and images[0].filename:
            upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'properties')
            os.makedirs(upload_dir, exist_ok=True)
            for img in images:
                if img and img.filename:
                    ext             = img.filename.rsplit('.', 1)[-1].lower()
                    unique_filename = f"{uuid.uuid4().hex}.{ext}"
                    img.save(os.path.join(upload_dir, unique_filename))
                    db.session.add(PropertyImage(
                        image_filename=unique_filename,
                        is_main=len(prop.images) == 0,
                        property_id=prop.id
                    ))

        db.session.commit()

        _rag_update(prop.id)

        flash('Property updated successfully!', 'success')
        return redirect(url_for('main.property_detail', property_id=prop.id))

    elif request.method == 'GET':
        form.title.data       = prop.title
        form.description.data = prop.description
        form.price.data       = prop.price
        form.location.data    = prop.location
        form.type.data        = prop.type
        form.size.data        = prop.size
        form.bedrooms.data    = prop.bedrooms
        form.bathrooms.data   = prop.bathrooms
        form.city.data        = prop.city
        form.address.data     = prop.address
        form.latitude.data    = prop.latitude
        form.longitude.data   = prop.longitude

    return render_template('edit_property.html', form=form, property=prop)

@main.route("/property/<int:property_id>/mark_sold", methods=['POST'])
@login_required
def mark_property_sold(property_id):
    
    prop = Property.query.get_or_404(property_id)
    if prop.agent_id != current_user.id and current_user.role != 'admin':
        return jsonify({'error': 'not authorized'}), 403

    data = request.get_json() or request.form.to_dict()
    try:
        actual_price = float(data.get('actual_price', 0))
    except (TypeError, ValueError):
        return jsonify({'error': 'invalid actual_price'}), 400

    if actual_price <= 0:
        return jsonify({'error': 'actual_price must be > 0'}), 400

    prop.sold_price = actual_price
    prop.sold_date  = datetime.utcnow()
    prop.status     = 'sold'
    if prop.created_at:
        delta = datetime.utcnow() - prop.created_at
        prop.days_on_market = max(1, delta.days)

    from models import PredictionLog
    logs = PredictionLog.query.filter_by(property_id=prop.id).all()
    for log in logs:
        if log.predicted_price > 0:
            log.actual_price = actual_price
            log.error_pct    = abs(actual_price - log.predicted_price) / actual_price * 100
            log.confirmed_at = datetime.utcnow()

    db.session.commit()

    return jsonify({
        'status':         'marked_sold',
        'property_id':    prop.id,
        'actual_price':   actual_price,
        'days_on_market': prop.days_on_market,
        'ml_predicted':   prop.ml_predicted_at_listing,
        'ml_error_pct':   (abs(actual_price - prop.ml_predicted_at_listing) /
                          actual_price * 100) if prop.ml_predicted_at_listing else None,
    })

@main.route("/api/ml/accuracy")
def api_ml_accuracy():
    
    from models import PredictionLog
    confirmed = PredictionLog.query.filter(
        PredictionLog.actual_price.isnot(None)
    ).all()
    if not confirmed:
        return jsonify({
            'confirmed_count':  0,
            'avg_error_pct':    None,
            'within_10pct':     0,
            'within_20pct':     0,
            'message':          'No confirmed sales yet — accuracy unknown'
        })

    errors = [c.error_pct for c in confirmed if c.error_pct is not None]
    within_10 = sum(1 for e in errors if e <= 10)
    within_20 = sum(1 for e in errors if e <= 20)
    return jsonify({
        'confirmed_count':  len(errors),
        'avg_error_pct':    round(sum(errors) / len(errors), 2) if errors else None,
        'within_10pct':     within_10,
        'within_20pct':     within_20,
        'accuracy_within_20pct': round(within_20 / len(errors) * 100, 1) if errors else 0,
    })

@main.route("/property/<int:property_id>")
def property_detail(property_id):
    prop = Property.query.get_or_404(property_id)
    if current_user.is_authenticated and current_user.role == 'customer':
        rv = RecentlyViewed(user_id=current_user.id, property_id=prop.id)
        db.session.add(rv)
        db.session.commit()
        
    try:
        from ml_engine import ml
        features = {
            'type': prop.type or 'Villa',
            'governorate': prop.city or 'Muscat',
            'area': prop.location or prop.city or 'Muscat',
            'sqm': float(prop.size or 250),
            'bedrooms': int(prop.bedrooms or 3),
            'bathrooms': int(prop.bathrooms or 3),
            'floor': 0,
            'year': 2026
        }
        growth_data = ml.predict_growth(features, years=5)
        roi_val = ml.predict_roi({
            'type': prop.type,
            'location': prop.location or prop.city or 'Muscat',
            'status': prop.status or 'available',
            'price_omr': float(prop.price or 0)
        })
        if roi_val <= 0:
            from ai_utils import get_roi_assumption
            roi_val = get_roi_assumption(prop.type)
        
        base_score = growth_data.get('confidence', 70) * 0.7 + min(growth_data.get('growth_pct', 10), 30)
        
        if prop.is_omran:
            base_score = min(98, base_score + 15)
        elif prop.is_surooh:
            base_score = min(95, base_score + 10)
            
        ai_score = max(50, min(99, int(base_score)))
        ai_growth = growth_data.get('growth_pct', 0)
        ai_future = growth_data.get('future', 0)
    except Exception as e:
        import logging
        logging.error(f"Error calculating AI score: {e}")
        ai_score = 65
        ai_growth = 5.5
        ai_future = prop.price * 1.25
        roi_val = 6.0

    return render_template('property_detail.html', property=prop, ai_score=ai_score, ai_growth=ai_growth, ai_future=ai_future, roi_val=roi_val)

@main.route("/search")
def search():
    q_location = request.args.get('location', '')
    q_type     = request.args.get('type', '')
    price_min  = request.args.get('price_min', type=float)
    price_max  = request.args.get('price_max', type=float)
    surooh_only = request.args.get('surooh_only', type=int)
    omran_only  = request.args.get('omran_only',  type=int)
    sort_by     = request.args.get('sort', '')

    query = Property.query

    if q_location:
        query = query.filter(Property.location.ilike(f'%{q_location}%'))
    if q_type:
        query = query.filter_by(type=q_type)
    if price_min is not None:
        query = query.filter(Property.price >= price_min)
    if price_max is not None:
        query = query.filter(Property.price <= price_max)
    if surooh_only:
        query = query.filter_by(is_surooh=True)
    if omran_only:
        query = query.filter_by(is_omran=True)

    results = query.order_by(Property.created_at.desc()).all()

    if sort_by == 'cheapest':
        results.sort(key=lambda x: (x.price or float('inf')))
    elif sort_by == 'highest_roi':
        results.sort(key=lambda x: get_roi_assumption(x.type or 'Unknown'), reverse=True)
    elif sort_by == 'best_investment':
        prices = [float(p.price) for p in results if p.price]
        avg    = sum(prices) / len(prices) if prices else 100000
        results.sort(
            key=lambda x: calculate_score(
                {'price': x.price, 'type': x.type, 'location': x.location}, avg
            ), reverse=True
        )

    page = request.args.get('page', 1, type=int)
    per_page = 12
    total = len(results)
    total_pages = (total + per_page - 1) // per_page
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_results = results[start_idx:end_idx]

    return render_template('search_results.html',
                           properties=paginated_results,
                           page=page,
                           total_pages=total_pages,
                           total_results=total,
                           surooh_only=surooh_only,
                           omran_only=omran_only)

@main.route("/favorite/<int:property_id>", methods=["POST"])
@login_required
def toggle_favorite(property_id):
    existing = Favorite.query.filter_by(
        user_id=current_user.id, property_id=property_id
    ).first()

    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({"status": "removed", "property_id": property_id})

    fav = Favorite(user_id=current_user.id, property_id=property_id)
    db.session.add(fav)
    db.session.commit()
    return jsonify({"status": "added", "property_id": property_id})

@main.route("/api/favorites")
def api_favorites():
    if not current_user.is_authenticated:
        return jsonify({"favorite_ids": []})
    favs    = Favorite.query.filter_by(user_id=current_user.id).all()
    fav_ids = [f.property_id for f in favs]
    return jsonify({"favorite_ids": fav_ids})

@main.route("/api/send_message", methods=["POST"])
@login_required
def send_message():
    data        = request.get_json()
    agent_id    = data.get("agent_id")
    content     = data.get("message", "")
    property_id = data.get("property_id")

    if not agent_id or not content:
        return jsonify({"error": "agent_id and message required"}), 400

    msg = Message(
        sender_id=current_user.id,
        receiver_id=agent_id,
        property_id=property_id,
        content=content
    )
    db.session.add(msg)

    sender_name = current_user.username if current_user.is_authenticated else "Customer"
    notif = Notification(
        user_id=agent_id,
        message=f"لديك رسالة جديدة من {sender_name}"
    )
    db.session.add(notif)
    db.session.commit()

    return jsonify({"status": "sent", "message_id": msg.id})

@main.route("/api/notifications")
@login_required
def api_notifications():
    notifs = Notification.query.filter_by(
        user_id=current_user.id, is_read=False
    ).order_by(Notification.timestamp.desc()).all()

    return jsonify([{
        "id":        n.id,
        "message":   n.message,
        "timestamp": n.timestamp.strftime("%H:%M")
    } for n in notifs])

@main.route("/api/notifications/read/<int:notif_id>", methods=["POST"])
@login_required
def mark_notif_read(notif_id):
    notif = Notification.query.filter_by(
        id=notif_id, user_id=current_user.id
    ).first_or_404()
    notif.is_read = True
    db.session.commit()
    return jsonify({"status": "success"})

@main.route("/api/messages/<int:user_id>")
@login_required
def api_messages(user_id):
    if current_user.role not in ['agent', 'admin'] and current_user.id != user_id:
        return jsonify({"error": "Unauthorized"}), 403

    msgs = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == user_id)) |
        ((Message.sender_id == user_id) & (Message.receiver_id == current_user.id))
    ).order_by(Message.timestamp.desc()).limit(50).all()

    all_msgs = msgs[::-1]  

    return jsonify([{
        "id":          m.id,
        "sender_id":   m.sender_id,
        "receiver_id": m.receiver_id,
        "from":        m.sender.username,
        "to":          m.receiver.username,
        "content":     m.content,
        "is_read":     m.is_read,
        "timestamp":   m.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        "is_mine":     m.sender_id == current_user.id
    } for m in all_msgs])

@main.route("/api/predict_price", methods=["POST"])
@limiter.limit("30 per minute; 500 per hour")
def predict_price_api():
    
    from ml_engine import ml

    data  = request.get_json() or {}
    loc   = data.get("location", "")
    ptype = data.get("type", "Apartment")
    try:
        price = float(data.get("price", 0))
    except (TypeError, ValueError):
        price = 0

    if price < 100:
        return jsonify({"error": "Please enter a realistic current value (e.g., > 1,000 OMR)."}), 400

    _loc_aliases = {
        'alburaimi': 'Al Buraimi', 'buraimi': 'Al Buraimi', 'al-buraimi': 'Al Buraimi',
        'almouj':    'Al Mouj',    'mouj':    'Al Mouj',    'al-mouj':    'Al Mouj',
        'almawaleh': 'Al Mawaleh', 'mawaleh': 'Al Mawaleh',
        'alhail':    'Al Hail',    'hail':    'Al Hail',
        'alkhuwair': 'Al Khuwair', 'khuwair': 'Al Khuwair',
        'alghubra':  'Al Ghubra',  'ghubra':  'Al Ghubra',
        'alkhoud':   'Al Khoud',   'khoud':   'Al Khoud',
        'alseeb':    'Al Seeb',    'seeb':    'Al Seeb',
    }
    _norm = loc.lower().replace(' ', '').replace('-', '')
    if _norm in _loc_aliases:
        loc = _loc_aliases[_norm]

    features = {
        'type':       ptype,
        'area':       loc or 'Muscat',
        'sqm':        float(data.get('sqm', 100)),
        'bedrooms':   float(data.get('bedrooms', 2)),
        'bathrooms':  float(data.get('bathrooms', 2)),
        'floor':      float(data.get('floor', 0)),
    }

    growth_5y = ml.predict_growth(features, years=5)
    method = growth_5y.get('method', '')
    
    ml_used = method.startswith('ml_')

    annual_rate = growth_5y['annual_pct'] / 100   
    val_1y = price * (1 + annual_rate)
    val_5y = price * growth_5y['multiplier']

    current_pred = ml.predict_price({**features, 'year': 2026})

    projection = []
    for yr in range(0, 11):
        m = (1 + annual_rate) ** yr
        projection.append({
            "year":  yr,
            "value": round(price * m, 0),
        })

    area_projection = []
    gov_projection  = []
    try:
        
        area_growth = ml.predict_area_growth(loc, years=5)
        area_annual = area_growth['annual_pct'] / 100

        gov = ml._guess_governorate(loc)
        gov_growth = ml.predict_area_growth(gov, years=5) if gov != loc else area_growth
        gov_annual = gov_growth['annual_pct'] / 100

        for yr in range(0, 11):
            area_projection.append({
                "year":  yr,
                "value": round(price * ((1 + area_annual) ** yr), 0),
            })
            gov_projection.append({
                "year":  yr,
                "value": round(price * ((1 + gov_annual) ** yr), 0),
            })
    except Exception as _e:
        logger.warning(f"[ML] comparison series unavailable: {_e}")
        area_projection = projection
        gov_projection  = projection

    if   "villa"      in ptype.lower(): rent_pct = 0.065
    elif "land"       in ptype.lower(): rent_pct = 0.090
    elif "townhouse"  in ptype.lower(): rent_pct = 0.070
    elif "commercial" in ptype.lower(): rent_pct = 0.085
    else:                               rent_pct = 0.075

    if method == 'ml_per_property_cagr':
        reason = (
            f"ML-predicted {annual_rate * 100:.2f}%/yr growth from per-property "
            f"RandomForest analysis (confidence: {growth_5y['confidence']}%). "
            f"Based on 3,500 real Omani price observations (2019-2026)."
        )
    elif method == 'ml_with_area_cagr_fallback':
        reason = (
            f"ML used area-level CAGR ({annual_rate * 100:.2f}%/yr) because "
            f"this exact feature combination is rare in training data. "
            f"More features (sqm, bedrooms) → better per-property accuracy."
        )
    elif method == 'baseline_5pct':
        reason = (
            f"Estimated {annual_rate * 100:.1f}%/yr baseline growth — "
            f"limited data for this combination. Add more property details."
        )
    else:
        reason = (
            f"Estimated {annual_rate * 100:.1f}%/yr growth from CAGR fallback "
            f"(ml_engine not available)."
        )

    is_cold_start  = ml.is_cold_start_area(loc) if loc else False
    confidence_band = ml.confidence_band(growth_5y.get('confidence', 0))
    cold_start_msg = None
    if is_cold_start:
        cold_start_msg = (
            f'⚠️ New area "{loc}" — ML using nearest governorate as proxy. '
            f'Prediction will improve after retraining.'
        )

    return jsonify({
        "estimated_price":  round(val_1y, 0),
        "roi":              round(rent_pct * 100, 1),
        "yearly_income":    round(price * rent_pct, 0),
        "value_1y":         round(val_1y, 0),
        "value_5y":         round(val_5y, 0),
        "annual_growth":    round(annual_rate * 100, 2),
        "ml_powered":       ml_used,
        "ml_method":        growth_5y.get('method'),
        "ml_confidence":    growth_5y.get('confidence'),
        "confidence_band":  confidence_band,        
        "cold_start":       is_cold_start,           
        "cold_start_msg":   cold_start_msg,
        "price_range":      current_pred.get('range'),
        "reason":            reason,
        "projection":        projection,            
        "area_projection":   area_projection,        
        "gov_projection":    gov_projection,         
        "current_price":     round(price, 0),
        "ml_estimated":      round(current_pred.get('price', 0), 0),
        "location":          loc or "Oman",
    })

@main.route("/api/recommendations")
def api_recommendations():
    all_props = Property.query.order_by(Property.created_at.desc()).limit(100).all()
    prices    = [float(p.price) for p in all_props if p.price]
    avg       = sum(prices) / len(prices) if prices else 100000

    scored = []
    for p in all_props:
        s = calculate_score({'price': p.price, 'type': p.type, 'location': p.location}, avg)
        scored.append({**p.to_dict(), "score": s})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return jsonify(scored[:6])

@main.route("/agent/messages")
@login_required
def agent_messages_inbox():
    if current_user.role != 'agent':
        return redirect(url_for('main.dashboard'))

    all_agent_msgs = Message.query.filter(
        (Message.sender_id == current_user.id) |
        (Message.receiver_id == current_user.id)
    ).order_by(Message.timestamp.asc()).all()

    agent_threads = {}
    for m in all_agent_msgs:
        other_id = m.receiver_id if m.sender_id == current_user.id else m.sender_id
        if other_id == current_user.id:
            continue
        if other_id not in agent_threads:
            other_user = User.query.get(other_id)
            agent_threads[other_id] = {
                'user': other_user, 'messages': [],
                'last_msg': None, 'unread': 0
            }
        agent_threads[other_id]['messages'].append(m)

    for uid, thread in agent_threads.items():
        thread['last_msg'] = thread['messages'][-1]
        thread['unread']   = sum(
            1 for m in thread['messages']
            if not m.is_read and m.receiver_id == current_user.id
        )

    agent_threads_list = sorted(
        agent_threads.values(),
        key=lambda t: t['last_msg'].timestamp, reverse=True
    )

    return render_template('dashboard_messages.html',
                           threads=agent_threads_list,
                           active_thread_id=None)

@main.route("/agent/messages/<int:customer_id>")
@login_required
def agent_message_thread(customer_id):
    if current_user.role != 'agent':
        return redirect(url_for('main.dashboard'))

    all_agent_msgs = Message.query.filter(
        (Message.sender_id == current_user.id) |
        (Message.receiver_id == current_user.id)
    ).order_by(Message.timestamp.asc()).all()

    agent_threads = {}
    for m in all_agent_msgs:
        other_id = m.receiver_id if m.sender_id == current_user.id else m.sender_id
        if other_id == current_user.id:
            continue
        if other_id not in agent_threads:
            other_user = User.query.get(other_id)
            agent_threads[other_id] = {
                'user': other_user, 'messages': [],
                'last_msg': None, 'unread': 0
            }
        agent_threads[other_id]['messages'].append(m)

        if (other_id == customer_id and
                m.receiver_id == current_user.id and not m.is_read):
            m.is_read = True

    db.session.commit()

    for uid, thread in agent_threads.items():
        thread['last_msg'] = thread['messages'][-1]
        thread['unread']   = sum(
            1 for m in thread['messages']
            if not m.is_read and m.receiver_id == current_user.id
        )

    agent_threads_list = sorted(
        agent_threads.values(),
        key=lambda t: t['last_msg'].timestamp, reverse=True
    )

    active_customer = User.query.get_or_404(customer_id)
    thread_msgs     = agent_threads.get(customer_id, {}).get('messages', [])

    return render_template('dashboard_messages.html',
                           threads=agent_threads_list,
                           active_thread_id=customer_id,
                           active_customer=active_customer,
                           thread_msgs=thread_msgs)

@main.route("/api/investment_requests")
@login_required
def api_investment_requests():
    
    if current_user.role not in ('agent', 'admin'):
        return jsonify({"error": "Agent access required"}), 403

    if current_user.role == 'admin':
        requests_q = InvestmentRequest.query.order_by(
            InvestmentRequest.timestamp.desc()
        ).all()
    else:
        requests_q = InvestmentRequest.query.filter_by(
            agent_id=current_user.id
        ).order_by(InvestmentRequest.timestamp.desc()).all()

    return jsonify([{
        "id":        r.id,
        "user":      r.user.username  if r.user  else "anonymous",
        "agent":     r.agent.username if r.agent else "—",
        "project":   r.project   or "—",
        "message":   r.message   or "",
        "status":    r.status,
        "timestamp": r.timestamp.strftime("%Y-%m-%d %H:%M"),
    } for r in requests_q])

@main.route("/api/investment_requests/<int:req_id>/status", methods=["POST"])
@login_required
def update_investment_request_status(req_id):
    
    if current_user.role not in ('agent', 'admin'):
        return jsonify({"error": "Agent access required"}), 403

    req = InvestmentRequest.query.get_or_404(req_id)

    if current_user.role == 'agent' and req.agent_id != current_user.id:
        return jsonify({"error": "Not your request"}), 403

    data       = request.get_json() or {}
    new_status = data.get("status", "")
    allowed    = ("pending", "contacted", "closed")

    if new_status not in allowed:
        return jsonify({"error": f"status must be one of {allowed}"}), 400

    req.status = new_status
    db.session.commit()

    return jsonify({
        "status":  "updated",
        "req_id":  req_id,
        "new_status": new_status,
    })
