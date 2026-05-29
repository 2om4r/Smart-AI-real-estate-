import os
import pandas as pd
import sqlite3
import joblib
import logging
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    # 1. Define paths
    PROJECT_ROOT = Path(__file__).parent.parent
    DB_PATH = PROJECT_ROOT / "instance" / "database" / "area.db"
    MODEL_DIR = PROJECT_ROOT / "models" / "registry"
    MODEL_PATH = MODEL_DIR / "area_model.pkl"

    if not DB_PATH.exists():
        logger.error(f"Database not found at {DB_PATH}")
        return

    # 2. Load Data from SQLite
    logger.info(f"Connecting to database: {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    
    # The table name is in Arabic as per the user's DB
    table_name = "معدل نمو الاسثتمار في عمان"
    try:
        df = pd.read_sql(f'SELECT * FROM "{table_name}"', conn)
    except Exception as e:
        logger.error(f"Failed to read table: {e}")
        return
    finally:
        conn.close()

    logger.info(f"Loaded {len(df)} records from {table_name}.")

    # 3. Prepare Features (X) and Target (y)
    # The columns from the prompt are: Demand_Index, Price_Growth_Rate, Services_Score, Listing_Count
    features = ['Demand_Index', 'Price_Growth_Rate', 'Services_Score', 'Listing_Count']
    target = 'Investment_Label'

    # Ensure no missing values
    df = df.dropna(subset=features + [target])

    X = df[features]
    y = df[target]

    # 4. Split data for testing (80% training, 20% testing)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # 5. Initialize and Train the Random Forest Classifier
    logger.info("Training Random Forest Classifier for Area Scoring...")
    rf_model = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42, class_weight='balanced')
    rf_model.fit(X_train, y_train)

    # 6. Evaluate the model
    y_pred = rf_model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    logger.info(f"Model Accuracy on Test Set: {accuracy * 100:.2f}%")
    logger.info("\nClassification Report:\n" + classification_report(y_test, y_pred))

    # 7. Save the model
    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(rf_model, MODEL_PATH)
    logger.info(f"Model successfully saved to {MODEL_PATH}")
    
    # Save feature names to ensure we pass them in the correct order later
    metadata = {
        'features': features,
        'classes': rf_model.classes_.tolist()
    }
    joblib.dump(metadata, MODEL_DIR / "area_model_meta.pkl")
    logger.info("Saved metadata (features and classes order).")

if __name__ == "__main__":
    main()
