"""
Comprehensive tests for the KDLanguage translation system.
Tests all aspects of the language manager including translations, formatting, and edge cases.
"""

import os
import sys

try:
    from kemonodownloader.kd_language import KDLanguage, language_manager, translate
except ImportError:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))
    from kemonodownloader.kd_language import KDLanguage, language_manager, translate


class TestKDLanguageClass:
    """Tests for the KDLanguage class itself."""

    def test_class_instantiation(self):
        """Test that KDLanguage can be instantiated."""
        manager = KDLanguage()
        assert manager is not None
        assert hasattr(manager, "current_language")
        assert hasattr(manager, "translations")

    def test_translations_dict_exists(self):
        """Test that translations dictionary exists and is populated."""
        manager = KDLanguage()
        assert isinstance(manager.translations, dict)
        assert len(manager.translations) > 0

    def test_default_language(self):
        """Test that default language is English."""
        manager = KDLanguage()
        assert manager.current_language == "english"


class TestLanguageSwitching:
    """Tests for language switching functionality."""

    def setup_method(self):
        """Store original language before each test."""
        self.original = language_manager.current_language

    def teardown_method(self):
        """Restore original language after each test."""
        language_manager.set_language(self.original)

    def test_switch_to_english(self):
        """Test switching to English."""
        language_manager.set_language("english")
        assert language_manager.current_language == "english"

    def test_switch_to_japanese(self):
        """Test switching to Japanese."""
        language_manager.set_language("japanese")
        assert language_manager.current_language == "japanese"

    def test_switch_to_korean(self):
        """Test switching to Korean."""
        language_manager.set_language("korean")
        assert language_manager.current_language == "korean"

    def test_switch_to_chinese_simplified(self):
        """Test switching to Simplified Chinese."""
        language_manager.set_language("chinese-simplified")
        assert language_manager.current_language == "chinese-simplified"

    def test_switch_multiple_times(self):
        """Test switching languages multiple times."""
        languages = ["english", "japanese", "korean", "chinese-simplified", "english"]

        for lang in languages:
            language_manager.set_language(lang)
            assert language_manager.current_language == lang


class TestTranslationOutput:
    """Tests for translation output in different languages."""

    def setup_method(self):
        """Store original language before each test."""
        self.original = language_manager.current_language

    def teardown_method(self):
        """Restore original language after each test."""
        language_manager.set_language(self.original)

    def test_english_translation(self):
        """Test English translation output."""
        language_manager.set_language("english")
        result = translate("added_to_queue")
        assert result == "Added to queue"

    def test_japanese_translation(self):
        """Test Japanese translation output."""
        language_manager.set_language("japanese")
        result = translate("added_to_queue")
        assert result == "キューに追加されました"

    def test_korean_translation(self):
        """Test Korean translation output."""
        language_manager.set_language("korean")
        result = translate("added_to_queue")
        assert result == "대기열에 추가됨"

    def test_chinese_simplified_translation(self):
        """Test Simplified Chinese translation output."""
        language_manager.set_language("chinese-simplified")
        result = translate("added_to_queue")
        assert result == "已添加到队列"


class TestTranslationFormatting:
    """Tests for translation string formatting with arguments."""

    def setup_method(self):
        """Store original language before each test."""
        self.original = language_manager.current_language
        language_manager.set_language("english")

    def teardown_method(self):
        """Restore original language after each test."""
        language_manager.set_language(self.original)

    def test_single_argument_formatting(self):
        """Test translation with single format argument."""
        result = translate("total_posts", 42)
        assert result == "Total posts: 42"

    def test_multiple_argument_formatting(self):
        """Test translation with multiple format arguments."""
        result = translate("parsed_url_service_creator", "fanbox", "12345")
        assert "fanbox" in result
        assert "12345" in result

    def test_string_argument_formatting(self):
        """Test translation with string arguments."""
        result = translate("checking_creator_with_url", "https://example.com")
        assert "https://example.com" in result

    def test_zero_argument(self):
        """Test translation with zero as argument."""
        result = translate("total_posts", 0)
        assert "0" in result


