"""
test_resonance.py - resonance.py のテスト
"""

import pytest

from src.resonance import calculate_resonance, calculate_resonance_bonus


class TestCalculateResonance:
    """calculate_resonance のテスト"""

    def test_valence_match_positive(self):
        """valence一致（positive）"""
        memory = {"emotional_valence": "positive", "emotional_arousal": 50, "emotional_tags": []}
        current = {"valence": "positive", "arousal": 50, "tags": []}
        score = calculate_resonance(memory, current)
        assert score >= 0.3  # valenceボーナス

    def test_valence_match_negative(self):
        """valence一致（negative）"""
        memory = {"emotional_valence": "negative", "emotional_arousal": 50, "emotional_tags": []}
        current = {"valence": "negative", "arousal": 50, "tags": []}
        score = calculate_resonance(memory, current)
        assert score >= 0.3

    def test_valence_mismatch(self):
        """valence不一致"""
        memory = {"emotional_valence": "positive", "emotional_arousal": 50, "emotional_tags": []}
        current = {"valence": "negative", "arousal": 50, "tags": []}
        score = calculate_resonance(memory, current)
        assert score < 0.3  # valenceボーナスなし

    def test_arousal_proximity_same(self):
        """arousal同一"""
        memory = {"emotional_valence": "neutral", "emotional_arousal": 50, "emotional_tags": []}
        current = {"valence": "neutral", "arousal": 50, "tags": []}
        score = calculate_resonance(memory, current)
        # arousalボーナス最大 + arousal近接ボーナス
        assert score >= 0.2

    def test_arousal_proximity_far(self):
        """arousal離れている"""
        memory = {"emotional_valence": "neutral", "emotional_arousal": 0, "emotional_tags": []}
        current = {"valence": "neutral", "arousal": 100, "tags": []}
        score = calculate_resonance(memory, current)
        # arousal近接ボーナスなし、valence一致で0.3
        assert abs(score - 0.3) < 0.01

    def test_tags_overlap_full(self):
        """tags完全一致"""
        memory = {"emotional_valence": "neutral", "emotional_arousal": 50, "emotional_tags": ["happy", "excited"]}
        current = {"valence": "neutral", "arousal": 50, "tags": ["happy", "excited"]}
        score = calculate_resonance(memory, current)
        # tagsボーナス = 0.5 × 1.0 = 0.5
        assert score >= 0.5

    def test_tags_overlap_partial(self):
        """tags部分一致"""
        memory = {"emotional_valence": "neutral", "emotional_arousal": 50, "emotional_tags": ["happy", "excited"]}
        current = {"valence": "neutral", "arousal": 50, "tags": ["happy", "calm"]}
        score = calculate_resonance(memory, current)
        # valence 0.3 + arousal 0.2 + tags(1/2=0.5) × 0.5 = 0.25 → 合計0.75
        assert abs(score - 0.75) < 0.01

    def test_tags_no_overlap(self):
        """tags不一致"""
        memory = {"emotional_valence": "neutral", "emotional_arousal": 50, "emotional_tags": ["happy"]}
        current = {"valence": "neutral", "arousal": 50, "tags": ["sad"]}
        score = calculate_resonance(memory, current)
        # valence 0.3 + arousal 0.2 + tags重複なし → 合計0.5
        assert abs(score - 0.5) < 0.01

    def test_empty_tags(self):
        """空のtags"""
        memory = {"emotional_valence": "neutral", "emotional_arousal": 50, "emotional_tags": []}
        current = {"valence": "neutral", "arousal": 50, "tags": []}
        score = calculate_resonance(memory, current)
        # valence 0.3 + arousal 0.2 + tags空 → 合計0.5
        assert abs(score - 0.5) < 0.01

    def test_maximum_resonance(self):
        """最大共鳴"""
        memory = {"emotional_valence": "positive", "emotional_arousal": 50, "emotional_tags": ["happy", "excited"]}
        current = {"valence": "positive", "arousal": 50, "tags": ["happy", "excited"]}
        score = calculate_resonance(memory, current)
        # valence 0.3 + arousal 0.2 + tags 0.5 = 1.0
        assert abs(score - 1.0) < 0.01


class TestCalculateResonanceBonus:
    """calculate_resonance_bonus のテスト"""

    def test_basic_bonus(self):
        """基本的なボーナス計算"""
        memory = {
            "emotional_valence": "positive",
            "emotional_arousal": 50,
            "emotional_tags": ["happy"],
            "retention_score": 100,
        }
        current = {"valence": "positive", "arousal": 50, "tags": ["happy"]}
        bonus = calculate_resonance_bonus(memory, current)
        # alpha=0.3, resonance~0.8, score=100 → bonus~24
        assert bonus > 0

    def test_zero_retention_score(self):
        """retention_score=0の場合"""
        memory = {
            "emotional_valence": "positive",
            "emotional_arousal": 50,
            "emotional_tags": ["happy"],
            "retention_score": 0,
        }
        current = {"valence": "positive", "arousal": 50, "tags": ["happy"]}
        bonus = calculate_resonance_bonus(memory, current)
        assert bonus == 0

    def test_no_resonance(self):
        """共鳴なしの場合"""
        memory = {
            "emotional_valence": "positive",
            "emotional_arousal": 0,
            "emotional_tags": [],
            "retention_score": 100,
        }
        current = {"valence": "negative", "arousal": 100, "tags": ["sad"]}
        bonus = calculate_resonance_bonus(memory, current)
        # 共鳴スコアが低いのでボーナスも低い
        assert bonus < 10
