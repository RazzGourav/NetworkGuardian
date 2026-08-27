#!/usr/bin/env python3
"""
NetworkGuardian — Train Baseline Model
Trains an Isolation Forest model on synthetic normal traffic patterns
and saves it to model.pkl.
"""

import os
import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
import logging

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("NetworkGuardian.TrainBaseline")

def generate_normal_data(n_samples=1000):
    """
    Generate synthetic normal network traffic data.
    Features: [latency_ms, packet_loss_percent, jitter_ms]
    """
    # Normal latency: ~10-20ms
    latency = np.random.normal(loc=15.0, scale=3.0, size=n_samples)
    
    # Normal packet loss: mostly 0%, occasionally up to 1-2%
    packet_loss = np.random.exponential(scale=0.5, size=n_samples)
    packet_loss = np.clip(packet_loss, 0, 100)
    
    # Normal jitter: ~1-3ms
    jitter = np.random.normal(loc=2.0, scale=0.5, size=n_samples)
    
    # Combine into feature matrix
    X = np.column_stack((latency, packet_loss, jitter))
    return X

def train_and_save_model(model_path="model.pkl"):
    """
    Train the Isolation Forest model and save it to disk.
    """
    LOG.info(f"Generating synthetic baseline data...")
    X_train = generate_normal_data(2000)
    
    LOG.info("Training Isolation Forest model...")
    # contamination is the expected proportion of outliers. Set to a low value for normal data.
    model = IsolationForest(n_estimators=100, contamination=0.01, random_state=42)
    model.fit(X_train)
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(os.path.abspath(model_path)), exist_ok=True)
    
    LOG.info(f"Saving model to {model_path}...")
    joblib.dump(model, model_path)
    LOG.info("Model training complete.")

if __name__ == "__main__":
    # If run locally or inside container, save to detection directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    target_path = os.path.join(current_dir, "model.pkl")
    train_and_save_model(target_path)
