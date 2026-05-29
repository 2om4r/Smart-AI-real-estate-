import os
import joblib
import logging
import numpy as np
from pathlib import Path

logger = logging.getLogger(__name__)

class AreaMLEngine:
    def __init__(self):
        self.model = None
        self.metadata = None
        self.classes = []
        self._load_model()

    def _load_model(self):
        project_root = Path(__file__).parent
        model_path = project_root / "models" / "registry" / "area_model.pkl"
        meta_path = project_root / "models" / "registry" / "area_model_meta.pkl"

        if model_path.exists() and meta_path.exists():
            try:
                self.model = joblib.load(model_path)
                self.metadata = joblib.load(meta_path)
                self.classes = self.metadata.get('classes', [])
                logger.info("[Area ML] Random Forest Model loaded successfully.")
            except Exception as e:
                logger.error(f"[Area ML] Failed to load model: {e}")
        else:
            logger.warning("[Area ML] Model files not found. Run scripts/train_area_model.py first.")

    def predict_area(self, demand, price_growth, services, listing_count):
        """
        Takes area features and returns a dict with ML predictions:
        - recommendation: Strong Buy, Moderate, or Risky
        - color: red, orange, or green
        - score: 0 to 100 based on class probabilities
        """
        # Default fallback if model is missing
        if self.model is None:
            logger.warning("[Area ML] Model is missing, using fallback calculation.")
            s = (demand * 0.4) + (price_growth * 0.3) + (services * 0.2) + (listing_count * 0.1)
            rec = 'Strong Buy' if s > 80 else ('Moderate' if s >= 50 else 'Risky')
            col = 'red' if s > 80 else ('orange' if s >= 50 else 'green')
            return {'score': s, 'recommendation': rec, 'color': col}

        # Prepare input array (order must match training: Demand_Index, Price_Growth_Rate, Services_Score, Listing_Count)
        features = np.array([[demand, price_growth, services, listing_count]])

        # Get Prediction
        try:
            pred_class = self.model.predict(features)[0]
            probabilities = self.model.predict_proba(features)[0]
            
            # Map probabilities to a 0-100 score for the heatmap
            # To create a meaningful score from 0-100 out of probabilities:
            # If Strong Buy is highest, score is high (80-100)
            # If Moderate is highest, score is medium (50-79)
            # If Risky is highest, score is low (0-49)
            
            # Create a weighted score:
            # Let's say Risky = 0 weight, Moderate = 60 weight, Strong Buy = 100 weight
            # Then the final score is the dot product of probabilities and these weights.
            
            class_weights = {}
            for cls in self.classes:
                if cls == 'Strong Buy':
                    class_weights[cls] = 100
                elif cls == 'Moderate':
                    class_weights[cls] = 60
                elif cls == 'Risky':
                    class_weights[cls] = 20
                else:
                    class_weights[cls] = 50

            score = sum(prob * class_weights.get(cls, 50) for prob, cls in zip(probabilities, self.classes))
            
            # Determine color based on predicted class (for consistency with UI)
            if pred_class == 'Strong Buy':
                color = 'red'
            elif pred_class == 'Moderate':
                color = 'orange'
            else:
                color = 'green'

            return {
                'score': round(score, 2),
                'recommendation': pred_class,
                'color': color
            }
        except Exception as e:
            logger.error(f"[Area ML] Prediction error: {e}")
            return {'score': 0, 'recommendation': 'Error', 'color': 'gray'}

# Instantiate globally so it's loaded once per worker
area_ml_engine = AreaMLEngine()
