import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder

preprocessor = ColumnTransformer(
    transformers=[
        ('cat', OneHotEncoder(handle_unknown='ignore'), ['type', 'location']),
    ],
    remainder='passthrough'
)

model = RandomForestRegressor(n_estimators=100, random_state=42)
trained = False

def train_price_model(properties):
    global trained
    if not properties:
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