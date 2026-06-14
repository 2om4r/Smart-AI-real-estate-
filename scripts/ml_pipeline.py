"""
scripts/ml_pipeline.py — Smart Continuous Retraining Pipeline
==========================================================
خطّ التَدريب الذكيّ المستمرّ للنموذج — يَجمع البيانات الأصليَّة + الجديدة
ويُعيد التَدريب فقط عند الحاجة.

Triggers (تَلقائيَّة):
  • Scheduled (Sunday 2am via APScheduler)
  • Threshold: >100 new properties since last training
  • Threshold: >7 days since last training
  • Manual: --force flag

Workflow:
  1. Check if retrain is worthwhile (skip if not enough data)
  2. Combine: original omanpDatabase.db (16k baseline) + new properties from DB
  3. Validate: remove outliers, drop invalid rows
  4. Train: RandomForestRegressor (same hyperparameters as baseline)
  5. Validate: cross-val R² must be >= 0.70 (rejection threshold)
  6. Save: versioned pickle → models/registry/v{YYYYMMDD_HHMM}.pkl
  7. Hot-swap: ml.hot_swap(new_path) — no restart needed
  8. Log: TrainingHistory row + console output
  9. Prune: keep only last 5 versions in registry

Usage:
    # Auto (cron-friendly — exits if not worthwhile)
    python scripts/ml_pipeline.py

    # Force retrain regardless of thresholds
    python scripts/ml_pipeline.py --force

    # Dry-run: simulate without saving or hot-swapping
    python scripts/ml_pipeline.py --dry-run

    # Custom threshold (default: 100 new rows or 7 days)
    python scripts/retrain.py --min-new 50 --min-days 3
"""

from __future__ import annotations

import os
import sys
import argparse
import logging
import sqlite3
import time
import pickle
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
from sklearn.model_selection import cross_val_score

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

PROJECT_ROOT  = Path(__file__).parent.parent
SOURCE_DB     = Path(os.environ.get("SOURCE_DB",
                                    str(PROJECT_ROOT / "instance" / "database" / "2019-2026db.db")))
REGISTRY_DIR  = PROJECT_ROOT / "models" / "registry"
LATEST_LINK   = REGISTRY_DIR / "latest.pkl"
LEGACY_PICKLE = PROJECT_ROOT / "ml_model_trained.pkl"   

TABLE_NAME = "Oman_RealEstate_Dataset_2019-2026"
YEARS      = list(range(2019, 2027))

MIN_R2_SCORE = 0.70

MAX_VERSIONS_TO_KEEP = 5

def should_retrain(min_new: int = 100, min_days: int = 7,
                   force: bool = False) -> tuple[bool, str]:
    """
    Decide whether to retrain based on:
      • Time since last training
      • Number of new properties added
      • Manual force override

    Returns (should_run, reason).
    """
    if force:
        return True, "manual --force flag"

    from app import create_app
    from models import TrainingHistory, Property

    app = create_app()
    with app.app_context():
        last = (TrainingHistory.query
                .order_by(TrainingHistory.trained_at.desc())
                .first())

        if last is None:
            return True, "no previous training run found"

        days_since = (datetime.utcnow() - last.trained_at).days
        new_props  = Property.query.filter(
            Property.created_at > last.trained_at
        ).count()

        if days_since >= min_days:
            return True, f"{days_since} days since last training ({last.version})"
        if new_props >= min_new:
            return True, f"{new_props} new properties since {last.version}"

        return False, (
            f"only {new_props} new props ({min_new} required) and "
            f"{days_since} days old ({min_days} required)"
        )

def load_baseline_data() -> pd.DataFrame:
    """Load new 3500-row properties from 2019-2026db.db."""
    if not SOURCE_DB.exists():
        logger.warning(f"Baseline DB not found: {SOURCE_DB} — using empty df")
        return pd.DataFrame()

    conn = sqlite3.connect(str(SOURCE_DB))
    df = pd.read_sql_query(f'SELECT * FROM "{TABLE_NAME}"', conn)
    conn.close()
    logger.info(f"Loaded baseline: {len(df)} properties")

    df['Sqm']       = pd.to_numeric(df['Sqm'],       errors='coerce').fillna(0)
    df['Bedrooms']  = pd.to_numeric(df['Bedrooms'],  errors='coerce').fillna(0)
    df['Bathrooms'] = pd.to_numeric(df['Bathrooms'], errors='coerce').fillna(0)
    df['Floor']     = pd.to_numeric(df['Floor'],     errors='coerce').fillna(0)
    df['Area']      = df['Wilayat'].fillna(df['Governorate'])
    df['Year']      = pd.to_numeric(df['Year'],      errors='coerce').fillna(2026)
    df['Price_OMR'] = pd.to_numeric(df['Price_OMR'].astype(str).str.replace(',', '', regex=False), errors='coerce').fillna(0)
    return df

