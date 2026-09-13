"""Response models for the spoken screen guide."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.enums import GuideLanguage, GuideScreen


class GuideSectionResponse(BaseModel):
    """One paragraph: a heading, what is said, and where its speech is."""

    index: int = Field(ge=0)
    heading: str
    text: str = Field(description="Exactly what the voice says, for reading along.")
    audio_path: str = Field(
        description=(
            "Path of this paragraph's MP3 below the API root. It carries a version that "
            "changes whenever the words or the voice do, so it may be cached indefinitely."
        )
    )


class GuideResponse(BaseModel):
    """The guide for one screen in one language."""

    screen: GuideScreen
    language: GuideLanguage
    title: str
    sections: list[GuideSectionResponse]
    voice_available: bool = Field(
        description=(
            "Whether this deployment can generate speech. When false the transcript is "
            "still complete; only paragraphs generated earlier will play."
        )
    )
    voice: str = Field(description="The speech engine and voice, named rather than implied.")
