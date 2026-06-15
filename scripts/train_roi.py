import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
import pickle
import os
import sqlite3
from pathlib import Path

# 1. Load Data
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "instance" / "database" / "ROI oman.db"

if not DB_PATH.exists():
    print(f"Error: Database {DB_PATH} not found.")
    exit(1)

print(f"Connecting to database: {DB_PATH}")
conn = sqlite3.connect(str(DB_PATH))
table_name = "oman_real_estate_roi_1050"

try:
    df = pd.read_sql(f'SELECT * FROM "{table_name}"', conn)
except Exception as e:
    print(f"Failed to read table: {e}")
    exit(1)
finally:
    conn.close()

print(f"Loaded {len(df)} ROI records from database successfully.")

X = df.drop(columns=['target_roi_percentage'])
y = df['target_roi_percentage']

# 2. Preprocessing
# We have categorical: property_type, location, status
# We have numerical: price_omr, area_sqm, age_years, services_score
categorical_cols = ['property_type', 'location', 'status']
numerical_cols = ['price_omr', 'area_sqm', 'age_years', 'services_score']

# Create transformers
numeric_transformer = StandardScaler()
categorical_transformer = OneHotEncoder(handle_unknown='ignore')

# Combine transformers into a preprocessor
preprocessor = ColumnTransformer(
    transformers=[
        ('num', numeric_transformer, numerical_cols),
        ('cat', categorical_transformer, categorical_cols)
    ]
)

# 3. Create Pipeline
model_pipeline = Pipeline(steps=[
    ('preprocessor', preprocessor),
    ('regressor', RandomForestRegressor(n_estimators=100, random_state=42))
])

# 4. Train Model
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
model_pipeline.fit(X_train, y_train)

# 5. Evaluate (Optional, just to see)
score = model_pipeline.score(X_test, y_test)
print(f"Model R2 Score: {score:.4f}")

# 6. Save Model
output_file = PROJECT_ROOT / "models" / "registry" / "roi_predictor.pkl"
with open(output_file, 'wb') as f:
    pickle.dump(model_pipeline, f)

print(f"Success! ROI Model saved to {output_file}")
