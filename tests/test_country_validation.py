"""
Test Suite for Country Validation in country_to_country Intent

This test suite validates that:
1. Valid countries are accepted and URLs are generated correctly
2. Invalid countries are rejected at multiple layers
3. Mixed valid/invalid countries are handled gracefully
4. Edge cases (empty, special chars, etc.) are handled
5. Existing functionality is not broken
"""

import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from chatbot.services.slot_manager import SlotManager, SlotConfig


class TestCountryValidation:
    """Test country validation logic in SlotManager"""

    def setup_method(self):
        """Setup test instance"""
        self.slot_manager = SlotManager(redis_manager=None)  # Use in-memory store
        self.session_id = "test_session_123"

    def teardown_method(self):
        """Cleanup after each test"""
        self.slot_manager.clear_slots(self.session_id)

    # ========================================================================
    # TEST 1: Valid Country Names - Should Accept
    # ========================================================================

    def test_valid_country_single_word(self):
        """Test that single-word valid countries are accepted"""
        assert self.slot_manager.is_valid_country("india") == True
        assert self.slot_manager.is_valid_country("china") == True
        assert self.slot_manager.is_valid_country("usa") == True
        assert self.slot_manager.is_valid_country("france") == True

    def test_valid_country_multi_word(self):
        """Test that multi-word valid countries are accepted"""
        assert self.slot_manager.is_valid_country("united states") == True
        assert self.slot_manager.is_valid_country("united kingdom") == True
        assert self.slot_manager.is_valid_country("south korea") == True
        assert self.slot_manager.is_valid_country("south africa") == True

    def test_valid_country_hyphenated(self):
        """Test that hyphenated country names are accepted"""
        assert self.slot_manager.is_valid_country("united-states") == True
        assert self.slot_manager.is_valid_country("united-kingdom") == True
        assert self.slot_manager.is_valid_country("south-korea") == True

    def test_valid_country_case_insensitive(self):
        """Test that validation is case-insensitive"""
        assert self.slot_manager.is_valid_country("USA") == True
        assert self.slot_manager.is_valid_country("United States") == True
        assert self.slot_manager.is_valid_country("CHINA") == True
        assert self.slot_manager.is_valid_country("India") == True

    # ========================================================================
    # TEST 2: Invalid Country Names - Should Reject
    # ========================================================================

    def test_invalid_country_names(self):
        """Test that invalid country names are rejected"""
        assert self.slot_manager.is_valid_country("atlantis") == False
        assert self.slot_manager.is_valid_country("narnia") == False
        assert self.slot_manager.is_valid_country("wakanda") == False
        assert self.slot_manager.is_valid_country("xyz") == False

    def test_invalid_country_empty(self):
        """Test that empty strings are rejected"""
        assert self.slot_manager.is_valid_country("") == False
        assert self.slot_manager.is_valid_country("   ") == False

    def test_invalid_country_special_chars(self):
        """Test that strings with special characters are rejected"""
        assert self.slot_manager.is_valid_country("Do-It.") == False
        assert self.slot_manager.is_valid_country("All-You.") == False
        assert self.slot_manager.is_valid_country("@#$%") == False

    def test_invalid_country_random_text(self):
        """Test that random text is rejected"""
        assert self.slot_manager.is_valid_country("import") == False
        assert self.slot_manager.is_valid_country("export") == False
        assert self.slot_manager.is_valid_country("all you") == False
        assert self.slot_manager.is_valid_country("do it") == False

    # ========================================================================
    # TEST 3: Slot Update with country_to_country Intent
    # ========================================================================

    def test_slot_update_valid_countries(self):
        """Test that valid countries are stored in slots"""
        params = {
            "origin_country": "belgium",
            "destination_country": "france",
            "direction": "export"
        }

        state = self.slot_manager.update_slots(
            self.session_id,
            "country_to_country",
            params
        )

        # Both countries should be stored
        assert state.slots.get("origin_country") == "belgium"
        assert state.slots.get("destination_country") == "france"
        assert state.slots.get("direction") == "export"
        assert len(state.missing_slots) == 0

    def test_slot_update_invalid_origin(self):
        """Test that invalid origin country is rejected"""
        params = {
            "origin_country": "atlantis",
            "destination_country": "france",
            "direction": "export"
        }

        state = self.slot_manager.update_slots(
            self.session_id,
            "country_to_country",
            params
        )

        # Invalid origin should be removed, destination should remain
        assert "origin_country" not in state.slots
        assert state.slots.get("destination_country") == "france"
        # origin_country should be marked as missing
        assert "origin_country" in state.missing_slots

    def test_slot_update_invalid_destination(self):
        """Test that invalid destination country is rejected"""
        params = {
            "origin_country": "belgium",
            "destination_country": "narnia",
            "direction": "export"
        }

        state = self.slot_manager.update_slots(
            self.session_id,
            "country_to_country",
            params
        )

        # Origin should remain, invalid destination should be removed
        assert state.slots.get("origin_country") == "belgium"
        assert "destination_country" not in state.slots
        # destination_country should be marked as missing
        assert "destination_country" in state.missing_slots

    def test_slot_update_both_invalid(self):
        """Test that both invalid countries are rejected"""
        params = {
            "origin_country": "atlantis",
            "destination_country": "narnia",
            "direction": "export"
        }

        state = self.slot_manager.update_slots(
            self.session_id,
            "country_to_country",
            params
        )

        # Both should be removed
        assert "origin_country" not in state.slots
        assert "destination_country" not in state.slots
        # Both should be marked as missing
        assert "origin_country" in state.missing_slots
        assert "destination_country" in state.missing_slots

    # ========================================================================
    # TEST 4: URL Generation with country_to_country Intent
    # ========================================================================

    def test_url_generation_valid_countries(self):
        """Test that valid countries generate correct URL"""
        slots = {
            "origin_country": "belgium",
            "destination_country": "france",
            "direction": "export"
        }

        url = self.slot_manager.generate_url("country_to_country", slots)

        assert url is not None
        assert "Belgium" in url
        assert "France" in url
        assert "export" in url
        assert "/cntry/" in url

    def test_url_generation_invalid_origin(self):
        """Test that invalid origin prevents URL generation"""
        slots = {
            "origin_country": "atlantis",
            "destination_country": "france",
            "direction": "export"
        }

        url = self.slot_manager.generate_url("country_to_country", slots)

        # Should return None because origin is invalid
        assert url is None

    def test_url_generation_invalid_destination(self):
        """Test that invalid destination prevents URL generation"""
        slots = {
            "origin_country": "belgium",
            "destination_country": "narnia",
            "direction": "export"
        }

        url = self.slot_manager.generate_url("country_to_country", slots)

        # Should return None because destination is invalid
        assert url is None

    def test_url_generation_both_invalid(self):
        """Test that both invalid prevents URL generation"""
        slots = {
            "origin_country": "atlantis",
            "destination_country": "narnia",
            "direction": "export"
        }

        url = self.slot_manager.generate_url("country_to_country", slots)

        # Should return None
        assert url is None

    def test_url_generation_multi_word_countries(self):
        """Test URL generation with multi-word country names"""
        slots = {
            "origin_country": "united-states",
            "destination_country": "south-korea",
            "direction": "export"
        }

        url = self.slot_manager.generate_url("country_to_country", slots)

        assert url is not None
        # Multi-word countries should use %20 for spaces
        assert "United%20States" in url or "United-States" in url
        assert "South%20Korea" in url or "South-Korea" in url

    # ========================================================================
    # TEST 5: Edge Cases and Special Scenarios
    # ========================================================================

    def test_normalization_preserves_validity(self):
        """Test that country normalization maintains validity"""
        # Test various formats that should all normalize to the same valid country
        test_cases = [
            "usa",
            "USA",
            "Usa",
            "united states",
            "United States",
            "UNITED STATES",
            "united-states",
            "United-States"
        ]

        for country in test_cases:
            normalized = self.slot_manager._normalize_country(country)
            # After normalization, it should still be valid
            assert self.slot_manager.is_valid_country(normalized), \
                f"Country '{country}' normalized to '{normalized}' but is not valid"

    def test_slot_update_with_special_chars_in_country(self):
        """Test that countries with special characters are properly rejected"""
        params = {
            "origin_country": "Do-It.",
            "destination_country": "All-You.",
            "direction": "import"
        }

        state = self.slot_manager.update_slots(
            self.session_id,
            "country_to_country",
            params
        )

        # Both should be rejected due to special characters
        assert "origin_country" not in state.slots
        assert "destination_country" not in state.slots

    def test_intent_change_clears_invalid_slots(self):
        """Test that changing intent clears previous invalid slots"""
        # First, set some invalid countries
        params1 = {
            "origin_country": "atlantis",
            "destination_country": "narnia"
        }

        state1 = self.slot_manager.update_slots(
            self.session_id,
            "country_to_country",
            params1
        )

        # Then change to a different intent
        params2 = {
            "country": "india"
        }

        state2 = self.slot_manager.update_slots(
            self.session_id,
            "search_country_data",
            params2
        )

        # Previous invalid countries should be gone
        assert "origin_country" not in state2.slots
        assert "destination_country" not in state2.slots
        assert state2.intent == "search_country_data"

    # ========================================================================
    # TEST 6: Existing Functionality - Ensure Nothing Broke
    # ========================================================================

    def test_other_intents_not_affected(self):
        """Test that validation doesn't affect other intents"""
        # Test search_country_data
        params = {"country": "india", "direction": "import"}
        state = self.slot_manager.update_slots(
            self.session_id,
            "search_country_data",
            params
        )
        assert state.slots.get("country") == "india"

        # Clear for next test
        self.slot_manager.clear_slots(self.session_id)

        # Test search_trade_data
        params = {"country": "china", "product": "steel", "direction": "export"}
        state = self.slot_manager.update_slots(
            self.session_id,
            "search_trade_data",
            params
        )
        assert state.slots.get("country") == "china"
        assert state.slots.get("product") == "steel"

    def test_continent_detection_still_works(self):
        """Test that continent detection is not affected"""
        assert self.slot_manager.is_continent("africa") == True
        assert self.slot_manager.is_continent("asia") == True
        assert self.slot_manager.is_continent("europe") == True
        assert self.slot_manager.is_continent("india") == False  # country, not continent

    def test_restricted_country_detection_still_works(self):
        """Test that restricted country detection is not affected"""
        assert self.slot_manager.is_restricted_country("india") == True
        assert self.slot_manager.is_restricted_country("usa") == False


