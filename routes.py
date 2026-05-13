from flask import Blueprint, render_template, url_for, flash, redirect, request, jsonify, current_app
from flask_login import login_user, current_user, logout_user, login_required
from extensions import db
from models import User, Property, Favorite, Area, PropertyImage, Message, Inquiry, RecentlyViewed, Notification
from forms import RegistrationForm, LoginForm, PropertyForm
from ai_utils import get_ai_response,recommend_investment, portfolio_summary, calculate_score
import os
from werkzeug.utils import secure_filename
from ml_model import train_price_model, predict_price, get_ml_investment_score
from firebase import db as firebase_db

# ✅ Blueprint
main = Blueprint('main', __name__)

@main.route("/api/chat", methods=["POST"])
def chat_api():
    data = request.get_json()
    message = data.get("message", "")

    user_id = None
    if current_user.is_authenticated:
        user_id = current_user.id

    try:
        reply = get_ai_response(message, user_id=user_id)
        return jsonify(reply)

    except Exception as e:
        print("ERROR:", str(e))
        return jsonify({
            "text": "Sorry, server error 😅" if "english" in message.lower() else "صار خطأ في السيرفر",
            "properties": []
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
            "email": user.email,
            "role": user.role
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
# 📊 Dashboard
# =====================================================
@main.route("/property/<int:property_id>/delete", methods=["POST"])
@login_required
def delete_property(property_id):
    prop = Property.query.get_or_404(property_id)
    
    # Check authorization
    if prop.agent_id != current_user.id and current_user.role != 'admin':
        flash("You are not authorized to delete this property.", "danger")
        return redirect(url_for('main.dashboard'))
        
    try:
        import os
        from flask import current_app
        
        # Clean up physical image files
        upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'properties')
        for img in prop.images:
            filepath = os.path.join(upload_dir, img.image_filename)
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except:
                    pass
                    
        # Manually delete dependent records that don't have cascade setup
        from models import RecentlyViewed, Message
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
        props = Property.query.filter_by(agent_id=current_user.id).order_by(Property.created_at.desc()).all()

        prop_dicts = [{
            'title': p.title,
            'type': p.type,
            'price': p.price,
            'location': p.location
        } for p in props]

        ai_rec = recommend_investment(prop_dicts)
        pf_stats = portfolio_summary(prop_dicts)

        for p in props:
            p.predicted_price = p.price
            p.ml_score = 60

        # Build conversation threads grouped by customer
        all_agent_msgs = Message.query.filter(
            (Message.sender_id == current_user.id) | (Message.receiver_id == current_user.id)
        ).order_by(Message.timestamp.asc()).all()

        agent_threads = {}
        for m in all_agent_msgs:
            other_id = m.receiver_id if m.sender_id == current_user.id else m.sender_id
            if other_id == current_user.id:
                continue
            if other_id not in agent_threads:
                other_user = User.query.get(other_id)
                agent_threads[other_id] = {
                    'user': other_user,
                    'messages': [],
                    'last_msg': None,
                    'unread': 0
                }
            agent_threads[other_id]['messages'].append(m)

        for uid, thread in agent_threads.items():
            thread['last_msg'] = thread['messages'][-1]
            thread['unread'] = sum(1 for m in thread['messages'] if not m.is_read and m.receiver_id == current_user.id)

        agent_threads_list = sorted(agent_threads.values(), key=lambda t: t['last_msg'].timestamp, reverse=True)

        return render_template('dashboard_agent.html',
                               properties=props,
                               ai_rec=ai_rec,
                               pf_stats=pf_stats,
                               agent_messages=all_agent_msgs,
                               threads=agent_threads_list)

    elif current_user.role == 'admin':
        users = User.query.all()
        properties = Property.query.all()

        if properties:
            train_price_model(properties)

        for p in properties:
            p.score = calculate_score({
                'type': p.type,
                'price': p.price,
                'location': p.location
            })

            p.predicted_price = predict_price(p)
            p.ml_score = get_ml_investment_score(p.predicted_price, p.price)

        return render_template('dashboard_admin.html',
                               users=users,
                               properties=properties)

    else:
        # Customer dashboard
        favorites = Favorite.query.filter_by(user_id=current_user.id).all()
        recently_viewed = RecentlyViewed.query.filter_by(user_id=current_user.id).order_by(RecentlyViewed.timestamp.desc()).limit(5).all()

        # Messages — build conversation threads grouped by agent
        all_msgs = Message.query.filter(
            (Message.sender_id == current_user.id) | (Message.receiver_id == current_user.id)
        ).order_by(Message.timestamp.asc()).all()

        threads = {}
        for m in all_msgs:
            other_id = m.receiver_id if m.sender_id == current_user.id else m.sender_id
            if other_id not in threads:
                other_user = User.query.get(other_id)
                threads[other_id] = {
                    'user': other_user,
                    'messages': [],
                    'last_msg': None,
                    'unread': 0
                }
            threads[other_id]['messages'].append(m)

        for uid, thread in threads.items():
            thread['last_msg'] = thread['messages'][-1]
            thread['unread'] = sum(1 for m in thread['messages'] if not m.is_read and m.receiver_id == current_user.id)

        threads_list = sorted(threads.values(), key=lambda t: t['last_msg'].timestamp, reverse=True)
        flat_messages = all_msgs  # keep for stats

        # Behavior tracking: Extract preferences
        pref_locs = set()
        pref_types = set()
        for f in favorites:
            pref_locs.add(f.property.location)
            pref_types.add(f.property.type)
        for rv in recently_viewed:
            pref_locs.add(rv.property.location)
            pref_types.add(rv.property.type)

        # AI Recommended properties (top scored + behavioral weighting)
        all_props = Property.query.all()
        prices = [float(p.price) for p in all_props if p.price]
        avg = sum(prices) / len(prices) if prices else 100000
        for p in all_props:
            base_score = calculate_score({'price': p.price, 'type': p.type, 'location': p.location}, avg)
            if p.location in pref_locs:
                base_score += 15
            if p.type in pref_types:
                base_score += 10
            p._score = base_score

        all_props.sort(key=lambda x: x._score, reverse=True)
        recommended = all_props[:6]

        # Compute ROI for recommended
        from ai_utils import get_roi_assumption
        for p in recommended:
            t = (p.type or '').lower()
            if 'villa' in t: p.roi = 6.0
            elif 'apartment' in t: p.roi = 7.0
            elif 'land' in t: p.roi = 8.0
            else: p.roi = 5.0
            if getattr(p, 'status', 'available') == 'under_construction': p.roi += 1.5
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
    data = request.get_json()
    receiver_id = data.get("receiver_id")
    content = data.get("content", "").strip()
    if not receiver_id or not content:
        return jsonify({"error": "receiver_id and content required"}), 400

    msg = Message(
        sender_id=current_user.id,
        receiver_id=receiver_id,
        content=content
    )
    db.session.add(msg)

    # Notify customer
    notif = Notification(
        user_id=receiver_id,
        message=f"لديك رسالة جديدة من الوكيل {current_user.username}"
    )
    db.session.add(notif)
    db.session.commit()

    return jsonify({
        "status": "sent",
        "id": msg.id,
        "from": current_user.username,
        "content": msg.content,
        "timestamp": msg.timestamp.strftime("%H:%M")
    })


# =====================================================
# ➕ Add Property
# =====================================================
import os
import uuid
from werkzeug.utils import secure_filename
from flask import current_app, request

@main.route("/property/new", methods=['GET', 'POST'])
@login_required
def new_property():
    form = PropertyForm()
    if form.validate_on_submit():
        is_surooh = 'surooh' in form.title.data.lower() or 'surooh' in form.location.data.lower() or current_user.username == 'surooh_agent'
        is_omran = 'omran' in form.title.data.lower() or 'omran' in form.location.data.lower() or current_user.username == 'omran_agent'

        prop = Property(
            title=form.title.data,
            description=form.description.data,
            price=form.price.data,
            location=form.location.data,
            type=form.type.data,
            size=form.size.data,
            is_surooh=is_surooh,
            is_omran=is_omran,
            agent_id=current_user.id
        )
        db.session.add(prop)
        db.session.flush() # get prop.id without committing

        # Handle file uploads
        upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'properties')
        os.makedirs(upload_dir, exist_ok=True)
        
        images = request.files.getlist(form.images.name)
        is_first = True
        for img in images:
            if img and img.filename:
                # generate UUID filename to avoid collisions
                ext = img.filename.rsplit('.', 1)[-1].lower()
                unique_filename = f"{uuid.uuid4().hex}.{ext}"
                filepath = os.path.join(upload_dir, unique_filename)
                img.save(filepath)
                
                new_img = PropertyImage(
                    image_filename=unique_filename,
                    is_main=is_first,
                    property_id=prop.id
                )
                db.session.add(new_img)
                is_first = False

        db.session.commit()
        flash('Property added with images!', 'success')
        return redirect(url_for('main.dashboard'))

    return render_template('create_property.html', form=form)



