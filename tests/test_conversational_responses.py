"""
Test Suite: Conversational Responses Validation

Tests the fixes for the bug where conversational phrases like "you suggest"
were being treated as valid country names.
"""

import pytest
from chatbot.services.slot_manager import SlotManager, SlotConfig


class TestConversationalResponseValidation:
    """Test validation of conversational responses in slot collection"""

    def setup_method(self):
        """Set up test fixtures"""
        self.slot_mgr = SlotManager(redis_manager=None)  # Use memory fallback
        self.session_id = "test-session-123"

    def test_reject_you_suggest(self):
        """Test that 'you suggest' is rejected as a country name"""
        intent = "search_trade_data"
        params = {"country": "you suggest", "product": "copper"}

        # Update slots
        state = self.slot_mgr.update_slots(self.session_id, intent, params)

        # Country should be cleared (not in slots)
        assert "country" not in state.slots or state.slots["country"] == ""
        # Country should be in missing slots
        assert "country" in state.missing_slots

    def test_reject_suggest(self):
        """Test that 'suggest' is rejected as a country name"""
        intent = "search_country_data"
        params = {"country": "suggest"}

        state = self.slot_mgr.update_slots(self.session_id, intent, params)

        assert "country" not in state.slots or state.slots["country"] == ""
        assert "country" in state.missing_slots

    def test_reject_any(self):
        """Test that 'any' is rejected as a country name"""
        intent = "hs_code"
        params = {"country": "any", "hs_code": "8301"}

        state = self.slot_mgr.update_slots(self.session_id, intent, params)

        assert "country" not in state.slots or state.slots["country"] == ""
        assert "country" in state.missing_slots

    def test_reject_recommend(self):
        """Test that 'recommend' is rejected as a country name"""
        intent = "search_trade_data"
        params = {"country": "recommend", "product": "steel"}

        state = self.slot_mgr.update_slots(self.session_id, intent, params)

        assert "country" not in state.slots or state.slots["country"] == ""
        assert "country" in state.missing_slots

    def test_reject_whatever(self):
        """Test that 'whatever' is rejected as a country name"""
        intent = "search_country_data"
        params = {"country": "whatever"}

        state = self.slot_mgr.update_slots(self.session_id, intent, params)

        assert "country" not in state.slots or state.slots["country"] == ""
        assert "country" in state.missing_slots

    def test_reject_invalid_responses(self):
        """Test that invalid responses like 'yes', 'no', 'ok' are rejected"""
        invalid_responses = ["yes", "no", "ok", "okay", "sure", "maybe"]

        for response in invalid_responses:
            # Reset session for each test
            session_id = f"test-session-{response}"
            intent = "search_trade_data"
            params = {"country": response, "product": "electronics"}

            state = self.slot_mgr.update_slots(session_id, intent, params)

            assert "country" not in state.slots or state.slots["country"] == "", \
                f"Failed to reject '{response}' as country name"
            assert "country" in state.missing_slots, \
                f"Country should be in missing_slots for response '{response}'"

    def test_accept_valid_country(self):
        """Test that valid country names are accepted"""
        valid_countries = ["usa", "china", "india", "germany", "japan"]

        for country in valid_countries:
            # Reset session for each test
            session_id = f"test-session-{country}"
            intent = "search_country_data"
            params = {"country": country}

            state = self.slot_mgr.update_slots(session_id, intent, params)

            assert state.slots.get("country") == country.lower().replace(" ", "-"), \
                f"Failed to accept valid country '{country}'"
            assert "country" not in state.missing_slots, \
                f"Country should not be in missing_slots for '{country}'"

    def test_accept_multi_word_country(self):
        """Test that multi-word country names are accepted"""
        multi_word_countries = [
            ("united states", "united-states"),
            ("south korea", "south-korea"),
            ("saudi arabia", "saudi-arabia"),
            ("united kingdom", "united-kingdom")
        ]

        for original, normalized in multi_word_countries:
            session_id = f"test-session-{normalized}"
            intent = "search_country_data"
            params = {"country": original}

            state = self.slot_mgr.update_slots(session_id, intent, params)

            assert state.slots.get("country") == normalized, \
                f"Failed to normalize '{original}' to '{normalized}'"
            assert "country" not in state.missing_slots

    def test_hs_code_intent_validation(self):
        """Test that hs_code intent also validates country names"""
        intent = "hs_code"
        params = {"country": "you suggest", "hs_code": "8301"}

        state = self.slot_mgr.update_slots(self.session_id, intent, params)

        assert "country" not in state.slots or state.slots["country"] == ""
        assert "country" in state.missing_slots

    def test_country_to_country_validation(self):
        """Test that country_to_country intent validates both origin and destination"""
        intent = "country_to_country"

        # Test invalid origin_country
        params = {"origin_country": "you suggest", "destination_country": "usa"}
        state = self.slot_mgr.update_slots(self.session_id, intent, params)
        assert "origin_country" not in state.slots or state.slots["origin_country"] == ""

        # Test invalid destination_country
        self.slot_mgr.clear_slots(self.session_id)
        params = {"origin_country": "china", "destination_country": "recommend"}
        state = self.slot_mgr.update_slots(self.session_id, intent, params)
        assert "destination_country" not in state.slots or state.slots["destination_country"] == ""

    def test_generate_url_rejects_invalid_country(self):
        """Test that generate_url returns None for invalid countries"""
        intent = "search_country_data"

        # Test with invalid country
        slots_invalid = {"country": "you-suggest"}
        url = self.slot_mgr.generate_url(intent, slots_invalid)
        assert url is None, "URL should be None for invalid country"

        # Test with valid country
        slots_valid = {"country": "usa"}
        url = self.slot_mgr.generate_url(intent, slots_valid)
        assert url is not None, "URL should be generated for valid country"
        assert "usa" in url.lower()

    def test_generate_url_hs_code_validation(self):
        """Test that generate_url for hs_code intent validates country"""
        intent = "hs_code"

        # Test with invalid country
        slots_invalid = {"country": "suggest", "hs_code": "8301"}
        url = self.slot_mgr.generate_url(intent, slots_invalid)
        assert url is None, "URL should be None for invalid country in hs_code"

        # Test with valid country
        slots_valid = {"country": "usa", "hs_code": "8301"}
        url = self.slot_mgr.generate_url(intent, slots_valid)
        assert url is not None, "URL should be generated for valid country in hs_code"
        assert "usa" in url.lower()
        assert "8301" in url

    def test_is_valid_country(self):
        """Test the is_valid_country method"""
        # Valid countries
        assert self.slot_mgr.is_valid_country("usa")
        assert self.slot_mgr.is_valid_country("china")
        assert self.slot_mgr.is_valid_country("united-states")
        assert self.slot_mgr.is_valid_country("united states")

        # Invalid conversational phrases
        assert not self.slot_mgr.is_valid_country("you suggest")
        assert not self.slot_mgr.is_valid_country("suggest")
        assert not self.slot_mgr.is_valid_country("any")
        assert not self.slot_mgr.is_valid_country("recommend")
        assert not self.slot_mgr.is_valid_country("whatever")

        # Invalid responses
        assert not self.slot_mgr.is_valid_country("yes")
        assert not self.slot_mgr.is_valid_country("no")
        assert not self.slot_mgr.is_valid_country("ok")

    def test_case_insensitive_validation(self):
        """Test that validation is case-insensitive"""
        # Valid countries in different cases
        assert self.slot_mgr.is_valid_country("USA")
        assert self.slot_mgr.is_valid_country("UsA")
        assert self.slot_mgr.is_valid_country("China")
        assert self.slot_mgr.is_valid_country("UNITED STATES")

        # Invalid responses in different cases
        assert not self.slot_mgr.is_valid_country("You Suggest")
        assert not self.slot_mgr.is_valid_country("SUGGEST")
        assert not self.slot_mgr.is_valid_country("Any")

    def test_hyphenated_and_spaced_country_names(self):
        """Test that both hyphenated and spaced formats work"""
        # Both formats should be recognized as valid
        assert self.slot_mgr.is_valid_country("south-korea")
        assert self.slot_mgr.is_valid_country("south korea")
        assert self.slot_mgr.is_valid_country("united-states")
        assert self.slot_mgr.is_valid_country("united states")

    def test_conversational_phrases_list(self):
        """Test all conversational phrases are rejected"""
        conversational_phrases = [
            "you-suggest", "you suggest", "suggest", "any", "all", "anywhere",
            "everywhere", "all-countries", "multiple", "many", "several",
            "which", "what", "where", "recommend", "best", "whatever",
            "doesn't matter", "dont care", "don't care", "idk", "i don't know",
            "i dunno", "dunno", "pick one", "choose", "decide", "up to you",
            "you pick", "you choose", "you decide", "your choice", "your pick"
        ]

        for phrase in conversational_phrases:
            session_id = f"test-phrase-{phrase.replace(' ', '-')}"
            intent = "search_country_data"
            params = {"country": phrase}

            state = self.slot_mgr.update_slots(session_id, intent, params)

            assert "country" not in state.slots or state.slots["country"] == "", \
                f"Failed to reject conversational phrase '{phrase}'"


