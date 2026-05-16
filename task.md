# Dynamic Permission Management — Task Tracker

## Phase 1: Database & Models
- [/] Migration V004__dynamic_permissions.sql
- [ ] Model: permission.go
- [ ] DTO: permission_dto.go

## Phase 2: Repository & Service
- [ ] Repository: permission_repo.go
- [ ] Service: permission_service.go (with Redis cache)
- [ ] Cache key helper in redis.go

## Phase 3: API & Middleware
- [ ] Handler: permission_handler.go
- [ ] Middleware: permission.go
- [ ] Wire into main.go (DI + routes)

## Phase 4: Route Refactor
- [ ] Replace hardcoded RequireRole("ADMIN") in main.go routes

## Phase 5: Frontend
- [ ] Service: permissionService.ts
- [ ] Component: PermissionEditor.tsx
- [ ] Update RoleManager.tsx

## Verification
- [ ] Go build passes
- [ ] Frontend builds
