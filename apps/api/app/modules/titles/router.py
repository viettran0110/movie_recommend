from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.errors import ERROR_RESPONSES, NOT_FOUND_RESPONSES
from app.modules.titles import service
from app.modules.titles.models import MediaType
from app.modules.titles.schemas import Genre, Page, TitleCredits, TitleDetail, TitleSummary

router = APIRouter(tags=["titles"], responses=ERROR_RESPONSES)

Session = Annotated[AsyncSession, Depends(get_session)]
# Bounded so an out-of-range id is a 422, not a database overflow.
TitleId = Annotated[int, Path(ge=1, le=2**63 - 1)]
MediaTypeFilter = Annotated[MediaType | None, Query(description="Defaults to all media types")]
PageNumber = Annotated[int, Query(ge=1, le=10_000)]
PageSize = Annotated[int, Query(ge=1, le=100)]


@router.get("/titles/{title_id}", responses=NOT_FOUND_RESPONSES)
async def get_title(title_id: TitleId, session: Session) -> TitleDetail:
    return await service.get_title(session, title_id)


@router.get("/titles/{title_id}/credits", responses=NOT_FOUND_RESPONSES)
async def get_title_credits(title_id: TitleId, session: Session) -> TitleCredits:
    return await service.get_title_credits(session, title_id)


@router.get("/genres")
async def list_genres(session: Session, media_type: MediaTypeFilter = None) -> list[Genre]:
    return await service.list_genres(session, media_type)


@router.get("/genres/{slug}/titles", responses=NOT_FOUND_RESPONSES)
async def list_genre_titles(
    slug: Annotated[str, Path(max_length=64)],
    session: Session,
    media_type: MediaTypeFilter = None,
    page: PageNumber = 1,
    page_size: PageSize = 20,
) -> Page[TitleSummary]:
    return await service.list_genre_titles(
        session, slug, media_type, page=page, page_size=page_size
    )
