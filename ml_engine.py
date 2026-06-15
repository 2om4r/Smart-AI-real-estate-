
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

class TTLCache:
    
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

class MLEngine:
    
    DEFAULT_MODEL_PATH = os.path.join(
        os.path.dirname(__file__), "models", "registry", "ml_model_trained.pkl"
    )

    FEATURE_NAMES = [
        'type', 'governorate', 'area',
        'sqm', 'bedrooms', 'bathrooms', 'floor', 'year',
    ]

    BASE_YEAR = 2026   

    def __init__(self):
        self.model        = None
        self.roi_model    = None
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

    def load(self, path: Optional[str] = None) -> bool:
        
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
                self.cache.clear()   
                self._loaded = True

            logger.info(
                f"[MLEngine] Loaded {self.metadata.get('version')} "
                f"({len(self.model.estimators_)} trees) from {path}"
            )
            
            roi_path = os.path.join(os.path.dirname(__file__), "models", "registry", "roi_predictor.pkl")
            if os.path.exists(roi_path):
                with open(roi_path, 'rb') as f:
                    self.roi_model = pickle.load(f)
                logger.info(f"[MLEngine] Loaded ROI model from {roi_path}")
            else:
                logger.warning(f"[MLEngine] ROI model not found at {roi_path}")

            return True
        except Exception as e:
            logger.error(f"[MLEngine] Load failed: {e}")
            self._loaded = False
            return False

    def hot_swap(self, new_path: str) -> bool:
        
        return self.load(new_path)

    def status(self) -> dict:
        
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
                
                'predictions_total': total_preds,
                'cache_hits_total':  stats['cache_hits'],
                'errors_total':      stats['errors'],
                'avg_latency_ms':    round(avg_latency, 2),
            }

    _stats = {'predictions_total': 0, 'cache_hits': 0, 'errors': 0,
              'total_latency_ms': 0.0}

    def predict_price(self, features: dict) -> dict:
        
        _t_start = time.time()
        MLEngine._stats['predictions_total'] += 1

        if not self._loaded:
            MLEngine._stats['errors'] += 1
            return {'price': 0.0, 'confidence': 0, 'range': [0, 0], 'std': 0,
                    'error': 'model_not_loaded'}

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

            tree_preds = np.array([
                tree.predict(X_transformed)[0]
                for tree in self.model.estimators_
            ])
            mean_pred = float(tree_preds.mean())
            std_pred  = float(tree_preds.std())

            if mean_pred > 0:
                cv = std_pred / mean_pred
                # Balanced tuning: a 30% std dev gives ~70% confidence, 50% gives 50%
                confidence = max(20.0, min(99.0, 100.0 - (cv * 100.0)))
                
                # --- Anomaly Detection Penalty ---
                # Random Forests cannot extrapolate beyond training max values (all terminal leaves).
                # If inputs are absurdly out of bounds, variance drops to 0 artificially. We must penalize this.
                if feats.get('sqm', 0) > 10000 or feats.get('sqm', 0) < 20 or feats.get('bedrooms', 0) > 15 or feats.get('bathrooms', 0) > 15:
                    confidence = min(confidence, 15.0)
            else:
                confidence = 0.0

            result = {
                'price':      round(mean_pred, 0),
                'confidence': round(confidence, 1),
                'range':      [round(mean_pred - std_pred, 0),
                               round(mean_pred + std_pred, 0)],
                'std':        round(std_pred, 0),
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

    TRAINING_YEAR_MIN = 2019
    TRAINING_YEAR_MAX = 2026

    def predict_roi(self, features: dict) -> float:
        
        if not self.roi_model:
            return 0.0

        try:
            import pandas as pd
            
            df_input = pd.DataFrame([{
                'property_type': str(features.get('type', 'Apartment')).capitalize(),
                'location': str(features.get('location', 'Muscat')),
                'status': str(features.get('status', 'Ready')).capitalize(),
                'price_omr': float(features.get('price_omr', 100000)),
                'area_sqm': float(features.get('area_sqm', 150)),
                'age_years': float(features.get('age_years', 5)),
                'services_score': float(features.get('services_score', 50))
            }])
            
            roi_pred = self.roi_model.predict(df_input)[0]
            return round(float(roi_pred), 1)
        except Exception as e:
            logger.error(f"[MLEngine] ROI Prediction failed: {e}")
            return 0.0

    def predict_growth(self, features: dict, years: int = 5) -> dict:
        
        if not self._loaded:
            return self._cagr_fallback(features, years)

        try:
            
            now_features = {**features, 'year': self.TRAINING_YEAR_MAX}
            now_result   = self.predict_price(now_features)
            current_price = now_result['price']

            if current_price <= 0:
                return self._cagr_fallback(features, years)

            start_features = {**features, 'year': self.TRAINING_YEAR_MIN}
            start_result   = self.predict_price(start_features)
            start_price    = start_result['price']

            training_years = self.TRAINING_YEAR_MAX - self.TRAINING_YEAR_MIN  
            if start_price > 0 and training_years > 0:
                annual_rate = (current_price / start_price) ** (1.0 / training_years) - 1.0
            else:
                annual_rate = 0.055   

            method = 'ml_per_property_cagr'
            if abs(annual_rate) < 0.005 or now_result['confidence'] < 20:   
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
                        annual_rate = 0.05   
                        method = 'baseline_5pct'
                except Exception:
                    annual_rate = 0.05
                    method = 'baseline_5pct'

            annual_rate = max(0.005, min(0.20, annual_rate))

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

        deviation = (listed_price - predicted) / predicted
        abs_dev   = abs(deviation)

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

    def _normalize_features(self, features: dict) -> dict:
        
        area_in = str(features.get('area') or features.get('location') or 'Muscat')
        gov_in  = features.get('governorate') or self._guess_governorate(area_in)

        if self._known_areas and area_in not in self._known_areas:
            
            variants = [area_in.title(), area_in.lower().title(),
                       f"{area_in}, {gov_in}", f"{area_in.title()}, {gov_in}"]
            matched = next((v for v in variants if v in self._known_areas), None)
            if matched:
                area_in = matched
            elif gov_in in self._known_areas:
                area_in = gov_in   

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
        
        if not self._known_areas:
            return False
        return area not in self._known_areas

    def confidence_band(self, confidence: float) -> str:
        
        if confidence >= 80:  return 'high'
        if confidence >= 50:  return 'medium'
        return 'low'

    def _build_feature_row(self, feats: dict) -> pd.DataFrame:
        
        return pd.DataFrame([{name: feats[name] for name in self.FEATURE_NAMES}])

    def _hash_features(self, feats: dict) -> str:
        
        return hashlib.md5(
            json.dumps(feats, sort_keys=True, default=str).encode()
        ).hexdigest()

    def _extract_known_categories(self) -> None:
        
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
        
        a = (area_name or '').lower()
        if any(k in a for k in ['muscat', 'مسقط', 'seeb', 'السيب', 'bousher', 'بوشر', 'amerat', 'العامرات', 'quriyat', 'قريات']):
            return 'Muscat'
        elif any(k in a for k in ['dhofar', 'ظفار', 'salalah', 'صلالة', 'taqah', 'طاقة', 'thumrait', 'ثمريت', 'mirbat', 'مرباط']):
            return 'Dhofar'
        elif any(k in a for k in ['north batinah', 'الباطنة شمال', 'sohar', 'صحار', 'shinas', 'شناص', 'liwa', 'لوى', 'saham', 'صحم', 'khaburah', 'الخابورة', 'suwaiq', 'السويق']):
            return 'North Al Batinah'
        elif any(k in a for k in ['south batinah', 'الباطنة جنوب', 'rustaq', 'الرستاق', 'awabi', 'العوابي', 'nakhal', 'نخل', 'barka', 'بركاء', 'mussanah', 'المصنعة']):
            return 'South Al Batinah'
        elif any(k in a for k in ['buraimi', 'البريمي', 'mahah', 'محضة', 'sunaynah', 'السنينة']):
            return 'Al Buraimi'
        elif any(k in a for k in ['dakhiliyah', 'الداخلية', 'nizwa', 'نزوى', 'bahla', 'بهلاء', 'manah', 'منح', 'hamra', 'الحمراء', 'adam', 'أدم', 'izki', 'إزكي', 'samail', 'سمائل']):
            return 'Ad Dakhiliyah'
        elif any(k in a for k in ['north sharqiyah', 'الشرقية شمال', 'ibra', 'إبراء', 'mudhaibi', 'المضيبي', 'bidiya', 'بدية', 'qabil', 'القابل']):
            return 'North Ash Sharqiyah'
        elif any(k in a for k in ['south sharqiyah', 'الشرقية جنوب', 'sur', 'صور', 'kamil', 'الكامل', 'jalan', 'جعلان', 'masirah', 'مصيرة']):
            return 'South Ash Sharqiyah'
        elif any(k in a for k in ['wusta', 'الوسطى', 'haima', 'هيماء', 'duqm', 'الدقم', 'دقم', 'mahout', 'محوت']):
            return 'Al Wusta'
        elif any(k in a for k in ['dhahirah', 'الظاهرة', 'ibri', 'عبري', 'yanqul', 'ينقل', 'dhank', 'ضنك']):
            return 'Ad Dhahirah'
        elif any(k in a for k in ['musandam', 'مسندم', 'khasab', 'خصب', 'dibba', 'دبا', 'bukha', 'بخا']):
            return 'Musandam'
            
        return 'Muscat'   

    def _derive_version(self, path: str) -> str:
        
        try:
            mtime = os.path.getmtime(path)
            return f"v{datetime.fromtimestamp(mtime):%Y%m%d_%H%M}"
        except Exception:
            return 'unknown'

    def _cagr_fallback(self, features: dict, years: int) -> dict:
        
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
            'confidence':  40,   
            'method':      'cagr_fallback',
            'years':       years,
        }

ml = MLEngine()

def init_ml_engine(model_path: Optional[str] = None) -> bool:
    
    return ml.load(model_path)

def get_ml_investment_score(predicted_price, actual_price):
    if not actual_price or actual_price <= 0:
        return 50
    if not predicted_price:
        predicted_price = 0
    ratio = predicted_price / actual_price
    score = 60 + ((ratio - 1.0) * 50)
    return min(max(round(score), 0), 100)

def ensure_trained() -> bool:
    
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

    from models import Area
    annual_rate = 0.055
    if location and location.strip():
        area = Area.query.filter(Area.name.ilike(f"%{location}%")).first()
        if area and area.price_growth is not None:
            annual_rate = max(min(0.01 + (area.price_growth / 100.0) * 0.14, 0.15), 0.01)
    return round((1 + annual_rate) ** years, 6)