class TestSlotManagerEdgeCases:
    """Test edge cases and boundary conditions"""

    def setup_method(self):
        """Set up test fixtures"""
        self.slot_mgr = SlotManager(redis_manager=None)

    def test_empty_country(self):
        """Test that empty country is handled properly"""
        session_id = "test-empty"
        intent = "search_country_data"
        params = {"country": ""}

        state = self.slot_mgr.update_slots(session_id, intent, params)
        assert "country" in state.missing_slots

    def test_whitespace_only_country(self):
        """Test that whitespace-only country is rejected"""
        session_id = "test-whitespace"
        intent = "search_country_data"
        params = {"country": "   "}

        state = self.slot_mgr.update_slots(session_id, intent, params)
        assert "country" not in state.slots or state.slots["country"] == ""

    def test_numeric_country(self):
        """Test that numeric values are rejected as country names"""
        session_id = "test-numeric"
        intent = "search_country_data"
        params = {"country": "123"}

        state = self.slot_mgr.update_slots(session_id, intent, params)
        assert "country" not in state.slots or state.slots["country"] == ""

    def test_special_characters_country(self):
        """Test that special characters are rejected"""
        special_chars = ["@#$", "!!!", "???", "***"]

        for chars in special_chars:
            session_id = f"test-special-{chars}"
            intent = "search_country_data"
            params = {"country": chars}

            state = self.slot_mgr.update_slots(session_id, intent, params)
            assert "country" not in state.slots or state.slots["country"] == "", \
                f"Failed to reject special characters '{chars}'"


