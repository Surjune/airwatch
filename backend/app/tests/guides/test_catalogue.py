"""Tests for loading the voice guide's scripts."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.enums import GuideLanguage, GuideScreen
from app.guides import catalogue
from app.guides.catalogue import script_for, spoken_form


class TestEveryScript:
    @pytest.mark.parametrize("language", list(GuideLanguage))
    @pytest.mark.parametrize("screen", list(GuideScreen))
    def test_exists_with_words_in_every_paragraph(
        self, screen: GuideScreen, language: GuideLanguage
    ) -> None:
        script = script_for(screen, language)

        assert script.title
        assert script.sections
        assert all(section.heading and section.text for section in script.sections)

    @pytest.mark.parametrize("screen", list(GuideScreen))
    def test_says_as_much_in_hindi_and_tamil_as_in_english(self, screen: GuideScreen) -> None:
        # A translation that dropped a paragraph would leave a listener in one
        # language without an instruction the others hear.
        counts = {len(script_for(screen, language).sections) for language in GuideLanguage}
        assert len(counts) == 1

    def test_a_multi_line_paragraph_reads_as_one(self) -> None:
        text = script_for(GuideScreen.MAP, GuideLanguage.TAMIL).sections[0].text

        assert "\n" not in text
        assert "  " not in text


class TestSpokenForms:
    @pytest.mark.parametrize("language", [GuideLanguage.HINDI, GuideLanguage.TAMIL])
    def test_technical_terms_are_spoken_in_the_listeners_script(
        self, language: GuideLanguage
    ) -> None:
        section = script_for(GuideScreen.CITIZEN, language).sections[3]

        # Shown as the interface writes it, so the listener can match the label...
        assert "PM2.5" in section.text
        # ...and said the way people say it, not left to the voice to guess.
        assert "PM2.5" not in section.speech
        assert "PM10" not in section.speech

    def test_interface_labels_stay_as_they_appear_on_screen(self) -> None:
        text = script_for(GuideScreen.OVERVIEW, GuideLanguage.HINDI).sections[3].text

        assert "Open the map" in text

    def test_longer_terms_are_replaced_before_the_terms_inside_them(self) -> None:
        replacements = {"PM": "particulate", "PM2.5": "fine dust"}

        assert spoken_form("PM2.5 and PM", replacements) == "fine dust and particulate"


class TestLoadingRefuses:
    @pytest.fixture
    def script_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        monkeypatch.setattr(catalogue, "SCRIPT_DIR", tmp_path)
        return tmp_path

    @staticmethod
    def _screens(skip: GuideScreen | None = None) -> str:
        return "".join(
            f'[screens.{screen.value}]\ntitle = "T"\n'
            f'[[screens.{screen.value}.sections]]\nheading = "H"\ntext = "Words."\n'
            for screen in GuideScreen
            if screen is not skip
        )

    def test_a_language_missing_a_screen(self, script_dir: Path) -> None:
        body = 'language = "en"\n' + self._screens(skip=GuideScreen.ALERTS)
        (script_dir / "en.toml").write_text(body, encoding="utf-8")

        with pytest.raises(ValueError, match="alerts"):
            catalogue._load(GuideLanguage.ENGLISH)

    def test_a_file_declaring_another_language(self, script_dir: Path) -> None:
        (script_dir / "hi.toml").write_text('language = "ta"\n' + self._screens(), encoding="utf-8")

        with pytest.raises(ValueError, match="declares language"):
            catalogue._load(GuideLanguage.HINDI)

    def test_an_unknown_key(self, script_dir: Path) -> None:
        body = 'language = "en"\nvoice = "someone"\n' + self._screens()
        (script_dir / "en.toml").write_text(body, encoding="utf-8")

        with pytest.raises(ValueError, match="voice"):
            catalogue._load(GuideLanguage.ENGLISH)
