---
name: bdc-frontend
description: >
  Use for every task touching frontend/src/ - components, hooks, service calls,
  page routes, API route handlers, Tailwind styling, dark mode, modals, forms,
  or any new feature. Also consult when wiring up environment variables,
  proxy-aware fetches, or reviewing code consistency.
triggers:
  - frontend/
  - next.js
  - react
  - tailwind
  - typescript
  - nextauth
  - component
  - hook
  - page
version: "2.1"
authors:
  - BDC Team
requires:
  - bdc-core-orchestrator
---

# BDC Frontend - Developer Skill

**Runtime:** Node.js 20 Alpine
**Framework:** Next.js 14 App Router
**Language:** TypeScript (`strict: true`, `noImplicitAny: false`)
**Styling:** Tailwind CSS + shadcn/ui
**Auth:** NextAuth.js (credentials provider, JWT sessions)
**Backends:** Auth service `:8080` · LMS service `:8081`

---

## Directory Map (Key Paths)

```
frontend/src/
├── app/
│   ├── (auth)/               login, confirm-password-change
│   ├── (landing)/            public landing pages
│   ├── (main)/               authenticated sidebar app - dashboard, events, tasks, users
│   ├── (learning)/lms/       LMS area - admin, student, teacher, forums
│   └── api/                  Next.js Route Handlers (NextAuth, upload, youtube, health)
├── components/
│   ├── ui/                   shadcn/ui primitives - do not modify directly
│   ├── layout/               Sidebar, MobileNav, Navbar, Footer
│   ├── common/               SafeImage and other cross-feature components
│   ├── dashboard/            announcement/, event/, calendar/, modals/
│   ├── lms/shared/           LMS-flavoured primitives (separate from dashboard)
│   ├── lms/student/          AIDiagnosisModal, ContentViewer, QuizHistoryModal
│   └── lms/teacher/          AINodeManager, AIQuizGenPanel, BulkUploadModal
├── hooks/                    useAuth, useCurrentUser, useAnnouncements, useEvents, useTasks
├── services/                 ALL fetch() calls live here - never in components or hooks
├── types/                    All shared TypeScript interfaces - re-export from index.ts
├── store/UserContext.tsx      Global user state
├── providers/MainProvider.tsx SessionProvider + UserContext + ThemeProvider
└── utils/                    Pure helpers - no React imports
```

---

## Proxy Rewrites (next.config.ts)

Never call backend ports directly from client code. Use the proxy paths.

| Frontend path | Proxies to | Purpose |
|---------------|-----------|---------|
| `/apiv1/:path*` | `BACKEND_URL/:path*` | Auth, users, events, announcements |
| `/uploads/:path*` | `BACKEND_URL/uploads/:path*` | Auth service file uploads |
| `/lmsapiv1/:path*` | `LMS_API_URL/api/v1/:path*` | All LMS features |
| `/files/:path*` | `LMS_API_URL/api/v1/files/serve/:path*` | LMS file serving |

```ts
// ✅ Correct - works in Docker and production
const res = await fetch("/apiv1/announcements");

// ❌ Wrong - hardcoded port, breaks in Docker
const res = await fetch("http://localhost:8080/announcements");
```

---

## API Clients

Two base clients - every service file imports from one of them:

| Client | File | Use for |
|--------|------|---------|
| Auth backend | `services/api.ts` | `(main)/` pages |
| LMS backend | `services/lmsApiClient.ts` | `(learning)/lms/` pages |

Both clients attach `Authorization: Bearer <token>` from NextAuth session and
throw `Error` on non-2xx responses.

### Service File Template

```ts
// services/featureService.ts
import { apiClient } from "./api";  // or lmsApiClient for LMS resources
import type { Feature } from "@/types";

export const featureService = {
  getAll:  ():                     Promise<Feature[]> => apiClient.get("/features"),
  getById: (id: number):           Promise<Feature>   => apiClient.get(`/features/${id}`),
  create:  (data: Partial<Feature>):Promise<Feature>   => apiClient.post("/features", data),
  update:  (id: number, data: Partial<Feature>): Promise<Feature> =>
                                                          apiClient.put(`/features/${id}`, data),
  delete:  (id: number):           Promise<void>      => apiClient.delete(`/features/${id}`),
};
```

