#!/usr/bin/env bash
# Read-only checks; prints no credentials or learner data.
set -euo pipefail
namespace="${DEPLOY_NAMESPACE:-default}"
kubectl -n "$namespace" get deploy lms-service ai-service ai-worker \
  -o 'custom-columns=NAME:.metadata.name,IMAGE:.spec.template.spec.containers[0].image'
kubectl -n "$namespace" exec -i deploy/ai-service -- python - <<'PY'
import asyncio, json, os, urllib.error, urllib.request, asyncpg
schema = json.load(urllib.request.urlopen('http://127.0.0.1:8000/openapi.json', timeout=15))
assert 'post' in schema['paths'].get('/ai/flashcards/personal', {}), 'AI image is missing personal flashcard route'
print('AI personal flashcard route: OK')
async def check():
    conn = await asyncpg.connect(host=os.environ['AI_DB_HOST'], port=int(os.environ.get('AI_DB_PORT', '5432')), user=os.environ['AI_DB_USER'], password=os.environ['AI_DB_PASSWORD'], database=os.environ['AI_DB_NAME'])
    try:
        for table, column in [('personal_flashcard_decks','course_id'), ('personal_flashcard_jobs','course_id'), ('personal_flashcard_decks','source_content_id'), ('personal_flashcards','source_node_ids')]:
            exists = await conn.fetchval('SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=current_schema() AND table_name=$1 AND column_name=$2)', table, column)
            assert exists, 'Missing flashcard migration column: ' + table + '.' + column
        print('Flashcard schema V017/V018: OK')
    finally:
        await conn.close()
asyncio.run(check())
request = urllib.request.Request('http://lms-service:8081/api/v1/courses/1/flashcard-library', data=b'{"action":"list"}', headers={'Content-Type':'application/json'})
try:
    urllib.request.urlopen(request, timeout=15)
except urllib.error.HTTPError as exc:
    assert exc.code == 401, 'LMS route expected unauthenticated 401, got ' + str(exc.code)
    print('LMS personal flashcard route: OK (requires authentication)')
else:
    raise RuntimeError('LMS route unexpectedly allowed unauthenticated request')
PY