@main.route("/property/<int:property_id>")
def property_detail(property_id):
    prop = Property.query.get_or_404(property_id)
    if current_user.is_authenticated and current_user.role == 'customer':
        # Log recently viewed
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
    q_type = request.args.get('type', '')
    price_min = request.args.get('price_min', type=float)
    price_max = request.args.get('price_max', type=float)
    surooh_only = request.args.get('surooh_only', type=int)
    omran_only = request.args.get('omran_only', type=int)
    sort_by = request.args.get('sort', '')

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
        from ai_utils import get_roi_assumption
        results.sort(key=lambda x: get_roi_assumption(x.type or 'Unknown'), reverse=True)
    elif sort_by == 'best_investment':
        from ai_utils import calculate_score
        prices = [float(p.price) for p in results if p.price]
        avg = sum(prices)/len(prices) if prices else 100000
        results.sort(key=lambda x: calculate_score({'price': x.price, 'type': x.type, 'location': x.location}, avg), reverse=True)

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
    if not property_id:
        return jsonify({"error": "property_id required"}), 400

    existing = Favorite.query.filter_by(user_id=current_user.id, property_id=property_id).first()

    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({"status": "removed", "property_id": property_id})
    else:
        fav = Favorite(user_id=current_user.id, property_id=property_id)
        db.session.add(fav)
        db.session.commit()
        return jsonify({"status": "added", "property_id": property_id})


