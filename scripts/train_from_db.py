"""
scripts/train_from_db.py
========================
يُدرِّب نموذج ML على بيانات omanpDatabase.db الحقيقية (2000 عقار × 8 سنوات)
ويُحدِّث جدول Area بمعدلات CAGR الحقيقية.

Trains the ML model on real time-series data from omanpDatabase.db
(2000 properties × 8 years = 16,000 data points) and updates
Area.price_growth with real CAGR values.

Usage (from project root, venv activated):
    python scripts/train_from_db.py

What it does:
  1. Reads all 2000 rows from omanpDatabase.db
  2. Calculates per-area CAGR (2019-2026) and recent CAGR (2023-2026)
  3. Updates Area.price_growth in the app DB with real CAGR-based scores
  4. Retrains RandomForest on 16,000 data points (all years × all properties)
  5. Saves trained model to ./ml_model_trained.pkl for auto-loading on startup
"""

import os
import sys
import pickle
import logging
import sqlite3

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
from sklearn.model_selection import cross_val_score

# ── Project root on path ──────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
SOURCE_DB  = os.environ.get("SOURCE_DB", "/Users/omar/Desktop/omanpDatabase.db")
MODEL_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                          "ml_model_trained.pkl")

TABLE_NAME = "oman properties 2000"

PRICE_COLS = [
    'Price_2019_OMR', 'Price_2020_OMR', 'Price_2021_OMR', 'Price_2022_OMR',
    'Price_2023_OMR', 'Price_2024_OMR', 'Price_2025_OMR', 'Price_2026_OMR',
]
YEARS = [2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]


# =============================================================================
# STEP 1 — Load from SQLite DB
# =============================================================================

def load_db() -> pd.DataFrame:
    """
    Read all rows from omanpDatabase.db into a DataFrame.
    قراءة جميع الصفوف من omanpDatabase.db إلى DataFrame.
    """
    logger.info(f"Connecting to: {SOURCE_DB}")
    if not os.path.exists(SOURCE_DB):
        raise FileNotFoundError(f"Database not found: {SOURCE_DB}")

    conn = sqlite3.connect(SOURCE_DB)
    df   = pd.read_sql_query(f'SELECT * FROM "{TABLE_NAME}"', conn)
    conn.close()

    logger.info(f"Loaded {len(df)} rows from '{TABLE_NAME}'.")

    # Clean nulls
    df['Sqm']       = pd.to_numeric(df['Sqm'],       errors='coerce').fillna(0)
    df['Bedrooms']  = pd.to_numeric(df['Bedrooms'],  errors='coerce').fillna(0)
    df['Bathrooms'] = pd.to_numeric(df['Bathrooms'], errors='coerce').fillna(0)
    df['Floor']     = pd.to_numeric(df['Floor'],     errors='coerce').fillna(0)
    df['Area']      = df['Area'].fillna(df['Governorate'])

    for col in PRICE_COLS:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    return df


# =============================================================================
# STEP 2 — Calculate Real CAGR per Area & Governorate
# =============================================================================

def calc_cagr(df: pd.DataFrame) -> pd.DataFrame:
    """
    Full CAGR  (2019→2026, 7 years): long-run rate
    Recent CAGR (2023→2026, 3 years): forward-looking rate used for predictions

    CAGR = (P_end / P_start)^(1/n) - 1
    """
    df = df.copy()
    # avoid division by zero
    mask = df['Price_2019_OMR'] > 0
    df.loc[mask, 'cagr_full']   = (
        (df.loc[mask, 'Price_2026_OMR'] / df.loc[mask, 'Price_2019_OMR']) ** (1/7) - 1
    )
    mask3 = df['Price_2023_OMR'] > 0
    df.loc[mask3, 'cagr_recent'] = (
        (df.loc[mask3, 'Price_2026_OMR'] / df.loc[mask3, 'Price_2023_OMR']) ** (1/3) - 1
    )

    by_area = (df.groupby(['Governorate', 'Area'])
               .agg(
                   cagr_full_mean   = ('cagr_full',   'mean'),
                   cagr_full_n      = ('cagr_full',   'count'),
                   cagr_recent_mean = ('cagr_recent', 'mean'),
                   cagr_recent_n    = ('cagr_recent', 'count'),
               )
               .reset_index())

    # Keep areas with at least 3 data points
    by_area = by_area[by_area['cagr_full_n'] >= 3].copy()
    logger.info(f"CAGR computed for {len(by_area)} areas.")
    return by_area


# =============================================================================
# STEP 3 — Update Area.price_growth in App DB
# =============================================================================

def update_area_table(cagr_df: pd.DataFrame) -> None:
    """
    Convert CAGR → price_growth score (0-100) and update the app DB.
    تحويل CAGR إلى سكور 0-100 وتحديث جدول Area في قاعدة بيانات التطبيق.

    Scale: CAGR 0% → score 0 | CAGR 7% → score 100 (capped)
    Using recent CAGR (2023-2026) as the forward-looking rate.
    يستخدم CAGR الأخير (2023-2026) كمعدل نمو مستقبلي.
    """
    from app import create_app
    from models import Area
    from extensions import db

    app = create_app()
    with app.app_context():
        updated = skipped = 0

        for _, row in cagr_df.iterrows():
            area_name = row['Area']
            # Prefer recent CAGR (forward-looking); fall back to full CAGR
            cagr_val  = (row['cagr_recent_mean']
                         if row['cagr_recent_n'] >= 3
                         else row['cagr_full_mean'])

            if pd.isna(cagr_val):
                skipped += 1
                continue

            # Map CAGR → 0-100 score (cap at 100)
            # 7% annual growth = score 100 (excellent market)
            score = float(min(round((cagr_val / 0.07) * 100, 1), 100.0))
            score = max(score, 0.0)

            db_areas = Area.query.filter(
                Area.name.ilike(f"%{area_name}%")
            ).all()

            for db_area in db_areas:
                db_area.price_growth = score
                updated += 1

        db.session.commit()
        logger.info(f"Area table updated: {updated} rows updated, {skipped} skipped.")


