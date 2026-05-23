"""
ml_engine.py — Smart Estate Oman, ML Inference Layer v2
========================================================
طبقة الاستدلال الذكيَّة الجديدة — RF-driven بدلاً من CAGR ثابت

التَحسينات على ml_model.py القديم:
  ✅ Singleton pattern — instance واحد فقط (memory-safe)
  ✅ Hot-swap atomically — استبدال النموذج بدون إعادة تشغيل
  ✅ TTL cache — تَجَنُّب إعادة حساب نفس الـ prediction
  ✅ Thread-safe — يَستخدم RLock للقراءة/الكتابة المتزامنة
  ✅ Confidence intervals — من تَباين الـ 200 شجرة
  ✅ Per-property growth — استخدام RF مباشرة بدلاً من معادلة CAGR
  ✅ Cold-start fallback — يَتعامل مع المناطق الجديدة بذكاء
  ✅ Metadata tracking — version, R², trained_at لكل نموذج
"""

from __future__ import annotations

import os
import pickle
import logging
import threading
import hashlib
import json
import time
from datetime import datetime
from typing import Optional, Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# =============================================================================
# 🧠 TTL CACHE — simple in-memory cache with expiry
# =============================================================================

class TTLCache:
    """
    Thread-safe in-memory cache with per-entry TTL.
    تَخزين مؤقَّت آمن للـ threads مع انتهاء صلاحيَّة لكل مدخل.
    """
    def __init__(self, maxsize: int = 10_000, ttl_seconds: int = 3600):
        self.maxsize     = maxsize
        self.ttl_seconds = ttl_seconds
        self._store: dict = {}
        self._lock        = threading.RLock()
        self.hits         = 0
        self.misses       = 0

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self.misses += 1
                return None
            value, expires_at = entry
            if time.time() > expires_at:
                del self._store[key]
                self.misses += 1
                return None
            self.hits += 1
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            # Simple LRU eviction: drop random one if at capacity
            if len(self._store) >= self.maxsize:
                self._store.pop(next(iter(self._store)), None)
            self._store[key] = (value, time.time() + self.ttl_seconds)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return round(self.hits / total * 100, 1) if total > 0 else 0.0

    def __len__(self) -> int:
        return len(self._store)


# =============================================================================
# 🌲 ML ENGINE — Singleton inference engine
# =============================================================================

