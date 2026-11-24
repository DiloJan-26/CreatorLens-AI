"""Optional quota-bounded official metadata enrichment. No scraping, media or AI calls."""
import json
from time import monotonic
from datetime import datetime, UTC
from urllib.parse import urlsplit, parse_qs
import httpx
from app.core.access import require_principal, owned_project
from app.core.request_limits import client, enforce_rate
from app.db.session import database_session
from app.services.account_usage import latest_reservation

QUOTA_SCRIPT="local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],172800) end; return n"

def enrich(project_id, canonical_url, info, settings):
    if not getattr(settings,'youtube_metadata_enrichment_enabled',False):return info,{}
    if settings.provider_emergency_stop or not settings.youtube_api_key or not settings.redis_url:return info,{}
    principal=require_principal()
    with database_session() as session:
        owned_project(session,project_id,principal)
        reservation=latest_reservation(session,project_id)
        if not reservation or reservation.user_id!=principal.user_id or reservation.state not in {'reserved','processing'}:return info,{}
    from app.extraction.bounded_provider import public_count
    video_id=parse_qs(urlsplit(canonical_url).query).get('v',[None])[0]
    if not video_id:return info,{}
    original=dict(info); provenance={}
    def call(endpoint, params):
        # Conservative local cap; count each attempted list request, including failures.
        enforce_rate(settings,principal.user_id,'paid')
        n=client(settings.redis_url).eval(QUOTA_SCRIPT,1,'youtube-enrichment:'+datetime.now(UTC).strftime('%Y-%m-%d'))
        if n>settings.youtube_enrichment_daily_units:raise ValueError('Enrichment daily quota reached.')
        started=monotonic()
        with httpx.Client(timeout=settings.extraction_timeout_seconds,follow_redirects=False,trust_env=False,
                          transport=httpx.HTTPTransport(retries=0)) as http:
            with http.stream('GET','https://www.googleapis.com/youtube/v3/'+endpoint,params={**params,'key':settings.youtube_api_key}) as response:
                if response.status_code!=200:raise ValueError('Official metadata unavailable.')
                body=bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body)>settings.extraction_max_response_bytes or monotonic()-started>settings.extraction_timeout_seconds:raise ValueError('Enrichment response too large.')
                result=json.loads(body)
                return result.get('items',[]) if isinstance(result,dict) else []
    try:
        records=call('videos',dict(part='snippet,statistics',id=video_id))
        row=next((r for r in records if r.get('id')==video_id),None)
        if not row:return info,{}
        observed=datetime.now(UTC).isoformat();stats=row.get('statistics') or {};snippet=row.get('snippet') or {}
        candidate={key:public_count(stats.get(field)) for key,field in [('view_count','viewCount'),('like_count','likeCount'),('comment_count','commentCount')]}
        known={k for k,v in candidate.items() if v is not None}; existing={k for k in candidate if info.get(k) is not None}
        # Replace the count group only when the official snapshot preserves all known fields and fills a gap.
        if existing<known:
            info={**info,**candidate}
            for key,value in candidate.items():
                if value is not None:provenance[key]=dict(provider='youtube_data_api',observed_at=observed,source_id=video_id)
            provenance['previous_count_snapshot']={k:original.get(k) for k in candidate}
        if not info.get('upload_date') and snippet.get('publishedAt'):
            info={**info,'upload_date':snippet['publishedAt']}
            provenance['upload_date']=dict(provider='youtube_data_api',observed_at=observed,source_id=video_id)
        if info.get('subscriber_count') is None and snippet.get('channelId'):
            channels=call('channels',dict(part='statistics',id=snippet['channelId']))
            channel=next((c for c in channels if c.get('id')==snippet['channelId']),None)
            counts=(channel or {}).get('statistics') or {}
            count=public_count(counts.get('subscriberCount')) if not counts.get('hiddenSubscriberCount') else None
            if count is not None:
                info={**info,'subscriber_count':count}
                provenance['subscriber_count']=dict(provider='youtube_data_api',observed_at=datetime.now(UTC).isoformat(),source_id=snippet['channelId'],
                    limitation='Current publicly reported subscriber count may be rounded; not historical creator size.')
    except Exception:
        # Optional enrichment cannot discard a successful primary snapshot; never log credentials/URL query.
        provenance['enrichment_status']='partial_or_unavailable'
    return info,provenance
