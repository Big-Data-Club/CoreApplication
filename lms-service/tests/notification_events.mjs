// Run with PGLITE_TEST_MODULE=/tmp/.../node_modules/@electric-sql/pglite/dist/index.js
// node --test lms-service/tests/notification_events.mjs
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
const { PGlite } = await import(process.env.PGLITE_TEST_MODULE || '@electric-sql/pglite');
const root = fileURLToPath(new URL('../../', import.meta.url));
let db;
const source=readFileSync(root+'lms-service/internal/repository/notification_repository.go','utf8');
const feedSql=source.match(/const learningNoticeQuery = `([\s\S]*?)`/)[1];
const feed=async(user=502)=>(await db.query(feedSql,[user])).rows;
const count=async()=>Number((await db.query('SELECT COUNT(*) AS count FROM learning_notification_events')).rows[0].count);
before(async()=>{
 db=new PGlite();
 for(const file of ['V001__core_schema.sql','V005__organizations.sql','V021__learning_notifications.sql']) await db.exec(readFileSync(root+'lms-service/migrations/'+file,'utf8'));
 await db.exec(`INSERT INTO users(id,email) VALUES(501,'author@example.test'),(502,'learner@example.test'),(503,'outsider@example.test'),(504,'private@example.test');
 INSERT INTO organizations(id,name,slug,settings) VALUES(2,'Private','private','{"allow_cross_org_courses":false}'),(3,'Other','other','{"allow_cross_org_courses":true}');
 INSERT INTO organization_members(org_id,user_id) VALUES(1,501),(1,502),(2,504);
 INSERT INTO courses(id,title,status,created_by,org_id,visibility) VALUES(501,'Python','DRAFT',501,1,'PUBLIC');
 INSERT INTO enrollments(student_id,course_id,status) VALUES(502,501,'ACCEPTED');
 INSERT INTO course_sections(id,course_id,title,order_index,is_published) VALUES(501,501,'Loops',0,false);
 INSERT INTO section_content(id,section_id,title,type,order_index,created_by,is_published) VALUES(501,501,'For loops','TEXT',0,501,false);`);
});
after(async()=>{await db?.close()});
test('drafts are silent; publishing emits actual course, chapter and lesson events',async()=>{
 assert.equal(await count(),0);
 await db.exec(`UPDATE courses SET status='PUBLISHED',published_at=now() WHERE id=501;UPDATE course_sections SET is_published=true WHERE id=501;UPDATE section_content SET is_published=true WHERE id=501;`);
 assert.deepEqual((await feed()).map(n=>n.kind).sort(),['content_added','course_published','section_added']);
});
test('transaction rollback, no-op and AI indexing status do not create notifications',async()=>{
 const before=await count();
 await db.exec(`BEGIN;UPDATE section_content SET title='Rolled back' WHERE id=501;ROLLBACK;
 UPDATE section_content SET updated_at=now(),ai_index_status='processing' WHERE id=501;
 UPDATE courses SET updated_at=now() WHERE id=501;`);
 assert.equal(await count(),before);
});
test('batch additions group per chapter; published edits retain exact content target',async()=>{
 await db.exec(`INSERT INTO section_content(id,section_id,title,type,order_index,created_by,is_published) VALUES(502,501,'While loops','TEXT',1,501,true),(503,501,'Practice','TEXT',2,501,true);
 UPDATE section_content SET title='Updated for loops' WHERE id=501;`);
 const items=await feed();
 assert.equal(Number(items.find(n=>n.kind==='content_added').item_count),3);
 assert.equal(items.filter(n=>n.kind==='content_added').length,1);
 assert.equal(Number(items.find(n=>n.kind==='content_updated').content_id),501);
 assert.equal(items.find(n=>n.kind==='content_updated').entity_title,'Updated for loops');
});
test('updates require enrollment; private organization boundary is enforced',async()=>{
 assert.deepEqual((await feed(503)).map(n=>n.kind),['course_published']);
 assert.deepEqual(await feed(504),[]);
 await db.exec(`INSERT INTO courses(id,title,status,created_by,org_id,visibility) VALUES(502,'Private course','PUBLISHED',501,3,'ORG_ONLY');`);
 assert.ok(!(await feed(502)).some(n=>Number(n.course_id)===502));
});
test('read receipts are idempotent and isolated; a new edit has a new unread identity',async()=>{
 const old=(await feed()).find(n=>n.kind==='content_updated');
 await db.query(`INSERT INTO learning_notification_reads(user_id,notification_key) SELECT $1,key FROM (SELECT DISTINCT unnest($2::text[]) AS key) keys ON CONFLICT(user_id,notification_key) DO UPDATE SET read_at=now()`,[502,[`learning:${old.id}`,`learning:${old.id}`]]);
 await db.query(`INSERT INTO learning_notification_reads(user_id,notification_key) VALUES($1,$2) ON CONFLICT(user_id,notification_key) DO UPDATE SET read_at=now()`,[502,`learning:${old.id}`]);
 assert.equal((await db.query('SELECT * FROM learning_notification_reads WHERE user_id=502')).rows.length,1);
 assert.equal((await db.query('SELECT * FROM learning_notification_reads WHERE user_id=503')).rows.length,0);
 await db.exec(`UPDATE section_content SET description='Another edit' WHERE id=501`);
 const current=(await feed()).find(n=>n.kind==='content_updated');
 assert.notEqual(current.id,old.id);
 assert.equal((await db.query('SELECT * FROM learning_notification_reads WHERE user_id=$1 AND notification_key=$2',[502,`learning:${current.id}`])).rows.length,0);
});
test('hidden/deleted content never produces a broken direct link; revoked membership disappears',async()=>{
 await db.exec(`UPDATE section_content SET is_published=false WHERE id=501`);
 let items=await feed();
 assert.ok(!items.some(n=>n.kind==='content_updated'&&Number(n.content_id)===501));
 assert.ok(items.some(n=>n.kind==='content_removed'));
 await db.exec(`DELETE FROM course_sections WHERE id=501`);
 items=await feed();
 assert.ok(items.some(n=>n.kind==='section_removed'));
 assert.ok(!items.some(n=>n.kind.startsWith('content_')));
 await db.exec(`UPDATE enrollments SET status='REJECTED' WHERE student_id=502 AND course_id=501`);
 assert.deepEqual((await feed()).map(n=>n.kind),['course_published']);
});

