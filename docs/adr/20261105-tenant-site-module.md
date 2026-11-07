# Tenant website configuration in Auth/Management

Status: accepted implementation, 2026-11-05.

Auth owns organizations and now owns a `tenantsite` module, split into
controller, DTO, service, repository, model and HTTP middleware. No new service
or database cross-reads are introduced. The existing LMS authenticated image
upload API/object storage continues to own uploaded files.

`tenant_sites` stores one bounded website aggregate per organization. Pages,
navigation, sliders, contact and ordered sections are part of the same JSON
snapshot so publication is atomic and menu/page references can be validated
together. This is intentionally not an unbounded article/news CMS. Documents
are limited to 256 KiB, 30 information pages, 30 blocks per page, 12 slides,
12 menu entries per level and two menu levels. A future large CMS should use
separate page entities/service rather than grow this aggregate indefinitely.

The draft and public snapshot are separate columns. Draft writes and publication
lock the organization row and require an expected revision, returning 409 rather
than overwriting another editor. Public reads return only published documents
for active organizations. No HTML/JavaScript/CSS input is executed; text supports
Markdown with raw HTML disabled and links are validated as HTTP(S)/local paths.

Existing global `ROLE_ADMIN` is required for editor APIs. This does not delegate
publishing to all members or invent an organization-admin entitlement. The
public GET route alone is anonymous. Admin responses use no-store. Public reads
are cached for 30 seconds in HTTP and Next.js. Publishing can take up to 30
seconds to appear. Public information routes require no membership; service
routes retain their existing membership/role/resource checks.

The bounded in-process rate limiter is an instance-level safety net (60 admin
requests/minute/principal; 180 public reads/minute/remote address, 10,000 keys).
It does not claim a cluster-wide quota. Set ingress/gateway limits separately
if replicas or traffic require a global policy; forwarded headers are not trusted
by this limiter. Oversized declared request bodies are rejected before parsing.

Rollout: apply `auth-and-management-service/migrations/V20261105__tenant_sites.sql`
to the Auth database, deploy Auth, then deploy frontend. Existing organization
landing remains the fallback until publication and after unpublishing. No
production data is modified by development tests.
