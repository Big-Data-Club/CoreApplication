# Dynamic Permission Management for LMS

## Background

The LMS currently supports dynamic roles via `role_definitions` table and auth-service mapping. However, authorization is **hardcoded** throughout the backend — `if role == "ADMIN"` appears in ~20 locations across handlers and services. This plan introduces a granular permission system allowing admins to assign specific capabilities to any role through a UI.

> [!IMPORTANT]
> **ID Type Decision:** The SRD specifies UUID for `permissions.id`. However, **every existing table** in the LMS schema uses `BIGSERIAL` (int64). This plan uses `BIGSERIAL` to maintain consistency. Switching to UUID would require changes across the entire DI chain.

---

## Open Questions

> [!IMPORTANT]
> **ADMIN Bypass:** Should ADMIN always pass all permission checks automatically (super-admin pattern), or should ADMIN's permissions also be configurable? The current plan treats ADMIN as a hardcoded super-admin that always passes. This matches the existing behavior.

> [!WARNING]
> **Phase 4 Scope:** The SRD says "remove ALL hardcoded role checks." However, many checks are **ownership-based** (e.g., `if role != "ADMIN" && course.CreatedBy != userID`). These combine role checks with resource ownership and cannot be purely replaced by route-level middleware. Plan: Replace only **route-level** `RequireRole("ADMIN")` calls in `main.go`. Keep handler-level ownership checks as-is since they serve a different purpose (resource-level access, not capability-based access).

---

## Proposed Changes

### Phase 1: Database & Models

#### [NEW] [V004__dynamic_permissions.sql](file:///d:/CodeSpace/BDCApp/lms-service/migrations/V004__dynamic_permissions.sql)

Two new tables:

```sql
-- permissions: Master list of all grantable capabilities
CREATE TABLE permissions (
    id          BIGSERIAL PRIMARY KEY,
    code        VARCHAR(80) UNIQUE NOT NULL,  -- MODULE_ACTION format
    module      VARCHAR(40) NOT NULL,         -- grouping key for UI
    description VARCHAR(255),
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- role_permissions: N-N junction table
CREATE TABLE role_permissions (
    role_id       BIGINT NOT NULL REFERENCES role_definitions(id) ON DELETE CASCADE,
    permission_id BIGINT NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    assigned_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (role_id, permission_id)
);
```

Seed permissions (5 modules, 15 codes):

| Module | Codes |
|--------|-------|
| `COURSE` | `COURSE_VIEW`, `COURSE_CREATE`, `COURSE_EDIT`, `COURSE_DELETE`, `COURSE_PUBLISH` |
| `QUIZ` | `QUIZ_CREATE`, `QUIZ_EDIT`, `QUIZ_DELETE`, `QUIZ_GRADE` |
| `ENROLLMENT` | `ENROLLMENT_MANAGE`, `ENROLLMENT_BULK` |
| `AI` | `AI_INDEX`, `AI_GENERATE` |
| `SYSTEM` | `ROLE_MANAGE`, `ANALYTICS_VIEW` |

Auto-assign all permissions to ADMIN and teacher-relevant ones to TEACHER.

---

#### [NEW] [permission.go](file:///d:/CodeSpace/BDCApp/lms-service/internal/models/permission.go)

```go
type Permission struct {
    ID          int64     `json:"id" db:"id"`
    Code        string    `json:"code" db:"code"`
    Module      string    `json:"module" db:"module"`
    Description string    `json:"description" db:"description"`
    CreatedAt   time.Time `json:"created_at" db:"created_at"`
}

type RolePermission struct {
    RoleID       int64     `json:"role_id" db:"role_id"`
    PermissionID int64     `json:"permission_id" db:"permission_id"`
    AssignedAt   time.Time `json:"assigned_at" db:"assigned_at"`
}
```

---

#### [NEW] [permission_dto.go](file:///d:/CodeSpace/BDCApp/lms-service/internal/dto/permission_dto.go)

```go
type PermissionResponse struct {
    ID          int64  `json:"id"`
    Code        string `json:"code"`
    Module      string `json:"module"`
    Description string `json:"description"`
}

type AssignPermissionsRequest struct {
    PermissionIDs []int64 `json:"permission_ids" binding:"required"`
}

type RolePermissionsResponse struct {
    RoleID      int64               `json:"role_id"`
    RoleName    string              `json:"role_name"`
    Permissions []PermissionResponse `json:"permissions"`
}
```

---

### Phase 2: Repository & Service

#### [NEW] [permission_repo.go](file:///d:/CodeSpace/BDCApp/lms-service/internal/repository/permission_repo.go)

Key methods:
- `FindAll(ctx) → []Permission` — master list for UI
- `FindByRoleID(ctx, roleID) → []Permission` — current assignments
- `FindCodesByRoleName(ctx, roleName) → []string` — for middleware cache miss
- `AssignToRole(ctx, roleID, permissionIDs)` — **transactional**: DELETE old + INSERT new in single tx

---

#### [NEW] [permission_service.go](file:///d:/CodeSpace/BDCApp/lms-service/internal/service/permission_service.go)

