"""The voice guide's scripts, loaded once from ``scripts/<language>.toml``.

The words live in TOML rather than in Python because they are prose that a
translator should be able to correct without touching code, and a Tamil sentence
cannot be wrapped at a hundred columns without breaking it mid-word.

Two kinds of text come out of a script:

* **What is read** -- shown on screen as the transcript, keeping the interface's
  own English labels ("Open the map") so a listener can find the button being
  described.
* **What is spoken** -- the same text with a few technical terms spelled the way
  they are said. A Hindi voice left to read "PM2.5" may say "pm two dot five" in
  a Hindi accent or skip the decimal; the script's ``[spoken]`` table says
  "पीएम टू पॉइंट फाइव" instead, exactly as people in Delhi say it.

Every screen must exist in every language, checked at load: a guide that falls
silent on one screen in Tamil would read as that screen having nothing to say.

Leaf module: imports only ``core``.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.constants import SARVAM_TTS_MAX_CHARACTERS
from app.core.enums import GuideLanguage, GuideScreen

#: Directory holding one script file per language.
SCRIPT_DIR = Path(__file__).parent / "scripts"

#: Runs of whitespace, including the line breaks of a TOML multi-line string.
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class GuideSection:
    """One paragraph of a guide: read as ``text``, spoken as ``speech``."""

    heading: str
    text: str
    speech: str


@dataclass(frozen=True, slots=True)
class GuideScript:
    """Everything the guide says about one screen, in one language."""

    screen: GuideScreen
    language: GuideLanguage
    title: str
    sections: tuple[GuideSection, ...]


class _SectionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    heading: str = Field(min_length=1)
    text: str = Field(min_length=1)

    @field_validator("heading", "text")
    @classmethod
    def _collapse(cls, value: str) -> str:
        """Join the lines of a multi-line TOML string into one paragraph."""
        return _WHITESPACE.sub(" ", value).strip()


class _ScreenModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    sections: list[_SectionModel] = Field(min_length=1)


class _ScriptFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: GuideLanguage
    spoken: dict[str, str] = Field(default_factory=dict)
    screens: dict[GuideScreen, _ScreenModel]

    @field_validator("screens")
    @classmethod
    def _every_screen(
        cls, screens: dict[GuideScreen, _ScreenModel]
    ) -> dict[GuideScreen, _ScreenModel]:
        missing = [screen.value for screen in GuideScreen if screen not in screens]
        if missing:
            raise ValueError(f"no guide for screens: {', '.join(missing)}")
        return screens


def spoken_form(text: str, replacements: dict[str, str]) -> str:
    """The text as it should be said, with each listed term replaced.

    Longer terms are replaced first, so a term containing a shorter one is not
    half-rewritten by it.
    """
    for term in sorted(replacements, key=len, reverse=True):
        text = text.replace(term, replacements[term])
    return text


def _load(language: GuideLanguage) -> dict[GuideScreen, GuideScript]:
    """Read, validate and prepare one language's scripts.

    Raises:
        ValueError: The file is missing a screen, has an unknown key, declares a
            different language, or has a paragraph too long to synthesise.
    """
    path = SCRIPT_DIR / f"{language.value}.toml"
    parsed = _ScriptFile.model_validate(tomllib.loads(path.read_text(encoding="utf-8")))
    if parsed.language is not language:
        raise ValueError(f"{path.name} declares language {parsed.language.value!r}")

    scripts: dict[GuideScreen, GuideScript] = {}
    for screen, model in parsed.screens.items():
        sections: list[GuideSection] = []
        for section in model.sections:
            speech = spoken_form(section.text, parsed.spoken)
            if len(speech) > SARVAM_TTS_MAX_CHARACTERS:
                raise ValueError(
                    f"{path.name}: a '{screen.value}' paragraph is {len(speech)} characters, "
                    f"over the {SARVAM_TTS_MAX_CHARACTERS} one synthesis request accepts"
                )
            sections.append(GuideSection(heading=section.heading, text=section.text, speech=speech))
        scripts[screen] = GuideScript(
            screen=screen, language=language, title=model.title, sections=tuple(sections)
        )
    return scripts


@lru_cache(maxsize=len(GuideLanguage))
def _scripts(language: GuideLanguage) -> dict[GuideScreen, GuideScript]:
    return _load(language)


def script_for(screen: GuideScreen, language: GuideLanguage) -> GuideScript:
    """The guide for a screen in a language. Every pair exists, checked at load."""
    return _scripts(language)[screen]