class TestMissingTranslations:
    """Tests for handling missing translation keys."""

    def setup_method(self):
        """Store original language before each test."""
        self.original = language_manager.current_language
        language_manager.set_language("english")

    def teardown_method(self):
        """Restore original language after each test."""
        language_manager.set_language(self.original)

    def test_missing_key_returns_key(self):
        """Test that missing key returns the key itself."""
        result = translate("this_key_definitely_does_not_exist_123456789")
        assert result == "this_key_definitely_does_not_exist_123456789"

    def test_missing_key_with_arguments(self):
        """Test missing key with format arguments."""
        result = translate("nonexistent_key_with_args", "arg1", "arg2")
        # Should return the key since it doesn't exist
        assert "nonexistent_key_with_args" in result


class TestAvailableLanguages:
    """Tests for getting available languages."""

    def test_get_available_languages(self):
        """Test getting list of available languages."""
        languages = language_manager.get_available_languages()

        assert isinstance(languages, list)
        assert len(languages) == 4

    def test_available_languages_contains_english(self):
        """Test that English is in available languages."""
        languages = language_manager.get_available_languages()
        assert "english" in languages

    def test_available_languages_contains_japanese(self):
        """Test that Japanese is in available languages."""
        languages = language_manager.get_available_languages()
        assert "japanese" in languages

    def test_available_languages_contains_korean(self):
        """Test that Korean is in available languages."""
        languages = language_manager.get_available_languages()
        assert "korean" in languages

    def test_available_languages_contains_chinese(self):
        """Test that Simplified Chinese is in available languages."""
        languages = language_manager.get_available_languages()
        assert "chinese-simplified" in languages


class TestGetLanguageMethod:
    """Tests for the get_language method."""

    def setup_method(self):
        """Store original language before each test."""
        self.original = language_manager.current_language

    def teardown_method(self):
        """Restore original language after each test."""
        language_manager.set_language(self.original)

    def test_get_language_returns_current(self):
        """Test that get_language returns current language."""
        language_manager.set_language("japanese")
        assert language_manager.get_language() == "japanese"

    def test_get_language_after_switch(self):
        """Test get_language after switching languages."""
        language_manager.set_language("english")
        assert language_manager.get_language() == "english"

        language_manager.set_language("korean")
        assert language_manager.get_language() == "korean"


class TestCommonTranslationKeys:
    """Tests to verify common UI translation keys exist."""

    def setup_method(self):
        """Store original language before each test."""
        self.original = language_manager.current_language
        language_manager.set_language("english")

    def teardown_method(self):
        """Restore original language after each test."""
        language_manager.set_language(self.original)

    def test_ui_button_keys(self):
        """Test that UI button translation keys exist."""
        keys = ["browse", "apply_changes", "reset_to_defaults"]

        for key in keys:
            result = translate(key)
            assert result != key, f"Translation key '{key}' is missing"

    def test_settings_label_keys(self):
        """Test that settings label translation keys exist."""
        keys = ["folder_settings", "download_settings", "language_settings"]

        for key in keys:
            result = translate(key)
            assert result != key, f"Translation key '{key}' is missing"

    def test_error_message_keys(self):
        """Test that error message translation keys exist."""
        keys = ["error", "invalid_url_format"]

        for key in keys:
            result = translate(key)
            assert result != key, f"Translation key '{key}' is missing"

    def test_status_keys(self):
        """Test that status message translation keys exist."""
        keys = ["added_to_queue", "enabled", "disabled"]

        for key in keys:
            result = translate(key)
            assert result != key, f"Translation key '{key}' is missing"

    def test_help_thumbnail_favorites_fast_mode_keys(self):
        """Help sections added in 5.13.0 exist in all languages."""
        keys = [
            "help_thumbnail_title",
            "help_thumbnail_text",
            "help_favorites_title",
            "help_favorites_text",
            "help_fast_mode_title",
            "help_fast_mode_text",
            "favorites_no_api_key",
        ]
        for key in keys:
            for lang in language_manager.get_available_languages():
                language_manager.set_language(lang)
                result = translate(key)
                assert result != key, f"Translation key '{key}' is missing in {lang}"


