# routes.py — All Flask routes for Smart AI Real Estate Oman
# جميع مسارات التطبيق: API، صفحات، لوحات التحكم، الرسائل، التحليلات

from flask import (Blueprint, render_template, url_for, flash,
                   redirect, request, jsonify, current_app, session)
from flask_login import login_user, current_user, logout_user, login_required
from sqlalchemy import func
from datetime import datetime, timedelta

from extensions import db, limiter
from models import (User, Property, Favorite, Area, PropertyImage,
                    Message, Inquiry, RecentlyViewed, Notification,
                    ChatLog, ChatFeedback, Conversation)
from forms import (RegistrationForm, LoginForm, PropertyForm,
                   SettingsProfileForm, SettingsSecurityForm,
                   SettingsPreferencesForm)
from ai_utils import (get_ai_response, recommend_investment,
                      portfolio_summary, calculate_score, get_roi_assumption)
import os
import uuid
from ml_model import (train_price_model, predict_price,
                      predict_prices, get_ml_investment_score)
from firebase import db as firebase_db

# ─── Blueprint ────────────────────────────────────────────────────────────────
main = Blueprint('main', __name__)


# =====================================================
# 🤖 AI CHAT API
# =====================================================

@main.route("/api/chat", methods=["POST"])
@limiter.limit("10 per minute")   # تحديد 10 طلبات في الدقيقة لكل IP
def chat_api():
    """
    واجهة المحادثة مع Ahmed 2.0
    تقبل: message, conversation_id (اختياري)
    تُرجع: text, properties, investment_hotspots, conversation_id
    """
    data            = request.get_json()
    message         = data.get("message", "")
    conversation_id = data.get("conversation_id")   # يُرسَل من الفرونت بعد أول رسالة

    user_id = current_user.id if current_user.is_authenticated else None

    try:
        # get_ai_response يُدير الـ Conversation ويُسجّل في ChatLog داخليًا
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


# ─── Chat Feedback ────────────────────────────────────────────────────────────

@main.route("/api/chat/feedback", methods=["POST"])
def chat_feedback():
    """
    حفظ تقييم المستخدم على رسالة معينة (إيجابي/سلبي + تعليق)
    Body: { chat_log_id, rating (1=👍 / 0=👎), comment (optional) }
    """
    data        = request.get_json()
    chat_log_id = data.get("chat_log_id")
    rating      = data.get("rating")
    comment     = data.get("comment", "")

    # التحقق من المدخلات
    if chat_log_id is None or rating not in (0, 1):
        return jsonify({"error": "chat_log_id and rating (0 or 1) are required"}), 400

    # التأكد أن الـ ChatLog موجود
    log = ChatLog.query.get(chat_log_id)
    if not log:
        return jsonify({"error": "Chat log not found"}), 404

    # منع تكرار التقييم على نفس الرسالة
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


# ─── Admin Chat Analytics ─────────────────────────────────────────────────────

@main.route("/api/admin/chat-analytics")
@login_required
def chat_analytics():
    """
    تحليلات المحادثات للمشرف:
    - إجمالي المحادثات، متوسط وقت الاستجابة، متوسط التوكنز
    - توزيع النوايا، أكثر المواقع بحثًا، معدل الرضا، التكلفة اليومية
    """
    if current_user.role != 'admin':
        return jsonify({"error": "Admin access required"}), 403

    # --- النطاق الزمني: آخر 24 ساعة ---
    since = datetime.utcnow() - timedelta(hours=24)
    logs  = ChatLog.query.filter(ChatLog.timestamp >= since).all()

    total_chats = len(logs)

    # متوسط وقت الاستجابة (بالثواني)
    rt_values = [l.response_time for l in logs if l.response_time is not None]
    avg_response_time = round(sum(rt_values) / len(rt_values), 2) if rt_values else 0

    # متوسط التوكنز
    tk_values = [l.tokens_used for l in logs if l.tokens_used is not None]
    avg_tokens = round(sum(tk_values) / len(tk_values), 1) if tk_values else 0

    # التكلفة اليومية المقدّرة (GPT-4o-mini ≈ $0.000002 / token)
    total_tokens = sum(tk_values)
    daily_cost   = round(total_tokens * 0.000002, 4)

    # توزيع النوايا (intent breakdown)
    intent_counts = {}
    for log in logs:
        key = log.intent or "unknown"
        intent_counts[key] = intent_counts.get(key, 0) + 1

    # أكثر المواقع بحثًا — نستخرجها من رسائل المستخدم بكلمات مفتاحية
    location_keywords = [
        "muscat", "مسقط", "salalah", "صلالة", "barka", "بركاء",
        "sohar", "صحار", "nizwa", "نزوى", "sur", "صور",
        "duqm", "دقم", "rustaq", "الرستاق"
    ]
    location_map = {   # توحيد الأسماء
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

    # ترتيب المواقع تنازليًا
    top_locations = sorted(
        [{"location": k, "count": v} for k, v in loc_counts.items()],
        key=lambda x: x["count"], reverse=True
    )[:5]

    # معدل الرضا من ChatFeedback
    all_feedback = ChatFeedback.query.filter(
        ChatFeedback.timestamp >= since
    ).all()
    positive       = sum(1 for f in all_feedback if f.rating == 1)
    satisfaction   = round((positive / len(all_feedback)) * 100, 1) if all_feedback else None

    return jsonify({
        "period":            "last_24h",
        "total_chats":       total_chats,
        "avg_response_time": avg_response_time,   # seconds
        "avg_tokens":        avg_tokens,
        "daily_cost_usd":    daily_cost,
        "intent_breakdown":  intent_counts,
        "top_locations":     top_locations,
        "satisfaction_rate": satisfaction,         # % or null if no feedback yet
        "total_feedback":    len(all_feedback),
    })


# =====================================================
# 🗺️ INVESTMENT MAP API
# =====================================================

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


# =====================================================
# 🏠 Home
# =====================================================

@main.route("/")
@main.route("/home")
def home():
    properties = Property.query.order_by(Property.created_at.desc()).limit(6).all()
    return render_template('home.html', title='Home', properties=properties)


# =====================================================
# ℹ️ About
# =====================================================

@main.route("/about")
def about():
    return render_template('about.html', title='About')


# =====================================================
# 🗺️ Investment Map Page
# =====================================================

@main.route("/investment-map")
def investment_map():
    return render_template("investment_map.html")


# =====================================================
# 🔐 Register
# =====================================================

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


# =====================================================
# 🔐 Login
# =====================================================

@main.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))

    form = LoginForm()

    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            return redirect(url_for('main.home'))
        else:
            flash('Login failed', 'danger')

    return render_template('login.html', title='Login', form=form)