class TestKnownCountriesList:
    """Test that KNOWN_COUNTRIES list is comprehensive"""

    def test_known_countries_not_empty(self):
        """Ensure KNOWN_COUNTRIES has entries"""
        assert len(SlotConfig.KNOWN_COUNTRIES) > 0

    def test_known_countries_includes_major_economies(self):
        """Ensure major economies are in the list"""
        major_economies = [
            "usa", "china", "japan", "germany", "united kingdom",
            "france", "india", "italy", "brazil", "canada"
        ]

        for country in major_economies:
            assert country in SlotConfig.KNOWN_COUNTRIES, \
                f"Major economy '{country}' missing from KNOWN_COUNTRIES"

    def test_known_countries_includes_aliases(self):
        """Ensure common aliases are included"""
        # USA variations
        assert "usa" in SlotConfig.KNOWN_COUNTRIES or "united states" in SlotConfig.KNOWN_COUNTRIES

        # UK variations
        assert "uk" in SlotConfig.KNOWN_COUNTRIES or "united kingdom" in SlotConfig.KNOWN_COUNTRIES


class TestRegressionPrevention:
    """Test cases based on the original bug report"""

    def setup_method(self):
        """Setup test instance"""
        self.slot_manager = SlotManager(redis_manager=None)
        self.session_id = "regression_test"

    def teardown_method(self):
        """Cleanup"""
        self.slot_manager.clear_slots(self.session_id)

    def test_original_bug_scenario(self):
        """
        Test the original bug: pasted text was incorrectly classified as country_to_country
        with random words extracted as countries (Do-It., All-You.)
        """
        # Simulate LLM incorrectly extracting countries from pasted text
        params = {
            "origin_country": "Do-It.",
            "destination_country": "All-You.",
            "direction": "import"
        }

        state = self.slot_manager.update_slots(
            self.session_id,
            "country_to_country",
            params
        )

        # These invalid countries should be rejected
        assert "origin_country" not in state.slots
        assert "destination_country" not in state.slots

        # URL should NOT be generated
        url = self.slot_manager.generate_url("country_to_country", state.slots)
        assert url is None

        print("✓ Original bug scenario: Invalid countries rejected, no URL generated")

    def test_original_bug_url_not_created(self):
        """Ensure the original malformed URL cannot be created"""
        slots = {
            "origin_country": "Do-It.",
            "destination_country": "All-You.",
            "direction": "import"
        }

        url = self.slot_manager.generate_url("country_to_country", slots)

        # This malformed URL should NOT be created
        assert url is None
        assert url != "https://www.marketinsidedata.com/en/cntry/Do-It.-import-All-You."

        print("✓ Malformed URL cannot be created")


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "-s"])