class TestTranslationConsistency:
    """Tests for translation consistency across languages."""

    def setup_method(self):
        """Store original language before each test."""
        self.original = language_manager.current_language

    def teardown_method(self):
        """Restore original language after each test."""
        language_manager.set_language(self.original)

    def test_key_exists_in_all_languages(self):
        """Test that a common key exists in all languages."""
        key = "added_to_queue"
        languages = language_manager.get_available_languages()

        for lang in languages:
            language_manager.set_language(lang)
            result = translate(key)
            assert result != key, f"Key '{key}' missing in {lang}"

    def test_different_languages_give_different_results(self):
        """Test that different languages produce different translations."""
        key = "added_to_queue"

        language_manager.set_language("english")
        english_result = translate(key)

        language_manager.set_language("japanese")
        japanese_result = translate(key)

        assert english_result != japanese_result

    def test_format_placeholders_work_in_all_languages(self):
        """Test that format placeholders work in all languages."""
        key = "total_posts"
        value = 100
        languages = language_manager.get_available_languages()

        for lang in languages:
            language_manager.set_language(lang)
            result = translate(key, value)
            assert "100" in result, f"Format placeholder failed in {lang}"


class TestLanguageManagerSingleton:
    """Tests for the language_manager singleton."""

    def test_language_manager_is_kdlanguage_instance(self):
        """Test that language_manager is a KDLanguage instance."""
        assert isinstance(language_manager, KDLanguage)

    def test_translate_function_uses_singleton(self):
        """Test that translate function uses the singleton."""
        original = language_manager.current_language

        try:
            language_manager.set_language("japanese")
            result = translate("added_to_queue")

            # Should be Japanese translation
            assert result == "キューに追加されました"
        finally:
            language_manager.set_language(original)


class TestKDLanguageEdgeCases:
    """Test edge cases and error handling in KDLanguage."""

    def setup_method(self):
        """Store original language before each test."""
        self.original = language_manager.current_language
        language_manager.set_language("english")

    def teardown_method(self):
        """Restore original language after each test."""
        language_manager.set_language(self.original)

    def test_get_text_fallback_to_english(self):
        """Test fallback to English when a language is missing for a key."""
        # Use a key that we know exists (e.g. 'added_to_queue')
        # We need to manually inject a missing language for this test to be reliable
        # or use a language that is not in the translations for that key.
        # But all common keys have all 4 languages.
        # Let's mock a entry.
        original_translations = language_manager.translations.copy()
        try:
            language_manager.translations["test_fallback"] = {
                "english": "Fallback success"
            }
            language_manager.set_language("japanese")
            # Japanese is missing for 'test_fallback', should return English
            assert language_manager.get_text("test_fallback") == "Fallback success"
        finally:
            language_manager.translations = original_translations

    def test_get_text_format_error(self):
        """Test handling of formatting errors (e.g. too few arguments)."""
        # Create a new instance to ensure coverage is tracked for this instance
        manager = KDLanguage()
        # Mock a translation with a named placeholder to trigger KeyError
        manager.translations["test_error"] = {"english": "{missing_key}"}
        # Providing only positional arguments will cause a KeyError for {missing_key}
        result = manager.get_text("test_error", "english", "some_value")
        assert result == "{missing_key}"

    def test_set_language_invalid(self):
        """Test set_language with an invalid language code."""
        assert language_manager.set_language("invalid-lang") is False

    def test_get_language_name_basic(self):
        """Test get_language_name method."""
        # Current language is 'english' (from setup_method)
        # get_language_name() calls get_text('english')
        # Which should return 'English'
        assert language_manager.get_language_name() == "English"
        assert language_manager.get_language_name("japanese") == "Japanese"