# =============================================================================
# STEP 4 — Build Long-Format Training Dataset (property × year)
# =============================================================================

def build_training_data(df: pd.DataFrame):
    """
    Melt 8 price columns → long format.
    One row per (property, year) — 2000 × 8 = 16,000 training rows.
    تحويل أعمدة الأسعار إلى صيغة طويلة: صف واحد لكل (عقار × سنة).
    """
    records = []
    for _, row in df.iterrows():
        for year, col in zip(YEARS, PRICE_COLS):
            price = float(row[col])
            if price <= 0:
                continue
            records.append({
                'type':        str(row.get('Property_Type') or 'Unknown'),
                'governorate': str(row.get('Governorate')   or 'Unknown'),
                'area':        str(row.get('Area')          or 'Unknown'),
                'sqm':         float(row.get('Sqm', 0)      or 0),
                'bedrooms':    float(row.get('Bedrooms', 0) or 0),
                'bathrooms':   float(row.get('Bathrooms', 0)or 0),
                'floor':       float(row.get('Floor', 0)    or 0),
                'year':        int(year),
                'price':       price,
            })

    train_df = pd.DataFrame(records)
    logger.info(f"Training dataset: {len(train_df):,} rows "
                f"({df.shape[0]} properties × {len(YEARS)} years).")

    X = train_df[['type', 'governorate', 'area',
                  'sqm', 'bedrooms', 'bathrooms', 'floor', 'year']]
    y = train_df['price']
    return X, y


# =============================================================================
# STEP 5 — Train RandomForest & Save Pickle
# =============================================================================

def train_and_save(X: pd.DataFrame, y: pd.Series) -> None:
    """
    Train a RandomForestRegressor on the full dataset.
    تدريب RandomForestRegressor على البيانات الكاملة وحفظ النموذج.

    Features:
      Categorical (OHE): type, governorate, area
      Numeric (passthrough): sqm, bedrooms, bathrooms, floor, year

    Saves preprocessor + model together to ml_model_trained.pkl.
    """
    preprocessor = ColumnTransformer(
        transformers=[
            ('cat', OneHotEncoder(handle_unknown='ignore'),
             ['type', 'governorate', 'area']),
        ],
        remainder='passthrough',   # sqm, bedrooms, bathrooms, floor, year
    )

    rf = RandomForestRegressor(
        n_estimators  = 200,       # 200 أشجار
        max_depth     = 25,
        min_samples_leaf = 2,
        random_state  = 42,
        n_jobs        = -1,        # كل cores
    )

    logger.info("Fitting preprocessor...")
    X_transformed = preprocessor.fit_transform(X)

    logger.info("Training RandomForest on 16,000 rows (200 trees)...")
    rf.fit(X_transformed, y)

    # Cross-val R² on a 2,000-row sample (fast estimate)
    sample_idx = np.random.default_rng(42).choice(
        len(y), min(2000, len(y)), replace=False
    )
    cv = cross_val_score(
        rf,
        X_transformed[sample_idx],
        y.iloc[sample_idx],
        cv=3, scoring='r2', n_jobs=-1,
    )
    logger.info(f"Cross-val R²: {cv.round(3)} — mean {cv.mean():.3f}")

    # Save to pickle
    bundle = {'preprocessor': preprocessor, 'model': rf}
    with open(MODEL_PATH, 'wb') as fh:
        pickle.dump(bundle, fh)
    logger.info(f"Model saved → {MODEL_PATH}")

    # Hot-reload in-memory ml_model globals (immediate effect in same process)
    import ml_model as mlm
    mlm.preprocessor = preprocessor
    mlm.model        = rf
    mlm.trained      = True
    logger.info("In-memory ml_model globals updated.")


# =============================================================================
# STEP 6 — Print CAGR Summary Table
# =============================================================================

def print_summary(cagr_df: pd.DataFrame) -> None:
    gov = (cagr_df.groupby('Governorate')
           .agg(cagr_pct=('cagr_recent_mean', lambda x: x.mean() * 100),
                n_areas=('Area', 'count'))
           .reset_index()
           .sort_values('cagr_pct', ascending=False))

    print("\n" + "═"*58)
    print("  REAL ANNUAL GROWTH RATE BY GOVERNORATE  (2023 → 2026)")
    print("═"*58)
    for _, r in gov.iterrows():
        bar = "█" * max(int(r['cagr_pct'] / 0.4), 1)
        print(f"  {r['Governorate']:<28} {r['cagr_pct']:>5.2f}%  {bar}")
    print("═"*58)
    print(f"  Source: omanpDatabase.db  |  2,000 properties  |  8 years\n")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    logger.info("══════════════════════════════════════════")
    logger.info("  ML Training Pipeline — omanpDatabase.db")
    logger.info("══════════════════════════════════════════")

    # 1. Load
    df = load_db()

    # 2. CAGR
    cagr_df = calc_cagr(df)
    print_summary(cagr_df)

    # 3. Update Area table
    logger.info("Updating Area.price_growth in app database...")
    try:
        update_area_table(cagr_df)
    except Exception as e:
        logger.warning(f"DB update skipped: {e}")

    # 4. Build training data
    X, y = build_training_data(df)

    # 5. Train & save
    train_and_save(X, y)

    logger.info("══════════════════════════════════════════")
    logger.info("  Pipeline complete!")
    logger.info(f"  Restart Flask to auto-load {MODEL_PATH}")
    logger.info("══════════════════════════════════════════")
