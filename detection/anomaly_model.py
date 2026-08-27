#!/usr/bin/env python3
"""
NetworkGuardian — Anomaly Detection Model
Loads the trained Isolation Forest model and scores incoming readings in real time.
Provides a threshold-based fallback for robustness.
"""

import os
import joblib
import numpy as np
import logging

LOG = logging.getLogger("NetworkGuardian.AnomalyModel")

class AnomalyDetector:
    def __init__(self, model_path="model.pkl"):
        self.model = None
        self._load_model(model_path)
        
    def _load_model(self, model_path):
        """Loads the pre-trained ML model."""
        if os.path.exists(model_path):
            try:
                self.model = joblib.load(model_path)
                LOG.info(f"Successfully loaded anomaly model from {model_path}")
            except Exception as e:
                LOG.error(f"Failed to load model from {model_path}: {e}")
                self.model = None
        else:
            LOG.warning(f"Model file {model_path} not found. Operating in fallback-only mode.")
            self.model = None

    def is_anomalous(self, reading: dict) -> tuple[bool, float]:
        """
        Score an incoming metric reading in real time.
        
        Args:
            reading: Dictionary with at least:
                - latency_ms (float)
                - packet_loss_percent (float)
                - jitter_ms (float)
                
        Returns:
            (is_anomalous, score)
            where score is < 0 for anomalies in ML model, or a specific value for fallback.
        """
        # Default features
        latency = reading.get("latency_ms", 0.0)
        packet_loss = reading.get("packet_loss_percent", 0.0)
        jitter = reading.get("jitter_ms", 0.0)
        
        # 1. Threshold-based fallback (Robustness layer)
        # If latency is insanely high or loss is > 20%, it's definitely an anomaly.
        if packet_loss > 20.0 or latency > 100.0:
            LOG.warning(f"Threshold anomaly detected: latency={latency}ms, loss={packet_loss}%")
            return True, -1.0
            
        # 2. ML Model Scoring
        if self.model is not None:
            X = np.array([[latency, packet_loss, jitter]])
            # predict returns 1 for inliers, -1 for outliers
            prediction = self.model.predict(X)[0]
            # score_samples returns the anomaly score (negative means more anomalous)
            score = self.model.score_samples(X)[0]
            
            is_anomaly = bool(prediction == -1)
            return is_anomaly, score
            
        # If no model and threshold not crossed, assume normal
        return False, 1.0

# Provide a singleton-like functional interface for easier import
_default_detector = None

def init_detector(model_path=None):
    global _default_detector
    if model_path is None:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        model_path = os.path.join(current_dir, "model.pkl")
    _default_detector = AnomalyDetector(model_path)

def is_anomalous(reading: dict) -> tuple[bool, float]:
    """Exposed functional interface for real-time scoring."""
    global _default_detector
    if _default_detector is None:
        init_detector()
    return _default_detector.is_anomalous(reading)