Redis caching strategy:
- **Cache key:** `perm:role:{ROLE_NAME}` → JSON array of permission code strings
- **TTL:** 10 minutes
- **Read path:** `CheckPermission(ctx, roleName, code)` → Redis GET → if miss → DB query → Redis SET
- **Write path:** `AssignPermissions(ctx, roleID, permIDs)` → DB tx → invalidate cache for that role
- Uses `pkg/cache/redis.go` methods (`Get`, `Set`, `Delete`)

```
CheckPermission(roleName, code) flow:
  1. if roleName == "ADMIN" → return true (super-admin bypass)
  2. Redis GET "perm:role:{roleName}"
  3. HIT  → unmarshal []string, check contains(code)
  4. MISS → repo.FindCodesByRoleName(roleName) → Redis SET → check contains(code)
```

---

### Phase 3: API & Middleware

#### [NEW] [permission_handler.go](file:///d:/CodeSpace/BDCApp/lms-service/internal/handler/permission_handler.go)

Three endpoints under `/api/v1/admin/permissions`:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/admin/permissions` | List all permissions (master data) |
| `GET` | `/api/v1/admin/roles/:id/permissions` | Get permissions assigned to a role |
| `PUT` | `/api/v1/admin/roles/:id/permissions` | Replace permissions for a role |

All protected by `RequireRole("ADMIN")` initially.

---

#### [NEW] [permission.go](file:///d:/CodeSpace/BDCApp/lms-service/internal/middleware/permission.go)

```go
func RequirePermission(permService *service.PermissionService, code string) gin.HandlerFunc {
    return func(c *gin.Context) {
        roleName := c.GetString("user_role")
        
        // Super-admin bypass
        if roleName == "ADMIN" {
            c.Next()
            return
        }
        
        allowed, err := permService.CheckPermission(c.Request.Context(), roleName, code)
        if err != nil || !allowed {
            c.JSON(403, dto.NewErrorResponse("forbidden", "Insufficient permissions"))
            c.Abort()
            return
        }
        c.Next()
    }
}
```

---

#### [MODIFY] [main.go](file:///d:/CodeSpace/BDCApp/lms-service/cmd/api/main.go)

Wire new components into DI:

```go
permRepo := repository.NewPermissionRepository(db)
permService := service.NewPermissionService(permRepo, redisClient)
permHandler := handler.NewPermissionHandler(permService)
```

Register new routes under the existing `adminRoles` group and add a new permission routes group.

---

### Phase 4: Route-Level Refactor

Replace `middleware.RequireRole("ADMIN")` in `main.go` routes with `middleware.RequirePermission(permService, "CODE")`:

| Current | New |
|---------|-----|
| `courses.DELETE("/:courseId", middleware.RequireRole("ADMIN"), ...)` | `middleware.RequirePermission(permService, "COURSE_DELETE")` |
| `analytics.GET("/heatmap", middleware.RequireRoles("ADMIN", "TEACHER"), ...)` | `middleware.RequirePermission(permService, "ANALYTICS_VIEW")` |
| `adminRoles` group `RequireRole("ADMIN")` | `middleware.RequirePermission(permService, "ROLE_MANAGE")` |

> [!NOTE]
> Handler-level ownership checks (`if role != "ADMIN" && course.CreatedBy != userID`) are **not changed** in this phase. They serve resource-level access control which is orthogonal to capability-based permissions.

---

### Phase 5: Frontend UI

#### [NEW] [permissionService.ts](file:///d:/CodeSpace/BDCApp/frontend/src/services/permissionService.ts)

LMS API client calls for the 3 new endpoints.

---

#### [MODIFY] [RoleManager.tsx](file:///d:/CodeSpace/BDCApp/frontend/src/components/admin/RoleManager.tsx)

Add a "Permissions" action button per role row (alongside existing Edit/LMS Mapping/Delete buttons). When clicked, opens a `PermissionEditor` panel.

---

#### [NEW] [PermissionEditor.tsx](file:///d:/CodeSpace/BDCApp/frontend/src/components/admin/PermissionEditor.tsx)

Modal component showing:
- Header: "Configure permissions for role: [ROLE_NAME]"
- Permissions grouped by `module` (COURSE, QUIZ, AI, etc.)
- Each group shows checkboxes with permission descriptions
- "Save Changes" button with loading state
- Toast notification on success/error

UI style: Minimalist, follows BDC Design Rhythm. White cards, slate borders, blue-600 primary actions, dark mode support.

---

## Verification Plan

### Automated Tests

```bash
# Go build verification
cd lms-service && go build ./...

# Verify migration syntax (dry run)
psql -f migrations/V004__dynamic_permissions.sql --echo-errors
```

### Manual Verification

1. **Backend API:** Use curl/Postman to test all 3 permission endpoints
2. **Middleware:** Assign `COURSE_CREATE` to TEACHER role → verify teacher can create courses. Remove it → verify 403
3. **Cache:** Verify Redis key `perm:role:TEACHER` is created on first check, invalidated on permission update
4. **Frontend:** Open `/settings/roles` → click permissions icon → toggle checkboxes → save → verify immediate effect
5. **Regression:** Verify ADMIN still passes all checks without explicit permission assignments