@main.route("/api/favorites")
def api_favorites():
    if not current_user.is_authenticated:
        return jsonify({"favorite_ids": []})
    favs = Favorite.query.filter_by(user_id=current_user.id).all()
    fav_ids = [f.property_id for f in favs]
    return jsonify({"favorite_ids": fav_ids})


# =====================================================
# 💬 Messaging API
# =====================================================
@main.route("/api/send_message", methods=["POST"])
@login_required
def send_message():
    data = request.get_json()
    agent_id = data.get("agent_id")
    content = data.get("message", "")
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
    
    # Notify Receiver
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
    notifs = Notification.query.filter_by(user_id=current_user.id, is_read=False).order_by(Notification.timestamp.desc()).all()
    return jsonify([{
        "id": n.id,
        "message": n.message,
        "timestamp": n.timestamp.strftime("%H:%M")
    } for n in notifs])

@main.route("/api/notifications/read/<int:notif_id>", methods=["POST"])
@login_required
def mark_notif_read(notif_id):
    notif = Notification.query.filter_by(id=notif_id, user_id=current_user.id).first_or_404()
    notif.is_read = True
    db.session.commit()
    return jsonify({"status": "success"})


@main.route("/api/messages/<int:user_id>")
@login_required
def api_messages(user_id):
    # Only allow users to query their own messages, or agents to view conversations
    if current_user.role != 'agent' and current_user.id != user_id:
         return jsonify({"error": "Unauthorized"}), 403

    # Filter messages exactly strictly as user requested: WHERE receiver_id = user_id
    msgs = Message.query.filter_by(receiver_id=user_id).order_by(Message.timestamp.desc()).limit(50).all()

    # Also pull where sender_id = user_id to complete the chat history
    sent_msgs = Message.query.filter_by(sender_id=user_id).order_by(Message.timestamp.desc()).limit(50).all()
    
    all_msgs = list(set(msgs + sent_msgs))
    all_msgs.sort(key=lambda x: x.timestamp) # Chronological order

    result = []
    for m in all_msgs:
        result.append({
            "id": m.id,
            "sender_id": m.sender_id,
            "receiver_id": m.receiver_id,
            "from": m.sender.username,
            "to": m.receiver.username,
            "content": m.content,
            "is_read": m.is_read,
            "timestamp": m.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "is_mine": m.sender_id == current_user.id
        })
    return jsonify(result)

# =====================================================
# 📈 AI Price Predictor API
# =====================================================
@main.route("/api/predict_price", methods=["POST"])
def predict_price_api():
    data = request.get_json()
    loc = data.get("location", "").lower()
    ptype = data.get("type", "Apartment")
    price = float(data.get("price", 0))

    if price <= 0:
        return jsonify({"error": "Valid price required"}), 400

    # Determine growth rate based on location
    if "muscat" in loc or "مسقط" in loc: growth = 0.06
    elif "salalah" in loc or "صلالة" in loc: growth = 0.05
    elif "barka" in loc or "بركاء" in loc: growth = 0.07
    elif "sohar" in loc or "صحار" in loc: growth = 0.06
    else: growth = 0.055  # default

    # Base ROI varies slightly by type for realism (as per instructions, just calculate rent_estimate / price)
    # Using previous standard returns for rent estimate
    if "villa" in ptype.lower(): rent_estimate = price * 0.065
    elif "land" in ptype.lower(): rent_estimate = price * 0.09
    else: rent_estimate = price * 0.075

    roi = (rent_estimate / price) * 100
    val_1y = price * (1 + growth)
    val_5y = price * ((1 + growth) ** 5)

    return jsonify({
        "estimated_price": round(val_1y, 0),
        "roi": round(roi, 1),
        "yearly_income": round(rent_estimate, 0),
        "value_1y": round(val_1y, 0),
        "value_5y": round(val_5y, 0),
        "reason": f"Expected {growth*100}% annual growth in this area driven by local market trends and ongoing developments."
    })

# =====================================================
# 🏠 Customer Recommendations API
# =====================================================
@main.route("/api/recommendations")
def api_recommendations():
    all_props = Property.query.all()
    prices = [float(p.price) for p in all_props if p.price]
    avg = sum(prices) / len(prices) if prices else 100000

    scored = []
    for p in all_props:
        s = calculate_score({'price': p.price, 'type': p.type, 'location': p.location}, avg)
        scored.append({**p.to_dict(), "score": s})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return jsonify(scored[:6])