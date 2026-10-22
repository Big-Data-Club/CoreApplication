"""Metadata-only export contracts; no production database or real learner rows."""
import hashlib
import json
from contextlib import asynccontextmanager
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock,Mock,patch

import pytest
from fastapi import HTTPException

from app.api.endpoints import warehouse_export as export


def usage_row(**overrides):
    row={'id':1,'created_at':datetime(2026,1,1,tzinfo=timezone.utc),'task_code':'unit-task',
         'provider_code':'unit-provider','model_name':'unit-model','request_id':None,
         'prompt_tokens':10,'completion_tokens':5,'latency_ms':50,'success':True,
         'fallback_used':False,'attempt_no':1,'api_key_id':'excluded','error_message':'excluded'}
    return {**row,**overrides}


def test_private_fields_and_unknown_usage_are_not_exported_as_known_zero():
    payload=export.usage_payload(usage_row(success=False,prompt_tokens=0,completion_tokens=0))
    assert payload['usage_status']=='unknown'
    assert payload['prompt_tokens'] is None and payload['completion_tokens'] is None
    assert 'api_key_id' not in payload and 'error_message' not in payload


@pytest.mark.asyncio
async def test_count_and_rows_share_readonly_snapshot_and_verified_trailer():
    @asynccontextmanager
    async def transaction(**kwargs):
        assert kwargs=={'isolation':'repeatable_read','readonly':True}
        yield
    async def cursor(*args,**kwargs):
        yield usage_row()
    conn=Mock(fetchval=AsyncMock(return_value=1),transaction=transaction,cursor=cursor)
    @asynccontextmanager
    async def connection():
        yield conn
    end=datetime.now(timezone.utc)
    with patch.object(export,'get_ai_conn',connection):
        records=[json.loads(line) async for line in export.snapshot_lines(end-timedelta(days=1),end,10)]
    assert records[0]['record_count']==records[-1]['record_count']==1
    assert records[0]['export_id']==records[-1]['export_id']
    assert records[-1]['payload_sha256']==hashlib.sha256(export.encoded(records[1]['payload'])).hexdigest()


@pytest.mark.asyncio
async def test_oversized_window_is_explicitly_incomplete_and_does_not_read_rows():
    @asynccontextmanager
    async def transaction(**kwargs):
        yield
    conn=Mock(fetchval=AsyncMock(return_value=11),transaction=transaction)
    @asynccontextmanager
    async def connection():
        yield conn
    end=datetime.now(timezone.utc)
    with patch.object(export,'get_ai_conn',connection):
        records=[json.loads(line) async for line in export.snapshot_lines(end-timedelta(days=1),end,10)]
    assert len(records)==1 and records[0]['complete'] is False
    conn.cursor.assert_not_called()


@pytest.mark.asyncio
async def test_missing_secret_fails_closed_even_if_header_is_empty():
    with patch.object(export,'get_settings',return_value=SimpleNamespace(ai_service_secret='')):
        with pytest.raises(HTTPException) as caught:
            await export.export_llm_attempts(SimpleNamespace(headers={}),days=1,max_records=1)
    assert caught.value.status_code==403
