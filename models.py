from datetime import datetime, timedelta
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db, login_manager

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(20), nullable=False, default='customer') # customer, agent, admin
    full_name = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    profile_image = db.Column(db.String(100), default='default.jpg')
    preferred_language = db.Column(db.String(2), default='en')
    theme_mode = db.Column(db.String(10), default='light')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    properties = db.relationship('Property', backref='agent', lazy=True)
    favorites = db.relationship('Favorite', backref='user', lazy=True)
    inquiries = db.relationship('Inquiry', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"User('{self.username}', '{self.email}', '{self.role}')"

class Property(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, nullable=False)
    location = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(50), nullable=False) # Villa, Apartment, etc.
    size = db.Column(db.Float) # Size in sq meters/feet
    bedrooms = db.Column(db.Integer)
    bathrooms = db.Column(db.Integer)
    city = db.Column(db.String(100))
    address = db.Column(db.String(200))
    agent_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    is_surooh = db.Column(db.Boolean, default=False, nullable=False)  # Surooh project flag
    is_omran  = db.Column(db.Boolean, default=False, nullable=False)  # OMRAN project flag

    # New Map fields
    latitude  = db.Column(db.Float)
    longitude = db.Column(db.Float)
    
    # Surooh/Project metadata
    region      = db.Column(db.String(100))
    total_units = db.Column(db.Integer)
    villas      = db.Column(db.Integer)
    apartments  = db.Column(db.Integer)
    investment_omr = db.Column(db.Float)
    data_type   = db.Column(db.String(50))

    # Status & New property flags
    status = db.Column(db.String(30), default='available')  # available, under_construction

    # ── Project hierarchy ──────────────────────────────────────────
    # يَدعم إضافة "مشروع" (project) يَحتوي عدَّة وحدات (units)
    # is_project=True  → مشروع رئيسي (parent)
    # parent_project_id → الوحدة تنتمي لمشروع (child)
    is_project        = db.Column(db.Boolean, default=False, nullable=False)
    parent_project_id = db.Column(db.Integer, db.ForeignKey('property.id'), nullable=True)
    developer         = db.Column(db.String(100))   # اسم المطوِّر
    completion_date   = db.Column(db.String(50))    # تاريخ التسليم المتوقَّع

    # ── 🚨 ML Anomaly Detection ─────────────────────────────────
    # عند إضافة عقار، نُقارن سعره بتوَقُّع ML — إن انحرَفَ بـ >50% نُعلِّمه
    # When listed, RF predicts a price. If listing deviates >50%, flag it.
    flagged_anomaly  = db.Column(db.Boolean, default=False)
    anomaly_severity = db.Column(db.String(20))   # 'low' | 'medium' | 'high'
    anomaly_reason   = db.Column(db.String(255))  # human-readable explanation
    ml_predicted_at_listing = db.Column(db.Float)  # ML estimate when added

    # ── 💰 Sale tracking (for Active Learning) ──────────────────
    # يَتم تَعبئتها عند تَأكيد البيع — تَصبح ground truth للتدريب القادم
    sold_price       = db.Column(db.Float)
    sold_date        = db.Column(db.DateTime)
    days_on_market   = db.Column(db.Integer)

    @property
    def is_new(self):
        """Property is 'new' if created within last 30 days."""
        return (datetime.utcnow() - self.created_at) < timedelta(days=30)

    # Relationships
    images = db.relationship('PropertyImage', backref='property', lazy=True, cascade="all, delete-orphan")
    favorited_by = db.relationship('Favorite', backref='property', lazy=True, cascade="all, delete-orphan")
    inquiries = db.relationship('Inquiry', backref='property', lazy=True, cascade="all, delete-orphan")

    # وحدات المشروع: project.units → [unit1, unit2, ...]
    units = db.relationship(
        'Property',
        backref=db.backref('parent_project', remote_side='Property.id'),
        lazy='dynamic',
        foreign_keys=[parent_project_id],
    )

    def __repr__(self):
        return f"Property('{self.title}', '{self.type}', '{self.price}')"

    def to_dict(self):
        # Find main image
        main_img = None
        for img in self.images:
            if img.is_main:
                main_img = img.image_filename
                break
        if not main_img and self.images:
            main_img = self.images[0].image_filename

        return {
            'id': self.id,
            'title': self.title,
            'name': self.title.split(']', 1)[-1].strip() if ']' in self.title else self.title,
            'description': self.description,
            'price': self.price,
            'location': self.location,
            'type': self.type,
            'size': self.size,
            'bedrooms': self.bedrooms,
            'bathrooms': self.bathrooms,
            'city': self.city or self.location,
            'address': self.address,
            'lat': self.latitude,
            'lng': self.longitude,
            'is_surooh': self.is_surooh,
            'is_omran': self.is_omran,
            'is_new': self.is_new,
            'status': self.status or 'available',
            'image_url': f'/static/uploads/properties/{main_img}' if main_img else None,
            # Surooh specific
            'region': self.region,
            'total_units': self.total_units or 0,
            'villas': self.villas or 0,
            'apartments': self.apartments or 0,
            'investment': (self.investment_omr or 0) / 1_000_000,
            'data_type': self.data_type or 'Project',
        }


class PropertyImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    image_filename = db.Column(db.String(100), nullable=False)
    is_main = db.Column(db.Boolean, default=False)
    property_id = db.Column(db.Integer, db.ForeignKey('property.id'), nullable=False)

class Favorite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey('property.id'), nullable=False)

class Inquiry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey('property.id'), nullable=False)

class Area(db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(100), nullable=False)
    latitude      = db.Column(db.Float, nullable=False)
    longitude     = db.Column(db.Float, nullable=False)
    avg_price     = db.Column(db.Float, nullable=False, default=0)
    demand        = db.Column(db.Float, nullable=False, default=0)   # 0-100
    price_growth  = db.Column(db.Float, nullable=False, default=0)   # 0-100
    services      = db.Column(db.Float, nullable=False, default=0)   # 0-100
    listing_count = db.Column(db.Float, nullable=False, default=0)   # 0-100

    @property
    def score(self):
        return (self.demand * 0.4) + (self.price_growth * 0.3) + \
               (self.services * 0.2) + (self.listing_count * 0.1)

    @property
    def color(self):
        s = self.score
        if s > 80:   return 'red'
        if s >= 50:  return 'orange'
        return 'green'

    @property
    def recommendation(self):
        s = self.score
        if s > 80:   return 'Strong Buy'
        if s >= 50:  return 'Moderate'
        return 'Risky'

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name,
            'lat': self.latitude, 'lng': self.longitude,
            'avg_price': self.avg_price,
            'score': round(self.score, 1),
            'color': self.color,
            'recommendation': self.recommendation,
            'demand': self.demand,
            'price_growth': self.price_growth,
        }

    def __repr__(self):
        return f"Area('{self.name}', score={self.score:.1f})"

# ─── Conversation ─────────────────────────────────────────────────────────────
# نموذج المحادثة: يجمع عدة رسائل تحت محادثة واحدة لحفظ السياق
class Conversation(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)   # null = anonymous
    started_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    ended_at   = db.Column(db.DateTime, nullable=True)
    language   = db.Column(db.String(5), default='en')  # 'en' or 'ar'
    logs       = db.relationship('ChatLog', backref='conversation', lazy=True,
                                 cascade='all, delete-orphan')

    def __repr__(self):
        return f"Conversation(id={self.id}, user_id={self.user_id})"


# ─── ChatLog ──────────────────────────────────────────────────────────────────
# سجل كل رسالة في المحادثة مع تفاصيل الأداء
class ChatLog(db.Model):
    id              = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'), nullable=True)
    user_id         = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    user_message    = db.Column(db.Text, nullable=False)
    bot_response    = db.Column(db.Text, nullable=False)
    intent          = db.Column(db.String(50), nullable=True)   # search, investment, compare, etc.
    language        = db.Column(db.String(5), default='en')     # 'en' or 'ar'
    tokens_used     = db.Column(db.Integer, nullable=True)      # GPT tokens consumed
    response_time   = db.Column(db.Float, nullable=True)        # seconds to respond
    timestamp       = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Relationship to feedback (one log → one optional feedback)
    feedback        = db.relationship('ChatFeedback', backref='chat_log', uselist=False,
                                      cascade='all, delete-orphan')

    def __repr__(self):
        return f"ChatLog(id={self.id}, intent='{self.intent}', tokens={self.tokens_used})"


# ─── ChatFeedback ──────────────────────────────────────────────────────────────
# تقييم المستخدم لكل رسالة (إيجابي / سلبي + تعليق اختياري)
class ChatFeedback(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    chat_log_id = db.Column(db.Integer, db.ForeignKey('chat_log.id'), nullable=False)
    rating      = db.Column(db.Integer, nullable=False)          # 1 = 👍, 0 = 👎
    comment     = db.Column(db.Text, nullable=True)
    timestamp   = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f"ChatFeedback(log_id={self.chat_log_id}, rating={self.rating})"

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey('property.id'), nullable=True)
    content = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_messages')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_messages')

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