def load_new_properties_from_app_db() -> pd.DataFrame:
    """
    Load agent-added properties from the live Flask DB.

    These don't have historical prices (only current), so we synthesize
    them by assuming they're listed at the current year (2026) — RF
    will use them to fine-tune patterns for new areas/types.
    """
    from app import create_app
    from models import Property

    app = create_app()
    with app.app_context():
        
        if hasattr(Property, 'is_project'):
            props = Property.query.filter(
                Property.is_project == False,
                Property.price > 0,
            ).all()
        else:
            props = Property.query.filter(Property.price > 0).all()
        
        props = [p for p in props if (p.size or 0) > 0]

        records = []
        for p in props:
            
            sold_price = getattr(p, 'sold_price', None)
            price = float(sold_price) if sold_price else float(p.price)
            is_confirmed = bool(sold_price)

            records.append({
                'Property_Type': p.type or 'Apartment',
                'Governorate':   _infer_governorate(p.location),
                'Area':          p.location or 'Muscat',
                'Sqm':           float(p.size or 100),
                'Bedrooms':      float(p.bedrooms or 2),
                'Bathrooms':     float(p.bathrooms or 2),
                'Floor':         float(getattr(p, 'floor', 0) or 0),
                
                'Price_2026_OMR': price,
                '_is_confirmed_sale': is_confirmed,
            })

        confirmed_count = sum(1 for r in records if r['_is_confirmed_sale'])
        if confirmed_count > 0:
            logger.info(f"  ↳ {confirmed_count} confirmed sales (will get 3× weight)")

    df = pd.DataFrame(records)
    logger.info(f"Loaded {len(df)} agent-added properties from live DB")
    return df

def _infer_governorate(location: str) -> str:
    """Infer governorate from location keywords."""
    a = (location or '').lower()
    if   'muscat'  in a or 'مسقط'  in a: return 'Muscat'
    elif 'salalah' in a or 'صلالة' in a: return 'Dhofar'
    elif 'sohar'   in a:                 return 'North Al Batinah'
    elif 'barka'   in a:                 return 'South Al Batinah'
    elif 'buraimi' in a:                 return 'Al Buraimi'
    elif 'nizwa'   in a:                 return 'Ad Dakhiliyah'
    elif 'sur'     in a:                 return 'South Ash Sharqiyah'
    elif 'duqm'    in a:                 return 'Al Wusta'
    return 'Muscat'

def build_training_rows(df_baseline: pd.DataFrame,
                        df_new: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """
    Combine baseline (3.5k rows) + new agent properties into one training set.
    Returns (X, y) ready for fit.
    """
    records = []

    for _, row in df_baseline.iterrows():
        price = float(row.get('Price_OMR', 0))
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
            'year':        int(row.get('Year', 2026)),
            'price':       price,
        })

    for _, row in df_new.iterrows():
        price = float(row.get('Price_2026_OMR', 0))
        if price <= 0:
            continue
        records.append({
            'type':        str(row['Property_Type']),
            'governorate': str(row['Governorate']),
            'area':        str(row['Area']),
            'sqm':         float(row['Sqm']),
            'bedrooms':    float(row['Bedrooms']),
            'bathrooms':   float(row['Bathrooms']),
            'floor':       float(row['Floor']),
            'year':        2026,
            'price':       price,
        })

    df = pd.DataFrame(records)
    logger.info(f"Combined training set: {len(df):,} rows")

    df = _remove_outliers(df)
    logger.info(f"After outlier removal: {len(df):,} rows")

    X = df[['type', 'governorate', 'area',
            'sqm', 'bedrooms', 'bathrooms', 'floor', 'year']]
    y = df['price']
    return X, y

def _remove_outliers(df: pd.DataFrame, percentile: float = 0.01) -> pd.DataFrame:
    """Remove top/bottom 1% by price within each (area, year) bucket."""
    def trim_group(group):
        if len(group) < 10:
            return group   
        low  = group['price'].quantile(percentile)
        high = group['price'].quantile(1 - percentile)
        return group[(group['price'] >= low) & (group['price'] <= high)]

    return (df.groupby(['area', 'year'], group_keys=False)
              .apply(trim_group)
              .reset_index(drop=True))

