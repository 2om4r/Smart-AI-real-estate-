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

    @property
    def is_new(self):
        """Property is 'new' if created within last 30 days."""
        return (datetime.utcnow() - self.created_at) < timedelta(days=30)

    # Relationships
    images = db.relationship('PropertyImage', backref='property', lazy=True, cascade="all, delete-orphan")
    favorited_by = db.relationship('Favorite', backref='property', lazy=True, cascade="all, delete-orphan")
    inquiries = db.relationship('Inquiry', backref='property', lazy=True, cascade="all, delete-orphan")

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

class ChatLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_message = db.Column(db.Text, nullable=False)
    bot_response = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True) # Can be anonymous

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