class MLEngine:
    """
    Production-grade RandomForest inference engine.

    Usage:
        from ml_engine import ml

        # Price prediction with confidence
        result = ml.predict_price({
            'type': 'Villa', 'governorate': 'Muscat', 'area': 'Al Mouj',
            'sqm': 350, 'bedrooms': 4, 'bathrooms': 3, 'floor': 0, 'year': 2026
        })
        # → {'price': 245000, 'confidence': 92, 'range': [228k, 262k]}

        # Property-specific growth from RF (NOT CAGR formula)
        growth = ml.predict_growth({...same features...}, years=5)
        # → {'current': 245k, 'future': 388k, 'growth_pct': 58.4, 'confidence': 87}
    """

    # Default model location (can be overridden via env)
    DEFAULT_MODEL_PATH = os.path.join(
        os.path.dirname(__file__), "ml_model_trained.pkl"
    )

    # Required feature order — must match training
    FEATURE_NAMES = [
        'type', 'governorate', 'area',
        'sqm', 'bedrooms', 'bathrooms', 'floor', 'year',
    ]

    BASE_YEAR = 2026   # used as reference for "current year"

    def __init__(self):
        self.model        = None
        self.preprocessor = None
        self.metadata: dict = {
            'version':     'baseline',
            'loaded_at':   None,
            'r2_score':    None,
            'rows_count':  None,
        }
        self.cache = TTLCache(maxsize=10_000, ttl_seconds=3600)
        self._lock = threading.RLock()
        self._known_areas: set = set()
        self._known_types: set = set()
        self._loaded = False

    # ─────────────────────────────────────────────────────────────────
    # MODEL LIFECYCLE — load, hot-swap, status
    # ─────────────────────────────────────────────────────────────────

    def load(self, path: Optional[str] = None) -> bool:
        """
        Load model from pickle into the engine.
        Returns True on success, False otherwise (engine stays empty).
        """
        path = path or self.DEFAULT_MODEL_PATH
        if not os.path.exists(path):
            logger.warning(f"[MLEngine] Model file not found: {path}")
            return False

        try:
            with open(path, 'rb') as fh:
                bundle = pickle.load(fh)

            with self._lock:
                self.preprocessor = bundle['preprocessor']
                self.model        = bundle['model']
                self.metadata = bundle.get('metadata', {
                    'version':    self._derive_version(path),
                    'loaded_at':  datetime.utcnow().isoformat(),
                    'r2_score':   None,
                    'rows_count': None,
                })
                self.metadata.setdefault('loaded_at', datetime.utcnow().isoformat())
                self._extract_known_categories()
                self.cache.clear()   # invalidate stale predictions
                self._loaded = True

            logger.info(
                f"[MLEngine] Loaded {self.metadata.get('version')} "
                f"({len(self.model.estimators_)} trees) from {path}"
            )
            return True
        except Exception as e:
            logger.error(f"[MLEngine] Load failed: {e}")
            self._loaded = False
            return False

    def hot_swap(self, new_path: str) -> bool:
        """
        Atomically replace the live model with a new one.
        After successful load, all subsequent predictions use the new model.
        """
        return self.load(new_path)

    def status(self) -> dict:
        """Return current engine status (for /api/ml/status)."""
        with self._lock:
            stats = MLEngine._stats
            total_preds = stats['predictions_total']
            avg_latency = (stats['total_latency_ms'] / total_preds) if total_preds else 0

            return {
                'loaded':            self._loaded,
                'version':           self.metadata.get('version'),
                'r2_score':          self.metadata.get('r2_score'),
                'rows_count':        self.metadata.get('rows_count'),
                'loaded_at':         self.metadata.get('loaded_at'),
                'trees':             len(self.model.estimators_) if self.model else 0,
                'known_areas':       len(self._known_areas),
                'known_types':       len(self._known_types),
                'cache_size':        len(self.cache),
                'cache_hit_rate':    self.cache.hit_rate,
                # 🆕 Telemetry
                'predictions_total': total_preds,
                'cache_hits_total':  stats['cache_hits'],
                'errors_total':      stats['errors'],
                'avg_latency_ms':    round(avg_latency, 2),
            }

    # ─────────────────────────────────────────────────────────────────
    # CORE PREDICTIONS — price, growth, confidence
    # ─────────────────────────────────────────────────────────────────

    # Telemetry counters
    _stats = {'predictions_total': 0, 'cache_hits': 0, 'errors': 0,
              'total_latency_ms': 0.0}

    def predict_price(self, features: dict) -> dict:
        """
        Predict price for a single property with confidence interval.

        Returns:
            {
                'price':      float,         # mean prediction across 200 trees
                'confidence': float (0-100), # 100 = high agreement among trees
                'range':      [low, high],   # ±1 standard deviation
                'std':        float,         # raw std for advanced uses
            }
        """
        _t_start = time.time()
        MLEngine._stats['predictions_total'] += 1

        if not self._loaded:
            MLEngine._stats['errors'] += 1
            return {'price': 0.0, 'confidence': 0, 'range': [0, 0], 'std': 0,
                    'error': 'model_not_loaded'}

        # Normalize + cache lookup
        feats = self._normalize_features(features)
        cache_key = self._hash_features(feats)
        cached = self.cache.get(cache_key)
        if cached is not None:
            MLEngine._stats['cache_hits'] += 1
            elapsed_ms = (time.time() - _t_start) * 1000
            MLEngine._stats['total_latency_ms'] += elapsed_ms
            logger.debug(
                f"[ML] predict_price CACHE_HIT area={feats['area']} "
                f"type={feats['type']} took={elapsed_ms:.1f}ms"
            )
            return cached

        try:
            X = self._build_feature_row(feats)
            X_transformed = self.preprocessor.transform(X)

            # Per-tree predictions (200 of them)
            tree_preds = np.array([
                tree.predict(X_transformed)[0]
                for tree in self.model.estimators_
            ])
            mean_pred = float(tree_preds.mean())
            std_pred  = float(tree_preds.std())

            # Confidence: inverse of coefficient of variation
            # std/mean = 0     → confidence 100
            # std/mean = 0.5   → confidence 0
            if mean_pred > 0:
                cv = std_pred / mean_pred
                confidence = max(0.0, min(100.0, 100.0 - cv * 200.0))
            else:
                confidence = 0.0

            result = {
                'price':      round(mean_pred, 2),
                'confidence': round(confidence, 1),
                'range':      [round(mean_pred - std_pred, 2),
                               round(mean_pred + std_pred, 2)],
                'std':        round(std_pred, 2),
            }
            self.cache.set(cache_key, result)

            elapsed_ms = (time.time() - _t_start) * 1000
            MLEngine._stats['total_latency_ms'] += elapsed_ms
            logger.info(
                f"[ML] predict_price area={feats['area']} type={feats['type']} "
                f"sqm={feats['sqm']:.0f} → {mean_pred:,.0f} OMR "
                f"conf={confidence:.0f}% took={elapsed_ms:.1f}ms"
            )
            return result

        except Exception as e:
            MLEngine._stats['errors'] += 1
            logger.warning(f"[MLEngine] predict_price failed: {e}")
            return {'price': 0.0, 'confidence': 0, 'range': [0, 0], 'std': 0,
                    'error': str(e)}

    # Year range the model was trained on (used for CAGR extraction)
    TRAINING_YEAR_MIN = 2019
    TRAINING_YEAR_MAX = 2026

    def predict_growth(self, features: dict, years: int = 5) -> dict:
        """
        Predict growth using RF-derived PER-PROPERTY CAGR.

        Why this approach:
          • RF was trained on 2019-2026 — it can't extrapolate past 2026
          • But RF CAN tell us the historical growth FOR THIS SPECIFIC PROPERTY
          • So we extract per-property CAGR from RF, then compound forward

        Strategy:
          1. Get RF-predicted price at 2019 (start of training)
          2. Get RF-predicted price at 2026 (end of training)
          3. Compute CAGR from those two RF predictions
          4. Extrapolate forward using compound interest

        This gives PER-PROPERTY growth (not area average) because RF
        accounts for sqm, bedrooms, type interactions. A 500m² villa
        gets different growth than an 80m² apartment in the SAME area.

        Returns:
            {
                'current':      current price (from RF),
                'future':       projected price (RF + compound),
                'growth_pct':   total growth over N years,
                'annual_pct':   compounded annual rate (from this property),
                'multiplier':   future / current,
                'confidence':   ML confidence,
                'method':       'ml_per_property_cagr',
                'years':        N,
            }
        """
        if not self._loaded:
            return self._cagr_fallback(features, years)

        try:
            # Step 1 — current price (RF at base year)
            now_features = {**features, 'year': self.TRAINING_YEAR_MAX}
            now_result   = self.predict_price(now_features)
            current_price = now_result['price']

            if current_price <= 0:
                return self._cagr_fallback(features, years)

            # Step 2 — historical price at start of training (RF at year 2019)
            start_features = {**features, 'year': self.TRAINING_YEAR_MIN}
            start_result   = self.predict_price(start_features)
            start_price    = start_result['price']

            # Step 3 — derive PER-PROPERTY annual growth rate from RF history
            # CAGR = (P_end / P_start)^(1/n) - 1
            training_years = self.TRAINING_YEAR_MAX - self.TRAINING_YEAR_MIN  # 7
            if start_price > 0 and training_years > 0:
                annual_rate = (current_price / start_price) ** (1.0 / training_years) - 1.0
            else:
                annual_rate = 0.055   # fallback

            # 🆕 If RF predicts identical prices (rate ≈ 0), the feature combo
            # is too rare in training data. Fall back to area-level CAGR from DB.
            method = 'ml_per_property_cagr'
            if abs(annual_rate) < 0.005:   # < 0.5%/yr → likely a model artifact
                try:
                    from models import Area
                    location = features.get('area') or features.get('location', '')
                    area = Area.query.filter(Area.name.ilike(f"%{location}%")).first()
                    if area and area.price_growth is not None:
                        annual_rate = max(min(
                            0.01 + (area.price_growth / 100.0) * 0.14,
                            0.15
                        ), 0.02)
                        method = 'ml_with_area_cagr_fallback'
                        logger.info(
                            f"[ML] RF returned ~0% growth for rare feature combo "
                            f"({features.get('area')}, {features.get('type')}) — "
                            f"fell back to area CAGR {annual_rate*100:.2f}%/yr"
                        )
                    else:
                        annual_rate = 0.05   # generic 5% baseline
                        method = 'baseline_5pct'
                except Exception:
                    annual_rate = 0.05
                    method = 'baseline_5pct'

            # Sanity clamp: keep annual rate in plausible [0.5%, 20%] range
            annual_rate = max(0.005, min(0.20, annual_rate))

            # Step 4 — extrapolate forward using compound interest
            multiplier   = (1 + annual_rate) ** years
            future_price = current_price * multiplier
            growth_pct   = (multiplier - 1.0) * 100

            return {
                'current':     round(current_price, 2),
                'future':      round(future_price, 2),
                'historical_2019': round(start_price, 2),
                'growth_pct':  round(growth_pct, 2),
                'annual_pct':  round(annual_rate * 100, 2),
                'multiplier':  round(multiplier, 6),
                'confidence':  round(min(now_result['confidence'],
                                        start_result['confidence']), 1),
                'method':      method,
                'years':       years,
            }

        except Exception as e:
            logger.warning(f"[MLEngine] predict_growth failed: {e}, falling back to CAGR")
            return self._cagr_fallback(features, years)

    def detect_anomaly(self, features: dict, listed_price: float) -> dict:
        """
        Compare listed price to RF prediction. Flag suspicious listings.

        Severity bands (by absolute deviation):
          • > 70% deviation → 'high'    (likely error or fraud)
          • > 40% deviation → 'medium'  (worth reviewing)
          • > 20% deviation → 'low'     (informational)
          • else           → not flagged

        Returns:
            {
                'is_anomaly':     bool,
                'severity':       'low' | 'medium' | 'high' | None,
                'reason':         human-readable explanation,
                'deviation_pct':  signed % difference (-100 to +inf),
                'predicted':      RF estimate,
                'listed':         user-provided price,
                'confidence':     ML confidence (lower = less trust the flag),
            }
        """
        if not self._loaded or listed_price <= 0:
            return {'is_anomaly': False, 'severity': None, 'reason': '',
                    'deviation_pct': 0, 'predicted': 0,
                    'listed': listed_price, 'confidence': 0}

        pred = self.predict_price(features)
        predicted = pred['price']
        confidence = pred['confidence']

        if predicted <= 0:
            return {'is_anomaly': False, 'severity': None, 'reason': '',
                    'deviation_pct': 0, 'predicted': 0,
                    'listed': listed_price, 'confidence': confidence}

        # Signed deviation: positive means listed > predicted (overpriced)
        deviation = (listed_price - predicted) / predicted
        abs_dev   = abs(deviation)

        # Only flag if confidence is reasonable (>= 50%)
        # otherwise we don't trust our own prediction enough
        if confidence < 50:
            return {'is_anomaly': False, 'severity': None,
                    'reason': f'Low ML confidence ({confidence}%) — anomaly check skipped',
                    'deviation_pct': round(deviation * 100, 1),
                    'predicted': predicted, 'listed': listed_price,
                    'confidence': confidence}

        severity = None
        reason = ''
        if abs_dev > 0.70:
            severity = 'high'
            direction = 'higher' if deviation > 0 else 'lower'
            reason = (f'Listed price is {abs(deviation)*100:.0f}% {direction} '
                     f'than ML estimate ({predicted:,.0f} OMR). '
                     f'Verify before publishing.')
        elif abs_dev > 0.40:
            severity = 'medium'
            direction = 'above' if deviation > 0 else 'below'
            reason = (f'Listed price {abs(deviation)*100:.0f}% {direction} '
                     f'ML estimate. Worth reviewing.')
        elif abs_dev > 0.20:
            severity = 'low'
            direction = 'above' if deviation > 0 else 'below'
            reason = (f'Listed price {abs(deviation)*100:.0f}% {direction} '
                     f'ML estimate ({predicted:,.0f} OMR).')

        return {
            'is_anomaly':    severity is not None,
            'severity':      severity,
            'reason':        reason,
            'deviation_pct': round(deviation * 100, 1),
            'predicted':     round(predicted, 0),
            'listed':        listed_price,
            'confidence':    confidence,
        }

    def predict_area_growth(self, location: str, years: int = 5) -> dict:
        """
        Predict average growth for an area (when no specific property given).

        Uses RF with archetype features (median property in that area),
        not the linear CAGR formula.
        """
        archetype = {
            'type':        'Apartment',
            'governorate': self._guess_governorate(location),
            'area':        location,
            'sqm':         120,
            'bedrooms':    2,
            'bathrooms':   2,
            'floor':       2,
            'year':        self.BASE_YEAR,
        }
        return self.predict_growth(archetype, years)

    # ─────────────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────────────

    def _normalize_features(self, features: dict) -> dict:
        """
        Fill missing keys with sensible defaults, normalize types.

        🆕 Cold-start handling: if the area is unknown to the model,
        we use the governorate-level archetype as a proxy. The caller
        can detect this via .is_cold_start_area() to lower confidence.
        """
        area_in = str(features.get('area') or features.get('location') or 'Muscat')
        gov_in  = features.get('governorate') or self._guess_governorate(area_in)

        # Cold-start: if area not known to the model, substitute with governorate
        # (governorate is also in known_areas because it's commonly used as area)
        if self._known_areas and area_in not in self._known_areas:
            # Try common variants first
            variants = [area_in.title(), area_in.lower().title(),
                       f"{area_in}, {gov_in}", f"{area_in.title()}, {gov_in}"]
            matched = next((v for v in variants if v in self._known_areas), None)
            if matched:
                area_in = matched
            elif gov_in in self._known_areas:
                area_in = gov_in   # fall back to governorate name as area

        out = {
            'type':        str(features.get('type') or 'Apartment'),
            'governorate': str(gov_in),
            'area':        area_in,
            'sqm':         float(features.get('sqm') or features.get('size') or 100),
            'bedrooms':    float(features.get('bedrooms') or 2),
            'bathrooms':   float(features.get('bathrooms') or 2),
            'floor':       float(features.get('floor') or 0),
            'year':        int(features.get('year') or self.BASE_YEAR),
        }
        return out

    def is_cold_start_area(self, area: str) -> bool:
        """Return True if RF has never seen this area."""
        if not self._known_areas:
            return False
        return area not in self._known_areas

    def confidence_band(self, confidence: float) -> str:
        """Map confidence % to UI band: high / medium / low."""
        if confidence >= 80:  return 'high'
        if confidence >= 50:  return 'medium'
        return 'low'

    def _build_feature_row(self, feats: dict) -> pd.DataFrame:
        """Construct a single-row DataFrame in correct column order."""
        return pd.DataFrame([{name: feats[name] for name in self.FEATURE_NAMES}])

    def _hash_features(self, feats: dict) -> str:
        """Stable hash of features dict for caching."""
        return hashlib.md5(
            json.dumps(feats, sort_keys=True, default=str).encode()
        ).hexdigest()

    def _extract_known_categories(self) -> None:
        """Pull known type/area values from the trained OHE preprocessor."""
        try:
            for name, trans, cols in self.preprocessor.transformers_:
                if name == 'cat':
                    cats = trans.categories_
                    if len(cats) >= 3:
                        self._known_types = set(cats[0])
                        self._known_areas = set(cats[2])
        except Exception as e:
            logger.warning(f"[MLEngine] Could not extract categories: {e}")

    def _guess_governorate(self, area_name: str) -> str:
        """Infer governorate from area name keywords."""
        a = (area_name or '').lower()
        if   'muscat'  in a or 'مسقط'  in a: return 'Muscat'
        elif 'salalah' in a or 'صلالة' in a: return 'Dhofar'
        elif 'sohar'   in a or 'صحار'  in a: return 'Al Batinah'
        elif 'barka'   in a or 'بركاء' in a: return 'Al Batinah'
        elif 'buraimi' in a or 'بريمي' in a: return 'Al Buraimi'
        elif 'nizwa'   in a or 'نزوى'  in a: return 'Ad Dakhiliyah'
        elif 'sur'     in a or 'صور'   in a: return 'Ash Sharqiyah'
        elif 'duqm'    in a or 'دقم'   in a: return 'Al Wusta'
        return 'Muscat'   # safe default

    def _derive_version(self, path: str) -> str:
        """Derive version string from file metadata."""
        try:
            mtime = os.path.getmtime(path)
            return f"v{datetime.fromtimestamp(mtime):%Y%m%d_%H%M}"
        except Exception:
            return 'unknown'

    def _cagr_fallback(self, features: dict, years: int) -> dict:
        """
        Fallback to Area.price_growth-based CAGR if RF unavailable.
        يَستخدم نفس الصيغة القديمة فقط عند فشل ML — للحفاظ على الـ uptime.
        """
        try:
            from models import Area
            location = features.get('area') or features.get('location', '')
            area = Area.query.filter(Area.name.ilike(f"%{location}%")).first()
            if area and area.price_growth is not None:
                annual_rate = max(min(0.01 + (area.price_growth / 100.0) * 0.14, 0.15), 0.01)
            else:
                annual_rate = 0.055
        except Exception:
            annual_rate = 0.055

        multiplier = (1 + annual_rate) ** years
        return {
            'current':     0,
            'future':      0,
            'growth_pct':  round((multiplier - 1) * 100, 2),
            'annual_pct':  round(annual_rate * 100, 2),
            'multiplier':  round(multiplier, 6),
            'confidence':  40,   # lower confidence — not ML
            'method':      'cagr_fallback',
            'years':       years,
        }


