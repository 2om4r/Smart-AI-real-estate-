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
    role = db.Column(db.String(20), nullable=False, default='customer') 
    full_name = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    profile_image = db.Column(db.String(100), default='default.jpg')
    preferred_language = db.Column(db.String(2), default='en')
    theme_mode = db.Column(db.String(10), default='light')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
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
    type = db.Column(db.String(50), nullable=False) 
    size = db.Column(db.Float) 
    bedrooms = db.Column(db.Integer)
    bathrooms = db.Column(db.Integer)
    city = db.Column(db.String(100))
    address = db.Column(db.String(200))
    agent_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    is_surooh = db.Column(db.Boolean, default=False, nullable=False)  
    is_omran  = db.Column(db.Boolean, default=False, nullable=False)  

    latitude  = db.Column(db.Float)
    longitude = db.Column(db.Float)
    
    region      = db.Column(db.String(100))
    total_units = db.Column(db.Integer)
    villas      = db.Column(db.Integer)
    apartments  = db.Column(db.Integer)
    investment_omr = db.Column(db.Float)
    data_type   = db.Column(db.String(50))

    status = db.Column(db.String(30), default='available')  

    is_project        = db.Column(db.Boolean, default=False, nullable=False)
    parent_project_id = db.Column(db.Integer, db.ForeignKey('property.id'), nullable=True)
    developer         = db.Column(db.String(100))   
    completion_date   = db.Column(db.String(50))    

    flagged_anomaly  = db.Column(db.Boolean, default=False)
    anomaly_severity = db.Column(db.String(20))   
    anomaly_reason   = db.Column(db.String(255))  
    ml_predicted_at_listing = db.Column(db.Float)  

    sold_price       = db.Column(db.Float)
    sold_date        = db.Column(db.DateTime)
    days_on_market   = db.Column(db.Integer)

    @property
    def is_new(self):
        
        return (datetime.utcnow() - self.created_at) < timedelta(days=30)

    images = db.relationship('PropertyImage', backref='property', lazy=True, cascade="all, delete-orphan")
    favorited_by = db.relationship('Favorite', backref='property', lazy=True, cascade="all, delete-orphan")
    inquiries = db.relationship('Inquiry', backref='property', lazy=True, cascade="all, delete-orphan")

    units = db.relationship(
        'Property',
        backref=db.backref('parent_project', remote_side='Property.id'),
        lazy='dynamic',
        foreign_keys=[parent_project_id],
    )

    def __repr__(self):
        return f"Property('{self.title}', '{self.type}', '{self.price}')"

    def to_dict(self):
        
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
    demand        = db.Column(db.Float, nullable=False, default=0)   
    price_growth  = db.Column(db.Float, nullable=False, default=0)   
    services      = db.Column(db.Float, nullable=False, default=0)   
    listing_count = db.Column(db.Float, nullable=False, default=0)   

    @property
    def _ml_pred(self):
        if not hasattr(self, '_ml_prediction'):
            from area_ml import area_ml_engine
            self._ml_prediction = area_ml_engine.predict_area(
                self.demand, self.price_growth, self.services, self.listing_count
            )
        return self._ml_prediction

    @property
    def score(self):
        return self._ml_pred['score']

    @property
    def color(self):
        return self._ml_pred['color']

    @property
    def recommendation(self):
        return self._ml_pred['recommendation']

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

class Conversation(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)   
    started_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    ended_at   = db.Column(db.DateTime, nullable=True)
    language   = db.Column(db.String(5), default='en')  
    logs       = db.relationship('ChatLog', backref='conversation', lazy=True,
                                 cascade='all, delete-orphan')

    def __repr__(self):
        return f"Conversation(id={self.id}, user_id={self.user_id})"

class ChatLog(db.Model):
    id              = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'), nullable=True)
    user_id         = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    user_message    = db.Column(db.Text, nullable=False)
    bot_response    = db.Column(db.Text, nullable=False)
    intent          = db.Column(db.String(50), nullable=True)   
    language        = db.Column(db.String(5), default='en')     
    tokens_used     = db.Column(db.Integer, nullable=True)      
    response_time   = db.Column(db.Float, nullable=True)        
    timestamp       = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    feedback        = db.relationship('ChatFeedback', backref='chat_log', uselist=False,
                                      cascade='all, delete-orphan')

    def __repr__(self):
        return f"ChatLog(id={self.id}, intent='{self.intent}', tokens={self.tokens_used})"

class ChatFeedback(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    chat_log_id = db.Column(db.Integer, db.ForeignKey('chat_log.id'), nullable=False)
    rating      = db.Column(db.Integer, nullable=False)          
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

class InvestmentRequest(db.Model):
    id       = db.Column(db.Integer, primary_key=True)

    user_id  = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    agent_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    project  = db.Column(db.String(50), nullable=True)

    message  = db.Column(db.Text, nullable=True)

    status   = db.Column(db.String(20), nullable=False, default='pending')

    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user  = db.relationship('User', foreign_keys=[user_id],
                            backref='investment_requests_sent')
    agent = db.relationship('User', foreign_keys=[agent_id],
                            backref='investment_requests_received')

    def __repr__(self):
        return (f"InvestmentRequest(id={self.id}, agent_id={self.agent_id}, "
                f"status='{self.status}')")

class TrainingHistory(db.Model):
    
    __tablename__ = 'training_history'

    id            = db.Column(db.Integer, primary_key=True)
    version       = db.Column(db.String(40), unique=True, nullable=False)
    model_path    = db.Column(db.String(255), nullable=False)

    r2_score      = db.Column(db.Float)               
    rows_count    = db.Column(db.Integer)             
    new_rows      = db.Column(db.Integer, default=0)  

    trained_at    = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    duration_sec  = db.Column(db.Float)                
    trigger       = db.Column(db.String(30))            

    deployed      = db.Column(db.Boolean, default=False)
    is_active     = db.Column(db.Boolean, default=False)    
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

class PredictionLog(db.Model):
    
    __tablename__ = 'prediction_log'

    id              = db.Column(db.Integer, primary_key=True)
    property_id     = db.Column(db.Integer, db.ForeignKey('property.id'), nullable=True)

    predicted_price = db.Column(db.Float, nullable=False)
    confidence      = db.Column(db.Float)         
    model_version   = db.Column(db.String(40))    

    actual_price    = db.Column(db.Float)
    error_pct       = db.Column(db.Float)         

    listing_price   = db.Column(db.Float)         
    features_json   = db.Column(db.Text)          

    predicted_at    = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    confirmed_at    = db.Column(db.DateTime)      

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