---

## Authentication

### In Client Components

```ts
import { useAuth } from "@/hooks/useAuth";
const { user, isAdmin, checkAdminAccess } = useAuth();

// Guard admin mutations
const handleDelete = async (id: number) => {
  if (!checkAdminAccess("xóa")) return;
  await featureService.delete(id);
};
```

### In Route Handlers

```ts
import { getServerSession } from "next-auth";
import { authOptions } from "@/app/api/auth/[...nextauth]/route";

const session = await getServerSession(authOptions);
if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
```

---

## Hook Template (CRUD + Modal State)

```ts
// hooks/useFeature.tsx
import { useState, useEffect, useCallback } from "react";
import { featureService } from "@/services/featureService";
import type { Feature } from "@/types";

type ModalMode = "add" | "edit" | "view";
const EMPTY: Partial<Feature> = {};

export function useFeature() {
  const [items,   setItems]   = useState<Feature[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen]   = useState(false);
  const [modalMode, setModalMode]   = useState<ModalMode>("view");
  const [currentItem, setCurrentItem] = useState<Partial<Feature>>(EMPTY);

  const load = useCallback(async () => {
    setLoading(true);
    try   { setItems(await featureService.getAll()); }
    catch (err) { console.error("useFeature: fetch failed", err); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const openModal  = useCallback((mode: ModalMode, item?: Feature) => {
    setModalMode(mode);
    setCurrentItem(item ?? EMPTY);
    setModalOpen(true);
  }, []);

  const closeModal = useCallback(() => setModalOpen(false), []);

  const save = useCallback(async (item: Partial<Feature>) => {
    item.id ? await featureService.update(item.id, item)
            : await featureService.create(item);
    closeModal();
    await load();
  }, [closeModal, load]);

  const remove = useCallback(async (id: number) => {
    await featureService.delete(id);
    setItems(prev => prev.filter(f => f.id !== id));
  }, []);

  return { items, loading, modalOpen, modalMode, currentItem, setCurrentItem,
           openModal, closeModal, save, remove };
}
```

---

## Page Composition Pattern

`page.tsx` is a composition shell - no `useState`, `useEffect`, or `fetch()` directly.

```tsx
// app/(main)/feature/page.tsx
"use client";
export default function FeaturePage() {
  const { isAdmin, checkAdminAccess } = useAuth();
  const { items, loading, modalOpen, modalMode, currentItem, setCurrentItem,
          openModal, closeModal, save, remove } = useFeature();
  const { visibleItems, hasMore, remaining, showMore } = usePagination(items, 4);

  return (
    <>
      <FeatureModal open={modalOpen} mode={modalMode} item={currentItem}
        onOpenChange={closeModal} onChange={setCurrentItem}
        onSave={async () => { try { await save(currentItem); } catch (e: any) { alert(e.message); }}} />
      <div className="space-y-10">
        <DashboardHeader />
        <section>
          <SectionHeader title="Feature" showAddButton={isAdmin}
            onAdd={() => { if (checkAdminAccess()) openModal("add"); }} />
          <FeatureList items={visibleItems} loading={loading} isAdmin={isAdmin}
            onView={item => openModal("view", item)}
            onEdit={item => { if (checkAdminAccess()) openModal("edit", item); }}
            onDelete={async id => { if (checkAdminAccess("xóa")) await remove(id); }} />
          {hasMore && <ShowMoreButton onClick={showMore} remaining={remaining} />}
        </section>
      </div>
    </>
  );
}
```

---

## Styling Reference

### Colour Tokens