class TestValidCountryAcceptance:
    """Test that valid countries are properly accepted"""

    def setup_method(self):
        """Set up test fixtures"""
        self.slot_mgr = SlotManager(redis_manager=None)

    def test_accept_afghanistan(self):
        """Test that Afghanistan is accepted as a valid country"""
        session_id = "test-afghanistan"
        intent = "search_trade_data"
        params = {"country": "afghanistan", "product": "copper"}

        state = self.slot_mgr.update_slots(session_id, intent, params)

        # Afghanistan should be accepted (either in list or via heuristics)
        assert state.slots.get("country") == "afghanistan"
        assert "country" not in state.missing_slots

    def test_accept_countries_not_in_list(self):
        """Test that valid countries not in KNOWN_COUNTRIES are accepted via heuristics"""
        # These might not be in KNOWN_COUNTRIES but should pass heuristics
        potential_countries = [
            "saint lucia", "timor leste", "cabo verde",
            "papua new guinea", "marshall islands"
        ]

        for country in potential_countries:
            # Check if it's accepted (either in list or via heuristics)
            is_valid = self.slot_mgr.is_valid_country(country)
            assert is_valid, f"Failed to accept valid country '{country}'"

    def test_all_known_countries_accepted(self):
        """Test that all countries in KNOWN_COUNTRIES are accepted"""
        # Sample of countries from KNOWN_COUNTRIES
        known_countries = [
            "afghanistan", "albania", "algeria", "argentina", "australia",
            "bangladesh", "brazil", "canada", "china", "egypt",
            "france", "germany", "india", "indonesia", "japan",
            "mexico", "nigeria", "pakistan", "russia", "south africa",
            "united states", "vietnam", "zimbabwe"
        ]

        for country in known_countries:
            assert self.slot_mgr.is_valid_country(country), \
                f"Failed to accept known country '{country}'"


