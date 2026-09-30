---
name: bdc-frontend
description: Frontend submodule boundary guidance for Next.js UI, BFF routes, authenticated requests, and API contract changes.
triggers: [frontend, nextjs, react, typescript, nextauth, ui]
version: "3.0"
requires: [bdc-core-orchestrator]
---

# BDC Frontend Boundary

`frontend/` is a Git submodule. Before editing it, enter that repository, read
its current README and `.agents/skills/`, and make a reviewable submodule commit.
Then update this repository's submodule pointer separately.

- Keep browser secrets out of client code. Browser-to-service calls use approved
  frontend proxy/BFF routes and server-side identity injection where required.
- Do not invent API paths or role rules; coordinate with the owning backend and
  update the BA/data/API documentation for a contract change.
- Treat recommendation tracking tokens and internal service secrets as
  server-side only.
- Run the frontend's documented lint/test/build checks in the submodule.
