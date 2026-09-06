"""Source-bound collection browsing and media inspection."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.store import saved_sources
from app.catalog import catalog
from app.registry import identities
from app.pagination import encode, decode
from app.verification import revision, record
from yt_dlp.extractor import gen_extractor_classes

router = APIRouter()


class SourceURL(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    source_id: str | None = Field(default=None, max_length=150)


class CollectionRequest(SourceURL):
    cursor: str | None = Field(default=None, max_length=2000)
    limit: int = Field(default=20, ge=1, le=50)


def select_source(url, source_id=None):
    from app.connectors import public_url
    try:
        public_url(url)
    except (ValueError, TypeError):
        raise HTTPException(400, 'Utilisez une URL HTTP(S) publique sur un port standard.')
    candidates = [cls for cls in gen_extractor_classes() if cls.ie_key() != 'Generic' and cls.suitable(url)]
    mapping = identities()
    for source in saved_sources():
        if not source['enabled'] or (source_id is not None and source['id'] != source_id):
            continue
        extractor = source['connector'].get('extractor')
        if not extractor or extractor not in mapping:
            continue
        matched = next((cls for cls in candidates if cls.ie_key() == extractor), None)
        if not matched:
            matched = next((cls for cls in candidates if mapping[cls.ie_key()]['platform_id'] == mapping[extractor]['platform_id']), None)
        if matched:
            return source, matched.ie_key()
    raise HTTPException(400, 'Ajoutez et activez une source correspondant à cette URL.')


@router.post('/api/collections')
async def collection(body: CollectionRequest):
    from app.main import run_worker, searches
    source, extractor_key = select_source(body.url, body.source_id)
    context = ['collection', source['id'], body.url, revision(source['connector']), body.limit]
    offset = decode(body.cursor, context)
    try:
        async with searches:
            result = await run_worker({'mode': 'collection', 'url': body.url, 'connector': source['connector'],
                                       'extractor_key': extractor_key, 'offset': offset, 'limit': body.limit})
        record(source['connector'], body.url, 'verified' if result['items'] else 'empty', len(result['items']), feature='collections')
        return {**result, 'source_id': source['id'], 'next_cursor': encode(offset+body.limit, context) if result.get('has_more') else None}
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))


@router.post('/api/media/resolve')
async def resolve(body: SourceURL):
    from app.main import run_worker, searches
    source, extractor_key = select_source(body.url, body.source_id)
    try:
        async with searches:
            result = await run_worker({'mode': 'resolve', 'url': body.url, 'connector': source['connector'], 'extractor_key': extractor_key})
        record(source['connector'], body.url, 'verified', feature='resolve')
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))
    # Never expose signed upstream URLs or provider headers in the metadata API.
    return {'video': result['video'], 'source_id': source['id'], 'is_live': result['is_live'],
            'formats': [{k: v for k, v in item.items() if k not in ('url', 'manifest_url', 'http_headers')} for item in result['formats']],
            'subtitle_languages': list(result['subtitles'])}