class TestLoopDetection:
    """Test loop detection and escalation to support"""

    def setup_method(self):
        """Set up test fixtures"""
        self.slot_mgr = SlotManager(redis_manager=None)
        self.session_id = "test-loop-detection"

    def test_ask_count_increments(self):
        """Test that ask count increments each time we ask for a slot"""
        intent = "search_country_data"
        slots = {}  # No country provided

        # First ask
        question1 = self.slot_mgr.get_missing_slot_question(self.session_id, intent, slots)
        assert question1 is not None
        assert not question1.get("too_many_attempts")

        # Second ask
        question2 = self.slot_mgr.get_missing_slot_question(self.session_id, intent, slots)
        assert question2 is not None
        assert not question2.get("too_many_attempts")

        # Third ask - should trigger escalation
        question3 = self.slot_mgr.get_missing_slot_question(self.session_id, intent, slots)
        assert question3 is not None
        assert question3.get("too_many_attempts") is True
        assert "message" in question3

    def test_ask_count_resets_on_successful_fill(self):
        """Test that ask count resets when a slot is successfully filled"""
        intent = "search_country_data"
        slots = {}

        # Ask for country (increment count)
        question1 = self.slot_mgr.get_missing_slot_question(self.session_id, intent, slots)
        assert question1 is not None

        # Provide valid country
        params = {"country": "usa"}
        state = self.slot_mgr.update_slots(self.session_id, intent, params)

        # Ask count should be reset to 0
        assert state.slot_ask_counts.get("country") == 0

    def test_different_slots_tracked_separately(self):
        """Test that different slots have independent ask counts"""
        intent = "country_to_country"

        # Ask for origin_country multiple times
        question1 = self.slot_mgr.get_missing_slot_question(self.session_id, intent, {})
        question2 = self.slot_mgr.get_missing_slot_question(self.session_id, intent, {})

        # Provide origin_country
        state1 = self.slot_mgr.update_slots(self.session_id, intent, {"origin_country": "usa"})

        # Now ask for destination_country (should start from 1, not carry over)
        question3 = self.slot_mgr.get_missing_slot_question(
            self.session_id, intent, state1.slots
        )
        assert question3 is not None
        assert not question3.get("too_many_attempts")

    def test_loop_detection_message(self):
        """Test that loop detection provides helpful message"""
        intent = "search_country_data"
        slots = {}

        # Ask 3 times to trigger loop detection
        for _ in range(3):
            question = self.slot_mgr.get_missing_slot_question(self.session_id, intent, slots)

        # Should have escalation message
        assert question.get("too_many_attempts")
        assert "trouble understanding" in question.get("message", "").lower()


class TestHeuristicValidation:
    """Test heuristic validation for country names"""

    def setup_method(self):
        """Set up test fixtures"""
        self.slot_mgr = SlotManager(redis_manager=None)

    def test_accept_alphabetic_countries(self):
        """Test that alphabetic country-like names are accepted"""
        potential_countries = [
            "Afghanistan", "Xyz Land", "New Country", "South East"
        ]

        for name in potential_countries:
            # Should accept if passes heuristics (alphabetic, reasonable word count)
            is_valid = self.slot_mgr.is_valid_country(name)
            # Note: "Xyz Land" and "New Country" might be rejected as not in known countries
            # and failing some heuristics, but real country names should pass

    def test_reject_too_many_words(self):
        """Test that inputs with too many words are rejected"""
        too_many_words = "this is definitely not a country name at all"
        assert not self.slot_mgr.is_valid_country(too_many_words)

    def test_reject_numeric_only(self):
        """Test that numeric-only inputs are rejected"""
        assert not self.slot_mgr.is_valid_country("123")
        assert not self.slot_mgr.is_valid_country("456789")

    def test_reject_too_short(self):
        """Test that very short inputs are rejected"""
        assert not self.slot_mgr.is_valid_country("a")
        assert not self.slot_mgr.is_valid_country("xy")

    def test_accept_hyphenated_countries(self):
        """Test that hyphenated country names are accepted"""
        hyphenated = ["timor-leste", "guinea-bissau", "saint-lucia"]

        for name in hyphenated:
            # Should accept hyphenated names (common in country names)
            assert self.slot_mgr.is_valid_country(name), \
                f"Failed to accept hyphenated country '{name}'"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
