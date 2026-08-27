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
    Runs across 5 different random seeds and reports the range.
    """
    detector = AnomalyDetector(MODEL_PATH)
    n_samples = 1000
    seeds = [42, 123, 7, 9999, 314]
    fp_rates = []

    for seed in seeds:
        rng = np.random.RandomState(seed)
        false_positives = 0

        # Generate normal samples similar to training distribution
        latencies = rng.normal(15.0, 3.0, n_samples)
        losses = np.clip(rng.exponential(0.5, n_samples), 0, 10)
        jitters = rng.normal(2.0, 0.5, n_samples)

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
        fp_rates.append(fp_rate)

    min_fpr = min(fp_rates)
    max_fpr = max(fp_rates)
    avg_fpr = sum(fp_rates) / len(fp_rates)

    print(f"\nFalse Positive Rate across {len(seeds)} seeds:")
    for i, (seed, fpr) in enumerate(zip(seeds, fp_rates)):
        print(f"  Seed {seed}: {fpr:.2f}%")
    print(f"  Range: {min_fpr:.2f}% - {max_fpr:.2f}%  (avg {avg_fpr:.2f}%)")

    for seed, fpr in zip(seeds, fp_rates):
        assert fpr < 10.0, f"FPR {fpr}% exceeded 10% on seed {seed}"

def test_detection_latency():
    """Verify that scoring an incoming reading takes less than 2 seconds."""
    detector = AnomalyDetector(MODEL_PATH)
    reading = {"latency_ms": 15.0, "packet_loss_percent": 0.0, "jitter_ms": 2.0}

    # Warm up (first prediction might be slightly slower)
    detector.is_anomalous(reading)

    start_time = time.time()
    detector.is_anomalous(reading)
    duration = time.time() - start_time

    print(f"\nML Inference Latency: {duration:.4f} seconds")
    print(f"  (NOTE: Real MTTD = polling interval (~0.8s) + inference ({duration:.4f}s) ≈ 1-2s)")
    assert duration < 2.0, f"Detection latency {duration}s exceeded 2.0s threshold"