@main.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('main.home'))


# =====================================================
# ⚙️ Settings
# =====================================================

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


# =====================================================
# 📊 Dashboard
# =====================================================

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
        users      = User.query.all()
        properties = Property.query.all()

        if properties:
            train_price_model(properties)
            predictions = predict_prices(properties)
            for i, p in enumerate(properties):
                p.score = calculate_score({
                    'type': p.type, 'price': p.price, 'location': p.location
                })
                p.predicted_price = predictions[i]
                p.ml_score        = get_ml_investment_score(p.predicted_price, p.price)

        return render_template('dashboard_admin.html',
                               users=users,
                               properties=properties)

    else:
        # Customer dashboard
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

        all_props = Property.query.all()
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

    notif = Notification(
        user_id=receiver_id,
        message=f"لديك رسالة جديدة من الوكيل {current_user.username}"
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


# =====================================================
# ➕ Add / Edit Property
# =====================================================

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
        flash('Property added with images!', 'success')
        return redirect(url_for('main.dashboard'))

    return render_template('create_property.html', form=form)


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


@main.route("/property/<int:property_id>")
def property_detail(property_id):
    prop = Property.query.get_or_404(property_id)
    if current_user.is_authenticated and current_user.role == 'customer':
        rv = RecentlyViewed(user_id=current_user.id, property_id=prop.id)
        db.session.add(rv)
        db.session.commit()
    return render_template('property_detail.html', property=prop)


# =====================================================
# 🔍 Search
# =====================================================

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

    return render_template('search_results.html',
                           properties=results,
                           surooh_only=surooh_only,
                           omran_only=omran_only)


# =====================================================
# ❤️ Favorite API
# =====================================================

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


# =====================================================
# 💬 Messaging API
# =====================================================

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


# =====================================================
# 🔔 Notifications API
# =====================================================

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
    if current_user.role != 'agent' and current_user.id != user_id:
        return jsonify({"error": "Unauthorized"}), 403

    msgs      = Message.query.filter_by(receiver_id=user_id).order_by(Message.timestamp.desc()).limit(50).all()
    sent_msgs = Message.query.filter_by(sender_id=user_id).order_by(Message.timestamp.desc()).limit(50).all()

    all_msgs = list(set(msgs + sent_msgs))
    all_msgs.sort(key=lambda x: x.timestamp)

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


# =====================================================
# 📈 AI Price Predictor API
# =====================================================

@main.route("/api/predict_price", methods=["POST"])
def predict_price_api():
    data  = request.get_json()
    loc   = data.get("location", "").lower()
    ptype = data.get("type", "Apartment")
    price = float(data.get("price", 0))

    if price <= 0:
        return jsonify({"error": "Valid price required"}), 400

    if   "muscat"  in loc or "مسقط"   in loc: growth = 0.06
    elif "salalah" in loc or "صلالة"  in loc: growth = 0.05
    elif "barka"   in loc or "بركاء"  in loc: growth = 0.07
    elif "sohar"   in loc or "صحار"   in loc: growth = 0.06
    else:                                      growth = 0.055

    if   "villa" in ptype.lower(): rent_estimate = price * 0.065
    elif "land"  in ptype.lower(): rent_estimate = price * 0.09
    else:                          rent_estimate = price * 0.075

    roi    = (rent_estimate / price) * 100
    val_1y = price * (1 + growth)
    val_5y = price * ((1 + growth) ** 5)

    return jsonify({
        "estimated_price": round(val_1y, 0),
        "roi":             round(roi, 1),
        "yearly_income":   round(rent_estimate, 0),
        "value_1y":        round(val_1y, 0),
        "value_5y":        round(val_5y, 0),
        "reason": (f"Expected {growth * 100:.1f}% annual growth in this area "
                   f"driven by local market trends and ongoing developments.")
    })


# =====================================================
# 🏠 Customer Recommendations API
# =====================================================

@main.route("/api/recommendations")
def api_recommendations():
    all_props = Property.query.all()
    prices    = [float(p.price) for p in all_props if p.price]
    avg       = sum(prices) / len(prices) if prices else 100000

    scored = []
    for p in all_props:
        s = calculate_score({'price': p.price, 'type': p.type, 'location': p.location}, avg)
        scored.append({**p.to_dict(), "score": s})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return jsonify(scored[:6])


# =====================================================
# ✉️ Agent Messages
# =====================================================

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
