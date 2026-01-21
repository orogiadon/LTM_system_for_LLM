"""
test_retention.py - retention.py のテスト
"""

import pytest

from src.retention import (
    calculate_retention_score,
    determine_level,
    calculate_initial_decay_coefficient,
    should_compress,
)


class TestCalculateRetentionScore:
    """calculate_retention_score のテスト"""

    def test_basic_calculation(self):
        """基本的な計算"""
        # intensity=100, decay=0.995, days=0 → 100
        score = calculate_retention_score(100, 0.995, 0)
        assert score == 100.0

    def test_decay_over_time(self):
        """時間経過による減衰"""
        # intensity=100, decay=0.995, days=100
        score = calculate_retention_score(100, 0.995, 100)
        expected = 100 * (0.995 ** 100)  # 約60.5
        assert abs(score - expected) < 0.01

    def test_low_intensity(self):
        """低感情強度"""
        score = calculate_retention_score(20, 0.995, 0)
        assert score == 20.0

    def test_zero_intensity(self):
        """感情強度0"""
        score = calculate_retention_score(0, 0.995, 100)
        assert score == 0.0

    def test_high_decay_coefficient(self):
        """高減衰係数（記憶が残りやすい）"""
        score = calculate_retention_score(100, 0.999, 100)
        expected = 100 * (0.999 ** 100)  # 約90.5
        assert abs(score - expected) < 0.01

    def test_low_decay_coefficient(self):
        """低減衰係数（記憶が消えやすい）"""
        score = calculate_retention_score(100, 0.9, 100)
        expected = 100 * (0.9 ** 100)  # ほぼ0
        assert score < 0.01


class TestDetermineLevel:
    """determine_level のテスト"""

    def test_level1_high_score(self):
        """高スコアはLevel 1"""
        level = determine_level(80)
        assert level == 1

    def test_level1_threshold(self):
        """Level 1の閾値（50）"""
        level = determine_level(50)
        assert level == 1

    def test_level2(self):
        """Level 2の範囲"""
        level = determine_level(30)
        assert level == 2

    def test_level2_threshold(self):
        """Level 2の閾値（20）"""
        level = determine_level(20)
        assert level == 2

    def test_level3(self):
        """Level 3の範囲"""
        level = determine_level(10)
        assert level == 3

    def test_level3_threshold(self):
        """Level 3の閾値（5）"""
        level = determine_level(5)
        assert level == 3

    def test_level4_archive(self):
        """Level 4（アーカイブ）"""
        level = determine_level(4)
        assert level == 4

    def test_level4_zero(self):
        """スコア0はLevel 4"""
        level = determine_level(0)
        assert level == 4


class TestCalculateInitialDecayCoefficient:
    """calculate_initial_decay_coefficient のテスト"""

    def test_casual_low_intensity(self):
        """casual + 低感情強度"""
        decay = calculate_initial_decay_coefficient("casual", 0)
        assert 0.70 <= decay <= 0.80

    def test_casual_high_intensity(self):
        """casual + 高感情強度"""
        decay = calculate_initial_decay_coefficient("casual", 100)
        assert 0.70 <= decay <= 0.80

    def test_work_category(self):
        """workカテゴリ"""
        decay = calculate_initial_decay_coefficient("work", 50)
        assert 0.85 <= decay <= 0.92

    def test_decision_category(self):
        """decisionカテゴリ"""
        decay = calculate_initial_decay_coefficient("decision", 50)
        assert 0.93 <= decay <= 0.97

    def test_emotional_category(self):
        """emotionalカテゴリ"""
        decay = calculate_initial_decay_coefficient("emotional", 50)
        assert 0.98 <= decay <= 0.999

    def test_intensity_affects_decay(self):
        """感情強度が減衰係数に影響"""
        low = calculate_initial_decay_coefficient("work", 0)
        high = calculate_initial_decay_coefficient("work", 100)
        assert high > low


class TestShouldCompress:
    """should_compress のテスト"""

    def test_no_compression_high_score(self):
        """高スコアは圧縮しない"""
        memory = {
            "current_level": 1,
            "retention_score": 80,
            "emotional_intensity": 80,
            "decay_coefficient": 0.995,
            "memory_days": 0,
            "protected": False,
        }
        should, new_level = should_compress(memory)
        assert should is False
        assert new_level == 1

    def test_compression_to_level2(self):
        """Level 1 → 2 への圧縮"""
        memory = {
            "current_level": 1,
            "retention_score": 30,
            "emotional_intensity": 50,
            "decay_coefficient": 0.995,
            "memory_days": 50,
            "protected": False,
        }
        should, new_level = should_compress(memory)
        assert should is True
        assert new_level == 2

    def test_protected_no_compression(self):
        """保護記憶は圧縮しない"""
        memory = {
            "current_level": 1,
            "retention_score": 10,
            "emotional_intensity": 50,
            "decay_coefficient": 0.995,
            "memory_days": 100,
            "protected": True,
        }
        should, new_level = should_compress(memory)
        assert should is False
        assert new_level == 1

    def test_no_downgrade(self):
        """レベルは下がらない"""
        memory = {
            "current_level": 3,
            "retention_score": 80,
            "emotional_intensity": 80,
            "decay_coefficient": 0.999,
            "memory_days": 0,
            "protected": False,
        }
        should, new_level = should_compress(memory)
        assert should is False
        assert new_level == 3