# =============================================================================
# 🌟 GLOBAL SINGLETON
# =============================================================================

# Single shared instance used across the entire Flask app
ml = MLEngine()


def init_ml_engine(model_path: Optional[str] = None) -> bool:
    """
    Convenience function — called from app.py at startup.
    Loads the model from disk into the singleton.
    """
    return ml.load(model_path)

# =============================================================================
# 🚀 LEGACY ML UTILS (Migrated from ml_model.py)
# =============================================================================

def get_ml_investment_score(predicted_price, actual_price):
    if not actual_price or actual_price <= 0:
        return 50
    if not predicted_price:
        predicted_price = 0
    ratio = predicted_price / actual_price
    score = 60 + ((ratio - 1.0) * 50)
    return min(max(round(score), 0), 100)

def ensure_trained() -> bool:
    '''Auto-train stub migrated from v1. v2 Engine is auto-loaded at startup.'''
    return ml._loaded

def get_future_multiplier(location: str, years: int,
                          property_type: str = "Apartment",
                          sqm: float = 100,
                          bedrooms: int = 2,
                          bathrooms: int = 2) -> float:
    try:
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
            return round(multiplier, 6)
    except Exception as e:
        pass

    # Legacy CAGR fallback
    from models import Area
    annual_rate = 0.055
    if location and location.strip():
        area = Area.query.filter(Area.name.ilike(f"%{location}%")).first()
        if area and area.price_growth is not None:
            annual_rate = max(min(0.01 + (area.price_growth / 100.0) * 0.14, 0.15), 0.01)
    return round((1 + annual_rate) ** years, 6)
