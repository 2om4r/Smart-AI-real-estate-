import os
import pickle
import logging
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder

logger = logging.getLogger(__name__)

# Path to the persisted model trained on 16,000 CSV data points
# مسار النموذج المُدرَّب المحفوظ على 16,000 نقطة من CSV
_MODEL_PKL = os.path.join(os.path.dirname(__file__), "ml_model_trained.pkl")

preprocessor = ColumnTransformer(
    transformers=[
        ('cat', OneHotEncoder(handle_unknown='ignore'), ['type', 'location']),
    ],
    remainder='passthrough'
)

model   = RandomForestRegressor(n_estimators=100, random_state=42)
trained = False

# ── Auto-load persisted model if pickle exists ─────────────────────────────
# يُحمَّل النموذج المحفوظ تلقائياً عند وجود ملف pickle
if os.path.exists(_MODEL_PKL):
    try:
        with open(_MODEL_PKL, 'rb') as _f:
            _bundle      = pickle.load(_f)
            preprocessor = _bundle['preprocessor']
            model        = _bundle['model']
            trained      = True
        logger.info(f"[ML] Loaded pre-trained model from {_MODEL_PKL}")
    except Exception as _e:
        logger.warning(f"[ML] Could not load pickle: {_e} — will train on DB data.")

def train_price_model(properties):
    global trained
    if trained or not properties:
        return

    # Extract data
    data = []
    for p in properties:
        data.append({
            'type': p.type or 'Unknown',
            'location': p.location or 'Unknown',
            'is_surooh': 1 if p.is_surooh else 0,
            'is_omran': 1 if p.is_omran else 0,
            'size': p.size if getattr(p, 'size', None) else 0,
            'price': p.price
        })

    df = pd.DataFrame(data)
    
    # Target and Features
    X = df[['type', 'location', 'is_surooh', 'is_omran', 'size']]
    y = df['price']

    # Fit pipeline
    X_transformed = preprocessor.fit_transform(X)
    model.fit(X_transformed, y)
    trained = True

def predict_price(p):
    if not trained:
        return getattr(p, 'price', 0)
    
    # Handle passing dictionary or object
    ptype = p.type if hasattr(p, 'type') else p.get('type', 'Unknown')
    ploc = p.location if hasattr(p, 'location') else p.get('location', 'Unknown')
    psur = p.is_surooh if hasattr(p, 'is_surooh') else p.get('is_surooh', False)
    pomr = p.is_omran if hasattr(p, 'is_omran') else p.get('is_omran', False)
    psize = p.size if hasattr(p, 'size') else p.get('size', 0)
    
    df = pd.DataFrame([{
        'type': ptype or 'Unknown',
        'location': ploc or 'Unknown',
        'is_surooh': 1 if psur else 0,
        'is_omran': 1 if pomr else 0,
        'size': psize if psize else 0
    }])
    
    X_transformed = preprocessor.transform(df)
    return float(model.predict(X_transformed)[0])

def predict_prices(properties):
    if not trained or not properties:
        return [getattr(p, 'price', 0) for p in properties]
    
    data = []
    for p in properties:
        ptype = p.type if hasattr(p, 'type') else p.get('type', 'Unknown')
        ploc = p.location if hasattr(p, 'location') else p.get('location', 'Unknown')
        psur = p.is_surooh if hasattr(p, 'is_surooh') else p.get('is_surooh', False)
        pomr = p.is_omran if hasattr(p, 'is_omran') else p.get('is_omran', False)
        psize = p.size if hasattr(p, 'size') else p.get('size', 0)
        data.append({
            'type': ptype or 'Unknown',
            'location': ploc or 'Unknown',
            'is_surooh': 1 if psur else 0,
            'is_omran': 1 if pomr else 0,
            'size': psize if psize else 0
        })
        
    df = pd.DataFrame(data)
    X_transformed = preprocessor.transform(df)
    predictions = model.predict(X_transformed)
    return [float(pred) for pred in predictions]

