import os
import random
import joblib
import numpy as np
from sklearn.ensemble import RandomForestRegressor

MODEL_PATH = os.path.join(os.path.dirname(__file__), "forecast_model.joblib")

NEIGHBORHOODS = ["Mangolpuri", "Rohini", "Pitampura", "Saraswati Vihar", "Paschim Vihar"]
# One-hot index per neighborhood, mirroring the frontend's NEIGHBORHOOD_BASE weighting
NEIGHBORHOOD_BASE = {"Mangolpuri": 1.15, "Rohini": 0.95, "Pitampura": 1.05,
                      "Saraswati Vihar": 0.80, "Paschim Vihar": 1.25}


def _encode(neighborhood: str, hour: int, is_weekend: int, is_raining: int):
    idx = NEIGHBORHOODS.index(neighborhood)
    one_hot = [1 if i == idx else 0 for i in range(len(NEIGHBORHOODS))]
    return one_hot + [hour, is_weekend, is_raining]


def generate_training_data(n_samples: int = 4000, seed: int = 42):
    rng = random.Random(seed)
    X, y = [], []
    for _ in range(n_samples):
        n = rng.choice(NEIGHBORHOODS)
        hour = rng.randint(6, 23)
        is_weekend = rng.choice([0, 1])
        is_raining = rng.choice([0, 1])

        base = 30 * NEIGHBORHOOD_BASE[n]
        val = base
        if 18 <= hour <= 22:
            val += 15
        if is_weekend:
            val += 35
        if is_raining:
            val += 20
        val += rng.gauss(0, 6)  # noise so the forest has something to learn beyond the linear rule

        X.append(_encode(n, hour, is_weekend, is_raining))
        y.append(max(0, val))
    return np.array(X), np.array(y)


def train_and_save():
    X, y = generate_training_data()
    model = RandomForestRegressor(n_estimators=200, max_depth=8, random_state=42)
    model.fit(X, y)
    joblib.dump(model, MODEL_PATH)
    print(f"Trained RandomForestRegressor on {len(X)} samples → saved to {MODEL_PATH}")
    return model


def load_model():
    if not os.path.exists(MODEL_PATH):
        return train_and_save()
    return joblib.load(MODEL_PATH)


_model = None


def predict_hotspot(neighborhood: str, hour: int, is_weekend: bool, is_raining: bool) -> dict:
    global _model
    if _model is None:
        _model = load_model()
    features = np.array([_encode(neighborhood, hour, int(is_weekend), int(is_raining))])
    predicted = float(_model.predict(features)[0])
    severity = min(round((predicted / 120) * 100), 100)
    return {
        "neighborhood": neighborhood,
        "predicted_servings": round(predicted),
        "hotspot_severity_percent": severity,
        "recommended_action": "Pre-stage volunteers" if severity > 60 else "Monitor",
    }


if __name__ == "__main__":
    train_and_save()