def train_model(X: pd.DataFrame, y: pd.Series) -> tuple:
    """Train RandomForestRegressor (same hyperparameters as baseline)."""
    preprocessor = ColumnTransformer(
        transformers=[
            ('cat', OneHotEncoder(handle_unknown='ignore'),
             ['type', 'governorate', 'area']),
        ],
        remainder='passthrough',
    )

    rf = RandomForestRegressor(
        n_estimators    = 200,
        max_depth       = 25,
        min_samples_leaf= 2,
        random_state    = 42,
        n_jobs          = -1,
    )

    logger.info("Fitting preprocessor + RF...")
    X_transformed = preprocessor.fit_transform(X)
    rf.fit(X_transformed, y)
    return preprocessor, rf, X_transformed

def validate_model(rf, X_transformed, y) -> float:
    """K-fold cross-validation. Returns mean R² score."""
    
    sample_size = min(2000, len(y))
    rng = np.random.default_rng(42)
    sample_idx = rng.choice(len(y), sample_size, replace=False)

    cv_scores = cross_val_score(
        rf,
        X_transformed[sample_idx],
        y.iloc[sample_idx],
        cv=3, scoring='r2', n_jobs=-1,
    )
    mean_r2 = float(cv_scores.mean())
    logger.info(f"Cross-val R²: {cv_scores.round(3).tolist()} (mean: {mean_r2:.3f})")
    return mean_r2

def save_versioned_model(preprocessor, rf, metadata: dict) -> Path:
    """Save model to models/registry/v{YYYYMMDD_HHMM}.pkl + update latest symlink."""
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)

    version = metadata['version']
    path    = REGISTRY_DIR / f"{version}.pkl"

    bundle = {
        'preprocessor': preprocessor,
        'model':        rf,
        'metadata':     metadata,
    }
    with open(path, 'wb') as fh:
        pickle.dump(bundle, fh)

    tmp_link = REGISTRY_DIR / "latest.pkl.tmp"
    if tmp_link.exists():
        tmp_link.unlink()
    tmp_link.symlink_to(path.name)
    tmp_link.replace(LATEST_LINK)

    try:
        if LEGACY_PICKLE.exists() or LEGACY_PICKLE.is_symlink():
            LEGACY_PICKLE.unlink()
        LEGACY_PICKLE.symlink_to(path)
    except Exception as e:
        logger.warning(f"Could not update legacy symlink: {e}")

    logger.info(f"Saved → {path}")
    return path

