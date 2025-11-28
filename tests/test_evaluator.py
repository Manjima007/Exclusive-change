"""
Tests for the Flag Evaluator Service.

These tests verify the core flag evaluation logic, including:
    - Deterministic hashing (MD5)
    - Percentage rollout
    - Flag status checks
"""

import pytest

from app.services.evaluator import EvaluationReason, FlagEvaluator


class TestHashBucket:
    """Tests for the deterministic hash bucket computation."""
    
    def test_hash_bucket_is_deterministic(self):
        """Same user+flag should always produce the same bucket."""
        user_id = "user-12345"
        flag_key = "dark-mode"
        
        # Call multiple times
        bucket1 = FlagEvaluator.compute_hash_bucket(user_id, flag_key)
        bucket2 = FlagEvaluator.compute_hash_bucket(user_id, flag_key)
        bucket3 = FlagEvaluator.compute_hash_bucket(user_id, flag_key)
        
        assert bucket1 == bucket2 == bucket3
    
    def test_hash_bucket_in_valid_range(self):
        """Hash bucket should be between 0 and 99."""
        # Test with various inputs
        test_cases = [
            ("user-1", "flag-1"),
            ("user-12345", "new-checkout"),
            ("abc123", "dark-mode"),
            ("", ""),  # Edge case: empty strings
            ("a" * 1000, "b" * 1000),  # Edge case: long strings
        ]
        
        for user_id, flag_key in test_cases:
            bucket = FlagEvaluator.compute_hash_bucket(user_id, flag_key)
            assert 0 <= bucket <= 99, f"Bucket {bucket} out of range for {user_id}, {flag_key}"
    
    def test_different_users_get_different_buckets(self):
        """Different users should (usually) get different buckets."""
        flag_key = "dark-mode"
        buckets = set()
        
        # Generate 100 users and check distribution
        for i in range(100):
            bucket = FlagEvaluator.compute_hash_bucket(f"user-{i}", flag_key)
            buckets.add(bucket)
        
        # With 100 users, we should have a good distribution
        # At least 50 unique buckets (statistically likely)
        assert len(buckets) >= 50, "Hash distribution seems poor"
    
    def test_different_flags_get_different_buckets(self):
        """Same user with different flags should get different buckets."""
        user_id = "user-12345"
        
        bucket1 = FlagEvaluator.compute_hash_bucket(user_id, "flag-a")
        bucket2 = FlagEvaluator.compute_hash_bucket(user_id, "flag-b")
        bucket3 = FlagEvaluator.compute_hash_bucket(user_id, "flag-c")
        
        # These should differ (statistically very likely)
        # All being equal would be a 1/10000 chance
        unique_buckets = len({bucket1, bucket2, bucket3})
        assert unique_buckets >= 2, "Different flags produced same buckets"


class TestRolloutLogic:
    """Tests for rollout percentage logic."""
    
    def test_zero_percent_rollout(self):
        """0% rollout should never include any user."""
        flag_key = "feature"
        rollout_percentage = 0
        
        included_count = 0
        for i in range(1000):
            bucket = FlagEvaluator.compute_hash_bucket(f"user-{i}", flag_key)
            if bucket < rollout_percentage:
                included_count += 1
        
        assert included_count == 0, "0% rollout included some users"
    
    def test_100_percent_rollout(self):
        """100% rollout should include all users."""
        flag_key = "feature"
        rollout_percentage = 100
        
        included_count = 0
        for i in range(1000):
            bucket = FlagEvaluator.compute_hash_bucket(f"user-{i}", flag_key)
            if bucket < rollout_percentage:
                included_count += 1
        
        assert included_count == 1000, "100% rollout excluded some users"
    
    def test_50_percent_rollout_distribution(self):
        """50% rollout should include roughly half of users."""
        flag_key = "feature"
        rollout_percentage = 50
        
        included_count = 0
        total_users = 10000
        
        for i in range(total_users):
            bucket = FlagEvaluator.compute_hash_bucket(f"user-{i}", flag_key)
            if bucket < rollout_percentage:
                included_count += 1
        
        # Should be around 50% (allow 5% variance)
        percentage = (included_count / total_users) * 100
        assert 45 <= percentage <= 55, f"50% rollout gave {percentage}%"
    
    def test_25_percent_rollout_distribution(self):
        """25% rollout should include roughly a quarter of users."""
        flag_key = "feature"
        rollout_percentage = 25
        
        included_count = 0
        total_users = 10000
        
        for i in range(total_users):
            bucket = FlagEvaluator.compute_hash_bucket(f"user-{i}", flag_key)
            if bucket < rollout_percentage:
                included_count += 1
        
        # Should be around 25% (allow 5% variance)
        percentage = (included_count / total_users) * 100
        assert 20 <= percentage <= 30, f"25% rollout gave {percentage}%"


class TestEvaluationReason:
    """Tests for evaluation reason enum."""
    
    def test_all_reasons_have_string_values(self):
        """All evaluation reasons should have string values."""
        for reason in EvaluationReason:
            assert isinstance(reason.value, str)
            assert len(reason.value) > 0
    
    def test_reason_values_are_uppercase(self):
        """Reason values should be uppercase for consistency."""
        for reason in EvaluationReason:
            assert reason.value == reason.value.upper()


# =============================================================================
# Integration tests would go here (require database/cache mocking)
# =============================================================================

class TestEvaluatorIntegration:
    """Integration tests for the FlagEvaluator class."""
    
    @pytest.mark.skip(reason="Requires database/cache mocking")
    async def test_evaluate_flag_not_found(self):
        """Evaluating non-existent flag should return default."""
        # TODO: Implement with mocked dependencies
        pass
    
    @pytest.mark.skip(reason="Requires database/cache mocking")
    async def test_evaluate_disabled_flag(self):
        """Disabled flag should always return False."""
        # TODO: Implement with mocked dependencies
        pass
    
    @pytest.mark.skip(reason="Requires database/cache mocking")
    async def test_evaluate_with_cache_hit(self):
        """Evaluation with cache hit should not query database."""
        # TODO: Implement with mocked dependencies
        pass
