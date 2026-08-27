import os
import time
import pytest
import numpy as np

from detection.train_baseline import train_and_save_model
from detection.anomaly_model import AnomalyDetector, init_detector, is_anomalous

MODEL_PATH = "tests/test_model.pkl"

@pytest.fixture(scope="module", autouse=True)
def setup_model():
    """Train and save a model before running tests."""
    train_and_save_model(MODEL_PATH)
    init_detector(MODEL_PATH)
    yield
    # Cleanup after tests
    if os.path.exists(MODEL_PATH):
        os.remove(MODEL_PATH)

def test_model_training_creates_file():
    """Verify that training the model creates the expected file."""
    assert os.path.exists(MODEL_PATH), "Model file should exist after training"

def test_threshold_fallback():
    """Verify that threshold-based rules catch extreme anomalies."""
    # High packet loss
    reading_loss = {"latency_ms": 15.0, "packet_loss_percent": 25.0, "jitter_ms": 2.0}
    is_anomaly, score = is_anomalous(reading_loss)
    assert is_anomaly, "Should flag >20% packet loss as anomaly"
    assert score == -1.0, "Threshold fallback should return score -1.0"

    # High latency
    reading_lat = {"latency_ms": 150.0, "packet_loss_percent": 0.0, "jitter_ms": 5.0}
    is_anomaly, score = is_anomalous(reading_lat)
    assert is_anomaly, "Should flag >100ms latency as anomaly"
    assert score == -1.0, "Threshold fallback should return score -1.0"

def test_ml_anomaly_detection():
    """Verify that ML model catches subtle anomalies that bypass threshold."""
    # Subtle anomaly: 50ms latency is unusual based on 15ms baseline, but bypasses 100ms threshold
    subtle_reading = {"latency_ms": 50.0, "packet_loss_percent": 5.0, "jitter_ms": 10.0}
    is_anomaly, score = is_anomalous(subtle_reading)
    assert is_anomaly, "ML model should catch subtle anomalies"
    assert score < 0, "ML model should return a negative score for anomalies"

def test_false_positive_rate():
    """
    Verify false positive rate is under 10% on stable synthetic data.
    """
    detector = AnomalyDetector(MODEL_PATH)
    n_samples = 1000
    false_positives = 0
    
    # Generate 1000 normal samples (similar to training data distribution)
    latencies = np.random.normal(15.0, 3.0, n_samples)
    losses = np.clip(np.random.exponential(0.5, n_samples), 0, 10)
    jitters = np.random.normal(2.0, 0.5, n_samples)
    
    for i in range(n_samples):
        reading = {
            "latency_ms": latencies[i],
            "packet_loss_percent": losses[i],
            "jitter_ms": jitters[i]
        }
        is_anomaly, _ = detector.is_anomalous(reading)
        if is_anomaly:
            false_positives += 1
            
    fp_rate = (false_positives / n_samples) * 100.0
    print(f"\nFalse Positive Rate: {fp_rate:.2f}%")
    assert fp_rate < 10.0, f"False positive rate {fp_rate}% exceeded 10% threshold"

def test_detection_latency():
    """Verify that scoring an incoming reading takes less than 2 seconds."""
    detector = AnomalyDetector(MODEL_PATH)
    reading = {"latency_ms": 15.0, "packet_loss_percent": 0.0, "jitter_ms": 2.0}
    
    # Warm up (first prediction might be slightly slower due to loading dependencies etc.)
    detector.is_anomalous(reading)
    
    start_time = time.time()
    detector.is_anomalous(reading)
    duration = time.time() - start_time
    
    print(f"\nDetection Latency: {duration:.4f} seconds")
    assert duration < 2.0, f"Detection latency {duration}s exceeded 2.0s threshold"
