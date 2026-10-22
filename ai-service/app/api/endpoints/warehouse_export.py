"""Source-owned, snapshot-consistent, metadata-only warehouse exports.

The warehouse never receives database credentials. This endpoint reads only AI's
own usage table and excludes keys, raw errors and all prompt/response content.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import datetime,timedelta,timezone
from uuid import uuid4

from fastapi import APIRouter,HTTPException,Query,Request
from fastapi.responses import StreamingResponse

from app.core.config import get_settings
from app.core.database import get_ai_conn

router=APIRouter(prefix='/internal/warehouse',tags=['Internal warehouse export'])


def usage_payload(row):
    """Legacy logging has no explicit missing-usage flag; never infer zero cost."""
    measured=bool(row['success']) and (row['prompt_tokens']>0 or row['completion_tokens']>0)
    code=row.get('error_code')
    known={'auth','context_length','empty_completion','rate_limited','unexpected','invalid_response'}
    error_class=code if code in known else ('provider_error' if code and re.fullmatch(r'provider_(?:[1-5][0-9]{2}|err)',code) else ('unclassified' if code else None))
    return {'usage_id':row['id'],'created_at':row['created_at'].astimezone(timezone.utc).isoformat(),
            'task_code':row['task_code'],'provider_code':row['provider_code'],'model_name':row['model_name'],
            'request_id':row['request_id'],'prompt_tokens':row['prompt_tokens'] if measured else None,
            'completion_tokens':row['completion_tokens'] if measured else None,
            'latency_ms':row['latency_ms'] if row['latency_ms'] and row['latency_ms']>0 else None,
            'success':row['success'],'fallback_used':row['fallback_used'],'attempt_no':row['attempt_no'],
            'usage_status':'reported' if measured else 'unknown','error_class':error_class}


def encoded(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()+b'\n'


async def snapshot_lines(since,until,max_records):
    export_id=uuid4().hex
    # All count/cursor reads share one MVCC snapshot. A serial ID is not used as
    # a commit watermark; repeated overlapping exports reconcile by immutable ID.
    async with get_ai_conn() as conn:
        async with conn.transaction(isolation='repeatable_read',readonly=True):
            count=await conn.fetchval('SELECT COUNT(*) FROM llm_usage_log WHERE created_at >= $1 AND created_at < $2',since,until,timeout=30)
            yield encoded({'kind':'header','schema_version':1,'source':'ai.llm_attempt','export_id':export_id,
                           'since':since.isoformat(),'until':until.isoformat(),'record_count':count,
                           'complete':count<=max_records})
            if count>max_records:
                return
            query='''SELECT id,created_at,task_code,provider_code,model_name,request_id,
                            prompt_tokens,completion_tokens,latency_ms,success,fallback_used,attempt_no,error_code
                     FROM llm_usage_log WHERE created_at >= $1 AND created_at < $2 ORDER BY id'''
            digest=hashlib.sha256()
            emitted=0
            async for row in conn.cursor(query,since,until,prefetch=100,timeout=30):
                payload=usage_payload(row)
                digest.update(encoded(payload))
                emitted+=1
                yield encoded({'kind':'row','payload':payload})
            yield encoded({'kind':'trailer','export_id':export_id,'record_count':emitted,
                           'payload_sha256':digest.hexdigest(),'complete':emitted==count})


@router.get('/llm-attempts')
async def export_llm_attempts(request:Request,days:int=Query(default=7,ge=1,le=60),
                              max_records:int=Query(default=10000,ge=1,le=10000)):
    expected=get_settings().ai_service_secret
    supplied=request.headers.get('X-AI-Secret','')
    if not expected or not hmac.compare_digest(expected,supplied):
        raise HTTPException(status_code=403,detail='Internal authentication required')
    until=datetime.now(timezone.utc)
    return StreamingResponse(snapshot_lines(until-timedelta(days=days),until,max_records),
                             media_type='application/x-ndjson',headers={'Cache-Control':'no-store'})