class RecentlyViewed(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey('property.id'), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    property = db.relationship('Property', backref='viewed_by')


# ─── InvestmentRequest ────────────────────────────────────────────────────────
# طلب استثمار — يُنشأ عندما يطلب المستخدم الاستثمار مع وكيل معين عبر الشاتبوت
# Created when a user requests investment with a specific agent via the chatbot
class InvestmentRequest(db.Model):
    id       = db.Column(db.Integer, primary_key=True)

    # nullable=True — المستخدمون المجهولون مسموح لهم بالطلب
    # nullable=True allows anonymous (non-logged-in) users to submit requests
    user_id  = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    # الوكيل المستهدف بالطلب
    # The agent this request is directed to
    agent_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    # 'surooh' | 'omran' | agent username — مصدر الطلب / نوع المشروع
    project  = db.Column(db.String(50), nullable=True)

    # الرسالة الأصلية من المستخدم كما وردت من الشاتبوت
    # Original user message captured from the chatbot
    message  = db.Column(db.Text, nullable=True)

    # دورة الحياة: pending → contacted → closed
    # Lifecycle: pending → contacted → closed
    status   = db.Column(db.String(20), nullable=False, default='pending')

    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # foreign_keys مطلوب صراحةً لأن كلا العلاقتين تشيران إلى نفس الجدول (User)
    # explicit foreign_keys required because both FKs point to the same table
    user  = db.relationship('User', foreign_keys=[user_id],
                            backref='investment_requests_sent')
    agent = db.relationship('User', foreign_keys=[agent_id],
                            backref='investment_requests_received')

    def __repr__(self):
        return (f"InvestmentRequest(id={self.id}, agent_id={self.agent_id}, "
                f"status='{self.status}')")


# ─────────────────────────────────────────────────────────────────────────────
# 🌲 ML TRAINING HISTORY — tracks every retrain run
# يَحفظ سجلّاً كاملاً لكل عملية تَدريب: الإصدار، الدقَّة، السبب، الحالة
# ─────────────────────────────────────────────────────────────────────────────

class TrainingHistory(db.Model):
    """
    Audit log for every ML retraining run.

    Used by:
      • scripts/retrain.py — writes a row after each successful train
      • /api/ml/history    — admin sees all past runs
      • /api/ml/rollback   — can pick previous version by id
    """
    __tablename__ = 'training_history'

    id            = db.Column(db.Integer, primary_key=True)
    version       = db.Column(db.String(40), unique=True, nullable=False)
    model_path    = db.Column(db.String(255), nullable=False)

    # Metrics
    r2_score      = db.Column(db.Float)               # cross-validation R²
    rows_count    = db.Column(db.Integer)             # total training rows
    new_rows      = db.Column(db.Integer, default=0)  # new since previous train

    # Training metadata
    trained_at    = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    duration_sec  = db.Column(db.Float)                # how long it took
    trigger       = db.Column(db.String(30))            # 'scheduled' | 'threshold' | 'manual'

    # Deployment status
    deployed      = db.Column(db.Boolean, default=False)
    is_active     = db.Column(db.Boolean, default=False)    # only one row is_active=True
    notes         = db.Column(db.Text)

    def __repr__(self):
        active = " ★ ACTIVE" if self.is_active else ""
        return f"<TrainingHistory {self.version} R²={self.r2_score:.3f}{active}>"

    def to_dict(self):
        return {
            'id':           self.id,
            'version':      self.version,
            'r2_score':     round(self.r2_score, 4) if self.r2_score else None,
            'rows_count':   self.rows_count,
            'new_rows':     self.new_rows,
            'trained_at':   self.trained_at.isoformat() if self.trained_at else None,
            'duration_sec': round(self.duration_sec, 1) if self.duration_sec else None,
            'trigger':      self.trigger,
            'deployed':     self.deployed,
            'is_active':    self.is_active,
            'notes':        self.notes,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 🎯 PREDICTION LOG — every ML prediction is recorded for active learning
# سِجلّ التَنَبُّؤات: نَحفظ كل تَنَبُّؤ + النتيجة الفعليَّة (عند البيع)
# هذا يَفتح الباب لـ Active Learning — تَحسين النموذج من النتائج الفعليَّة
# ─────────────────────────────────────────────────────────────────────────────

class PredictionLog(db.Model):
    """
    Audit log of every ML prediction.

    When a property sells, the actual_price is filled in. This gives us
    ground truth to measure ML accuracy over time and feed back into
    training (weighted by confirmation).
    """
    __tablename__ = 'prediction_log'

    id              = db.Column(db.Integer, primary_key=True)
    property_id     = db.Column(db.Integer, db.ForeignKey('property.id'), nullable=True)

    # What ML predicted
    predicted_price = db.Column(db.Float, nullable=False)
    confidence      = db.Column(db.Float)         # 0-100 from RF tree variance
    model_version   = db.Column(db.String(40))    # which RF version made this prediction

    # Ground truth (filled when property sells)
    actual_price    = db.Column(db.Float)
    error_pct       = db.Column(db.Float)         # |actual - predicted| / actual × 100

    # Context
    listing_price   = db.Column(db.Float)         # what agent listed it at
    features_json   = db.Column(db.Text)          # JSON dump of inputs

    # Timestamps
    predicted_at    = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    confirmed_at    = db.Column(db.DateTime)      # filled when actual_price set

    property = db.relationship('Property', backref='predictions')

    def __repr__(self):
        return (f"<PredictionLog #{self.id} pred={self.predicted_price:.0f} "
                f"actual={self.actual_price or '—'}>")

    def to_dict(self):
        return {
            'id':              self.id,
            'property_id':     self.property_id,
            'predicted_price': self.predicted_price,
            'actual_price':    self.actual_price,
            'error_pct':       self.error_pct,
            'confidence':      self.confidence,
            'model_version':   self.model_version,
            'predicted_at':    self.predicted_at.isoformat() if self.predicted_at else None,
            'confirmed_at':    self.confirmed_at.isoformat() if self.confirmed_at else None,
        }