| Role | Light | Dark |
|------|-------|------|
| Page background | `bg-slate-50` | `dark:bg-slate-950` |
| Card / Sidebar | `bg-white` | `dark:bg-slate-900` |
| Card border | `border-slate-200` | `dark:border-slate-800` |
| Input bg | `bg-slate-50` | `dark:bg-slate-800` |
| Input border | `border-slate-300` | `dark:border-slate-700` |
| Heading | `text-slate-900` | `dark:text-slate-50` |
| Body | `text-slate-600` | `dark:text-slate-400` |
| Caption | `text-slate-500` | `dark:text-slate-500` |
| Primary action | `bg-blue-600` | (unchanged) |
| Danger | `text-red-500 bg-red-50` | `dark:text-red-400 dark:bg-red-950/40` |

### Reusable Copy-Paste Patterns

**Card:**
```tsx
<div className="bg-white dark:bg-slate-900 p-6 rounded-2xl
                border border-slate-200 dark:border-slate-800
                shadow-sm hover:shadow-md transition-shadow duration-300">
```

**Primary Button:**
```tsx
<Button className="bg-blue-600 hover:bg-blue-700 text-white font-semibold
                   rounded-xl px-6 py-2.5 shadow-sm active:scale-95 transition-all duration-200">
```

**Input:**
```tsx
<Input className="rounded-xl border-slate-300 dark:border-slate-700
                  bg-slate-50 dark:bg-slate-800
                  focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20
                  transition-all duration-200" />
```

---

## Naming Conventions

| Item | Convention | Example |
|------|-----------|---------|
| Component file | PascalCase.tsx | `AnnouncementCard.tsx` |
| Hook file | camelCase.tsx, prefix `use` | `useAnnouncements.tsx` |
| Service file | camelCase.ts, suffix `Service` | `announcementService.ts` |
| Type file | kebab-case.ts | `announcement-event.ts` |
| Component export | Named (not default) | `export function AnnouncementCard` |
| Page / layout | Default export | `export default function DashboardPage` |
| Event handlers | Prefix `handle` | `handleSave`, `handleDelete` |
| Boolean state/props | Prefix `is/has/show` | `isAdmin`, `hasMore` |

---

## Route Groups

| Group | Layout | Auth |
|-------|--------|------|
| `(auth)` | Minimal, no sidebar | No |
| `(landing)` | Public landing | No |
| `(main)` | Sidebar + MobileNav | Yes |
| `(learning)/lms` | LMS shell | Yes |

---

## Anti-Patterns

| Do not | Instead |
|--------|---------|
| Call `fetch()` in a component or hook | Put in `services/`, call from hook |
| Write data-fetching logic in `page.tsx` | Extract to `use<Feature>()` hook |
| Use `any` type | Define interface in `src/types/` |
| Use `lmsApiClient` from `(main)/` pages | `(main)/` uses `api.ts` only |
| Hardcode backend URLs or ports | Use proxy paths via service files |
| Use `backdrop-blur` on sidebar/navbar | Solid `bg-white dark:bg-slate-900` |
| Multi-colour gradients | Solid colours or same-hue gradient |
| Inline `style={{}}` | Tailwind only |
| Omit `dark:` pair on any colour class | Every bg/text/border needs dark pair |
| Omit `active:scale-95` on buttons | All clickable elements need press feedback |
| Leave `console.log` in committed code | Remove before PR |
| Use default export for a component | Named exports only |
| Build new LMS primitive | Check `components/lms/shared/` first |

---

## Pre-PR Checklist

```
[ ] New type in src/types/ and re-exported from index.ts
[ ] Service uses api.ts or lmsApiClient.ts - no raw fetch() in hooks or components
[ ] Hook follows CRUD + modal pattern
[ ] Component in correct folder with named export
[ ] Props interface named <Component>Props, fully typed
[ ] page.tsx is composition only - no useState/useEffect/fetch inside
[ ] All colours from approved token table with dark: counterpart
[ ] Buttons have active:scale-95 transition-all duration-200
[ ] Cards use rounded-2xl border-slate-200 dark:border-slate-800 shadow-sm
[ ] Inputs use focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500
[ ] Loading uses <LoadingState /> - no custom spinner
[ ] Empty state has visible message
[ ] Admin mutations guarded with checkAdminAccess()
[ ] No hardcoded localhost URLs
[ ] No console.log
[ ] Works in both light and dark mode
```