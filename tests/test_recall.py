"""
test_recall.py - recall.py のテスト
"""

import pytest

from src.recall import process_recalled_memory, calculate_recall_weight


class TestProcessRecalledMemory:
    """process_recalled_memory のテスト"""

    def test_memory_days_halved(self):
        """memory_daysが半減する"""
        memory = {
            "memory_days": 10.0,
            "decay_coefficient": 0.995,
            "recall_count": 0,
        }
        updates = process_recalled_memory(memory)
        assert updates["memory_days"] == 5.0

    def test_decay_coefficient_boosted(self):
        """decay_coefficientが+0.02される"""
        memory = {
            "memory_days": 10.0,
            "decay_coefficient": 0.95,
            "recall_count": 0,
        }
        updates = process_recalled_memory(memory)
        assert updates["decay_coefficient"] == 0.97

    def test_decay_coefficient_capped(self):
        """decay_coefficientの上限は0.999"""
        memory = {
            "memory_days": 10.0,
            "decay_coefficient": 0.99,
            "recall_count": 0,
        }
        updates = process_recalled_memory(memory)
        assert updates["decay_coefficient"] == 0.999

    def test_recall_count_incremented(self):
        """recall_countがインクリメントされる"""
        memory = {
            "memory_days": 10.0,
            "decay_coefficient": 0.995,
            "recall_count": 5,
        }
        updates = process_recalled_memory(memory)
        assert updates["recall_count"] == 6

    def test_recalled_flag_reset(self):
        """recalled_since_last_batchがリセットされる"""
        memory = {
            "memory_days": 10.0,
            "decay_coefficient": 0.995,
            "recall_count": 0,
        }
        updates = process_recalled_memory(memory)
        assert updates["recalled_since_last_batch"] is False

    def test_zero_memory_days(self):
        """memory_days=0の場合"""
        memory = {
            "memory_days": 0.0,
            "decay_coefficient": 0.995,
            "recall_count": 0,
        }
        updates = process_recalled_memory(memory)
        assert updates["memory_days"] == 0.0


class TestCalculateRecallWeight:
    """calculate_recall_weight のテスト"""

    def test_zero_recall_count(self):
        """recall_count=0の場合、重みは1"""
        weight = calculate_recall_weight(0)
        assert weight == 1.0

    def test_recall_count_10(self):
        """recall_count=10の場合、重みは2"""
        weight = calculate_recall_weight(10)
        assert weight == 2.0

    def test_recall_count_5(self):
        """recall_count=5の場合、重みは1.5"""
        weight = calculate_recall_weight(5)
        assert weight == 1.5

    def test_high_recall_count(self):
        """高いrecall_count"""
        weight = calculate_recall_weight(100)
        assert weight == 11.0
