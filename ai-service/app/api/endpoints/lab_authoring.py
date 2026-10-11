"""Internal authenticated, durable lab draft jobs. Never mutates a lab."""
import json
import secrets
from uuid import UUID, uuid4
from fastapi import APIRouter, Header, HTTPException
from app.core.config import get_settings
from app.core.database import get_ai_conn
from app.services.lab_authoring_service import AuthoringRequest

router = APIRouter(prefix='/lab-authoring', tags=['Lab authoring'])


def verify(secret):
    configured = get_settings().ai_service_secret
    if not secret or not configured or not secrets.compare_digest(secret, configured):
        raise HTTPException(401, 'Invalid AI service secret')


def dto(row):
    proposal = row['proposal']
    return {'id': str(row['id']), 'status': row['status'], 'proposal': json.loads(proposal) if isinstance(proposal, str) else proposal,
            'error': row['error'], 'apply_required': True}


@router.post('', status_code=202)
async def create(body: AuthoringRequest, x_ai_secret: str | None = Header(None)):
    verify(x_ai_secret)
    if body.task == 'create_lab_generator' and body.lab_type != 'CODING':
        raise HTTPException(422, 'Generators are available for coding labs only')
    async with get_ai_conn() as conn:
        async with conn.transaction():
            await conn.execute('SELECT pg_advisory_xact_lock($1)', body.owner_id)
            active = await conn.fetchval("SELECT count(*) FROM lab_authoring_jobs WHERE owner_id=$1 AND status IN ('QUEUED','RUNNING')", body.owner_id)
            if active >= 3:
                raise HTTPException(429, 'Wait for existing drafts to finish')
            row = await conn.fetchrow('INSERT INTO lab_authoring_jobs(id,owner_id,request) VALUES($1,$2,$3::jsonb) RETURNING *', uuid4(), body.owner_id, body.model_dump_json())
    return dto(row)


@router.get('/{job_id}')
async def status(job_id: UUID, owner_id: int, x_ai_secret: str | None = Header(None)):
    verify(x_ai_secret)
    async with get_ai_conn() as conn:
        row = await conn.fetchrow('SELECT * FROM lab_authoring_jobs WHERE id=$1 AND owner_id=$2', job_id, owner_id)
    if not row:
        raise HTTPException(404, 'Draft not found')
    return dto(row)