def predict_future_price(p, years=5):
    current_predicted = predict_price(p)
    from models import Area
    
    ploc = p.location if hasattr(p, 'location') else p.get('location', '')
    base_growth = 1.05 # default 5% annual growth
    
    if ploc:
        area = Area.query.filter(Area.name.ilike(f"%{ploc}%")).first()
        if area and area.price_growth:
            # Map 0-100 logic to actual robust%
            growth_pct = max(min(area.price_growth / 10.0, 15.0), 1.0) 
            base_growth = 1.0 + (growth_pct / 100.0)
            
    future_price = current_predicted * (base_growth ** years)
    percent_growth = ((future_price - current_predicted) / current_predicted) * 100 if current_predicted > 0 else 0
    
    return float(future_price), round(percent_growth, 1)

def get_ml_investment_score(predicted_price, actual_price):
    if actual_price <= 0:
        return 50
    ratio = predicted_price / actual_price
    score = 60 + ((ratio - 1.0) * 50)
    return min(max(round(score), 0), 100)


def ensure_trained() -> bool:
    """
    Auto-train the model on all DB properties if not yet trained.
    Called by the chatbot at request time — safe to call multiple times.
    تدريب النموذج تلقائياً على عقارات قاعدة البيانات إذا لم يُدرَّب بعد.
    آمن للاستدعاء المتعدد — يُرجع True إذا كان النموذج جاهزاً.
    """
    global trained
    if trained:
        return True
    try:
        from models import Property
        props = Property.query.all()
        if props:
            train_price_model(props)
            return trained
    except Exception:
        pass
    return False


def get_future_multiplier(location: str, years: int,
                          property_type: str = "Apartment",
                          sqm: float = 100,
                          bedrooms: int = 2,
                          bathrooms: int = 2) -> float:
    """
    Return the compound price multiplier for a property over N years.

    🆕 v4 — Delegates to ml_engine.MLEngine.predict_growth()
    ─────────────────────────────────────────────────────────
    The ML engine is the single source of truth for growth predictions.
    Benefits over inline implementation:
      ✅ Thread-safe (RLock around model)
      ✅ Cached (TTL 1h — same query → instant)
      ✅ Per-property CAGR derived from RF (not just area average)
      ✅ Falls back to CAGR formula only if ml_engine unavailable

    Args:
        location:      area name (e.g. "Muscat", "Al Mouj")
        years:         years ahead to project
        property_type: Villa / Apartment / Land / Townhouse / Commercial
        sqm:           size in square meters
        bedrooms:      number of bedrooms
        bathrooms:     number of bathrooms

    Returns:
        float multiplier — future_price = current_price × multiplier
    """
    try:
        from ml_engine import ml
        if ml._loaded:
            result = ml.predict_growth({
                'type':      property_type,
                'area':      location or 'Muscat',
                'sqm':       float(sqm),
                'bedrooms':  float(bedrooms),
                'bathrooms': float(bathrooms),
                'floor':     1.0,
            }, years=years)
            multiplier = result['multiplier']
            logger.debug(
                f"[ml_model] {location} {property_type}: "
                f"{result['annual_pct']}%/yr × {years}y = ×{multiplier:.4f} "
                f"(method={result['method']}, conf={result['confidence']}%)"
            )
            return round(multiplier, 6)
    except Exception as e:
        logger.warning(f"[ml_model] ml_engine unavailable: {e} — falling back to CAGR")

    # ── Legacy CAGR fallback (kept for safety) ──────────────────────
    from models import Area
    annual_rate = 0.055
    if location and location.strip():
        area = Area.query.filter(Area.name.ilike(f"%{location}%")).first()
        if area and area.price_growth is not None:
            annual_rate = max(min(0.01 + (area.price_growth / 100.0) * 0.14, 0.15), 0.01)
    return round((1 + annual_rate) ** years, 6)