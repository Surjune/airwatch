"""The spoken guide to each screen.

Routes parse the request, call exactly one service, and shape the response.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.constants import VOICE_GUIDE_CACHE_MAX_AGE_SECONDS, VOICE_GUIDE_VERSION_LENGTH
from app.core.enums import GuideLanguage, GuideScreen
from app.repositories.session import get_db_session
from app.schemas.guide import GuideResponse, GuideSectionResponse
from app.services import voice_guide_service

router = APIRouter(prefix="/guide", tags=["guide"])

#: Highest paragraph index accepted in a path, well above any script's length.
_MAX_SECTION_INDEX = 50

Language = Annotated[
    GuideLanguage,
    Query(description="ISO 639-1 code: en, hi (Hindi) or ta (Tamil)."),
]


@router.get(
    "/{screen}", response_model=GuideResponse, summary="How a screen works, to read or hear"
)
def screen_guide(
    settings: Annotated[Settings, Depends(get_settings)],
    screen: GuideScreen,
    language: Language = GuideLanguage.ENGLISH,
) -> GuideResponse:
    """The transcript of a screen's spoken guide, with the path to each paragraph's audio."""
    view = voice_guide_service.guide(settings, screen, language)
    return GuideResponse(
        screen=view.screen,
        language=view.language,
        title=view.title,
        sections=[
            GuideSectionResponse(
                index=section.index,
                heading=section.heading,
                text=section.text,
                audio_path=(
                    f"/guide/{view.screen.value}/sections/{section.index}/audio"
                    f"?language={view.language.value}&v={section.audio_version}"
                ),
            )
            for section in view.sections
        ],
        voice_available=view.voice_available,
        voice=view.voice,
    )


@router.get(
    "/{screen}/sections/{index}/audio",
    summary="One paragraph of a screen's guide, spoken",
    response_class=Response,
    responses={200: {"content": {"audio/mpeg": {}}, "description": "The paragraph, as MP3."}},
)
async def section_audio(
    session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    screen: GuideScreen,
    index: Annotated[int, Path(ge=0, le=_MAX_SECTION_INDEX)],
    language: Language = GuideLanguage.ENGLISH,
    v: Annotated[
        str | None,
        Query(
            pattern=f"^[0-9a-f]{{{VOICE_GUIDE_VERSION_LENGTH}}}$",
            description="The version from the transcript; a current one is cached for a year.",
        ),
    ] = None,
) -> Response:
    """The paragraph's speech, generated on first request and stored after."""
    clip = await voice_guide_service.section_audio(session, settings, screen, language, index)
    # A URL naming the current version identifies these exact words, so it can be
    # kept forever. Any other request might be for words since corrected.
    cache_control = (
        f"public, max-age={VOICE_GUIDE_CACHE_MAX_AGE_SECONDS}, immutable"
        if v == clip.version
        else "no-cache"
    )
    return Response(
        content=clip.audio,
        media_type=clip.media_type,
        headers={"Cache-Control": cache_control},
    )
