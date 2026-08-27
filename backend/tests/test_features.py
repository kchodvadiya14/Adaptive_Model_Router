"""Tests for prompt feature extraction."""

from app.router.features import extract_features


def test_extract_features_detects_code():
    features = extract_features("Debug this Python code:\n```python\ndef foo():\n    pass\n```")
    assert features.has_code is True
    assert features.word_count > 0


def test_extract_features_detects_math():
    features = extract_features("Solve the equation 2x + 5 = 15 and calculate the integral.")
    assert features.has_math is True


def test_extract_features_instruction_count():
    features = extract_features("1. Analyze the data\n2. Write code\n3. Summarize findings")
    assert features.instruction_count >= 2