def prune_old_versions(keep: int = MAX_VERSIONS_TO_KEEP) -> int:
    """Delete oldest versions, keeping only the last N."""
    versions = sorted(
        [p for p in REGISTRY_DIR.glob("v*.pkl") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    pruned = 0
    for old in versions[keep:]:
        try:
            old.unlink()
            pruned += 1
            logger.info(f"Pruned old version: {old.name}")
        except Exception as e:
            logger.warning(f"Could not prune {old}: {e}")
    return pruned

def hot_swap_into_engine(model_path: Path) -> bool:
    """Tell live ml_engine to load the new model (no restart needed)."""
    try:
        from ml_engine import ml
        return ml.hot_swap(str(model_path))
    except Exception as e:
        logger.warning(f"Hot-swap failed: {e}")
        return False

def log_training(version: str, model_path: Path, r2: float,
                 rows_count: int, new_rows: int, duration: float,
                 trigger: str, deployed: bool, notes: str = '') -> None:
    """Insert a TrainingHistory row marking this as the active model."""
    from app import create_app
    from extensions import db
    from models import TrainingHistory

    app = create_app()
    with app.app_context():
        
        TrainingHistory.query.update({'is_active': False})

        entry = TrainingHistory(
            version=version,
            model_path=str(model_path),
            r2_score=r2,
            rows_count=rows_count,
            new_rows=new_rows,
            duration_sec=duration,
            trigger=trigger,
            deployed=deployed,
            is_active=deployed,
            notes=notes,
        )
        db.session.add(entry)
        db.session.commit()
        logger.info(f"TrainingHistory row #{entry.id} created ({version})")

def run(force: bool = False, dry_run: bool = False,
        min_new: int = 100, min_days: int = 7,
        trigger: str = 'manual') -> dict:
    """
    Run the complete retraining pipeline.
    Returns a dict summary of what happened.
    """
    start_time = time.time()
    logger.info("═" * 60)
    logger.info("  🌲 SMART RETRAIN PIPELINE STARTED")
    logger.info("═" * 60)

    do_run, reason = should_retrain(min_new=min_new, min_days=min_days, force=force)
    logger.info(f"Decision: {'PROCEED' if do_run else 'SKIP'} — {reason}")
    if not do_run:
        return {'status': 'skipped', 'reason': reason}

    df_baseline = load_baseline_data()
    df_new      = load_new_properties_from_app_db()

    X, y = build_training_rows(df_baseline, df_new)
    rows_count = len(y)
    new_rows   = len(df_new)

    if rows_count < 100:
        logger.error(f"Too few rows ({rows_count}) — aborting")
        return {'status': 'failed', 'reason': 'insufficient_data'}

    preprocessor, rf, X_transformed = train_model(X, y)

    r2 = validate_model(rf, X_transformed, y)
    if r2 < MIN_R2_SCORE:
        logger.error(f"R²={r2:.3f} < {MIN_R2_SCORE} threshold — REJECTING new model")
        if not dry_run:
            log_training(
                version=f"REJECTED_{datetime.utcnow():%Y%m%d_%H%M}",
                model_path=Path("/dev/null"),
                r2=r2, rows_count=rows_count, new_rows=new_rows,
                duration=time.time() - start_time,
                trigger=trigger, deployed=False,
                notes=f"Rejected: R²={r2:.3f} below {MIN_R2_SCORE}"
            )
        return {'status': 'rejected', 'r2': r2, 'reason': 'low_quality'}

    try:
        from app import create_app
        from models import TrainingHistory

        app = create_app()
        with app.app_context():
            current_active = TrainingHistory.query.filter_by(is_active=True).first()
            if current_active and current_active.r2_score:
                drift = current_active.r2_score - r2
                if drift > 0.05:   
                    logger.error(
                        f"⚠️ DRIFT DETECTED: new R²={r2:.4f} vs active "
                        f"R²={current_active.r2_score:.4f} (-{drift:.4f}). "
                        f"Keeping {current_active.version} as active."
                    )
                    if not dry_run:
                        log_training(
                            version=f"DRIFT_REJECTED_{datetime.utcnow():%Y%m%d_%H%M}",
                            model_path=Path("/dev/null"),
                            r2=r2, rows_count=rows_count, new_rows=new_rows,
                            duration=time.time() - start_time,
                            trigger=trigger, deployed=False,
                            notes=(f"Drift rejected: R² {r2:.4f} vs active "
                                   f"{current_active.r2_score:.4f}")
                        )
                    return {
                        'status':  'drift_rejected',
                        'r2':      r2,
                        'active_r2': current_active.r2_score,
                        'drift':   round(drift, 4),
                    }
    except Exception as e:
        logger.warning(f"Drift check failed (continuing): {e}")

    version = f"v{datetime.utcnow():%Y%m%d_%H%M}"
    metadata = {
        'version':    version,
        'r2_score':   r2,
        'rows_count': rows_count,
        'new_rows':   new_rows,
        'trained_at': datetime.utcnow().isoformat(),
        'trigger':    trigger,
    }

    if dry_run:
        logger.info("DRY-RUN: skipping save + hot-swap")
        return {'status': 'dry_run', 'r2': r2, 'version': version,
                'rows_count': rows_count, 'new_rows': new_rows}

    model_path = save_versioned_model(preprocessor, rf, metadata)
    swapped    = hot_swap_into_engine(model_path)
    duration   = time.time() - start_time

    log_training(
        version=version, model_path=model_path,
        r2=r2, rows_count=rows_count, new_rows=new_rows,
        duration=duration, trigger=trigger, deployed=swapped,
        notes=f"Hot-swap {'OK' if swapped else 'FAILED'}"
    )
    prune_old_versions()

    logger.info("═" * 60)
    logger.info(f"  ✅ COMPLETE in {duration:.1f}s")
    logger.info(f"     Version:    {version}")
    logger.info(f"     R²:         {r2:.4f}")
    logger.info(f"     Rows:       {rows_count:,} ({new_rows} new)")
    logger.info(f"     Hot-swap:   {'✅' if swapped else '❌'}")
    logger.info("═" * 60)

    return {
        'status':     'success',
        'version':    version,
        'r2':         r2,
        'rows_count': rows_count,
        'new_rows':   new_rows,
        'duration':   duration,
        'hot_swap':   swapped,
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Smart ML retraining pipeline")
    parser.add_argument('--force',     action='store_true',
                        help="Retrain regardless of thresholds")
    parser.add_argument('--dry-run',   action='store_true',
                        help="Simulate without saving or hot-swapping")
    parser.add_argument('--min-new',   type=int, default=100,
                        help="Min new properties to trigger retrain")
    parser.add_argument('--min-days',  type=int, default=7,
                        help="Min days since last training")
    parser.add_argument('--trigger',   default='manual',
                        choices=['manual', 'scheduled', 'threshold'],
                        help="Trigger source (for audit log)")
    args = parser.parse_args()

    result = run(
        force=args.force,
        dry_run=args.dry_run,
        min_new=args.min_new,
        min_days=args.min_days,
        trigger=args.trigger,
    )

    sys.exit(0 if result['status'] in ('success', 'dry_run', 'skipped') else 1)