test('all serving queries execute against PostgreSQL, including deadlines and node targets',async()=>{
 const queries=[...source.matchAll(/s\.db\.QueryContext\(ctx,\s*`([\s\S]*?)`, userID\)/g)].map(match=>match[1]);
 assert.ok(queries.length>=4);
 for(const query of queries) await db.query(query,[502]);
});
test('startup recognizes an installed schema without replaying publication events',async()=>{
 const startup=readFileSync(root+'lms-service/pkg/database/notifications.go','utf8');
 const sql=startup.match(/QueryRowContext\(ctx,\s*`([\s\S]*?)`/)[1];
 const before=await count();
 assert.equal(Object.values((await db.query(sql)).rows[0])[0],true);
 assert.equal(await count(),before);
});
test('new course launches cannot crowd out enrolled-course updates',async()=>{
 await db.exec(`UPDATE enrollments SET status='ACCEPTED' WHERE student_id=502 AND course_id=501`);
 for(let id=1000;id<1010;id++) await db.query(`INSERT INTO courses(id,title,status,created_by,org_id,visibility) VALUES($1,$2,'PUBLISHED',501,1,'PUBLIC')`,[id,`New course ${id}`]);
 const items=await feed();
 assert.equal(items.filter(n=>n.kind==='course_published').length,5);
 assert.ok(items.some(n=>n.kind==='section_removed'&&Number(n.course_id)===501));
});
