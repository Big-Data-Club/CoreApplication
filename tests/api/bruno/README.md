# BDC API Testing Guide with Bruno

| Field     | Value                     |
|-----------|---------------------------|
| Version   | 1.0.0                     |
| Status    | Approved                  |
| Date      | 2026-05-28                |
| Authors   | BDC Team                  |
| Reviewers | —                         |

## Revision History

| Version | Date       | Author   | Description   |
|---------|------------|----------|---------------|
| 1.0.0   | 2026-05-28 | BDC Team | Initial guide |

## 1. Overview

This document provides instructions on how to use the Bruno API testing collection to verify the Organization Isolation feature within the BDC LMS. The test collection automates authentication, organization operations, membership management, course visibility checks, and resource cleanup.

## 2. Directory Structure

The Bruno collection is structured as follows:

```
tests/api/bruno/
├── bruno.json
├── environments/
│   └── local.bru
├── 01. Authentication/
│   └── Login.bru
├── 02. Organizations/
│   ├── Create Org.bru
│   ├── List Orgs.bru
│   ├── Get Org.bru
│   ├── Update Org.bru
│   └── Get Org Stats.bru
├── 03. Members/
│   ├── Add Member.bru
│   ├── Update Member Role.bru
│   └── List Members.bru
├── 04. Courses/
│   ├── Create Org Course.bru
│   ├── List Visible Courses.bru
│   └── Toggle Visibility.bru
├── 05. User Orgs/
│   └── Get My Orgs.bru
└── 06. Cleanup/
    ├── Remove Member.bru
    └── Deactivate Org.bru
```

## 3. Dynamic Variables and Chaining

To achieve automated testing without manual token copying, the collection uses Bruno post-response scripts to capture variables dynamically:

1.  **Authentication**: `01. Authentication/Login.bru` calls `/api/auth/login` and extracts the Bearer token.
    ```javascript
    if (res.status === 200 && res.body.token) {
      bru.setVar("token", res.body.token);
    }
    ```
2.  **Organization ID**: `02. Organizations/Create Org.bru` captures the generated organization ID.
    ```javascript
    if (res.status === 201 && res.body.data && res.body.data.id) {
      bru.setVar("created_org_id", res.body.data.id);
    }
    ```
3.  **Course ID**: `04. Courses/Create Org Course.bru` captures the course ID for subsequent visibility checks.
    ```javascript
    if (res.status === 201 && res.body.data && res.body.data.id) {
      bru.setVar("created_course_id", res.body.data.id);
    }
    ```

## 4. How to Run the Tests

### 4.1 Prerequisites

1.  Download and install the **Bruno** desktop application.
2.  Verify the local services are running on ports 8080 (Auth) and 8081 (LMS).
3.  Ensure the environment values in `tests/api/bruno/environments/local.bru` match your setup:
    -   `AUTH_URL`: `http://localhost:8080`
    -   `LMS_URL`: `http://localhost:8081`
    -   `admin_email`: Credentials of a super administrator.
    -   `admin_password`: Password of the super administrator.
    -   `test_user_id`: ID of a user in the database to test membership assignment (defaults to `3`).

### 4.2 Importing the Collection

1.  Open the Bruno application.
2.  Select **Open Collection** from the home screen.
3.  Navigate to the project root and select the `tests/api/bruno` folder.
4.  Once imported, select the **local** environment from the environment selector dropdown in the top-right corner.

### 4.3 Executing Requests

To test all logic cases, run the requests in the following sequence:

1.  **Authentication**:
    -   Run `01. Authentication/Login.bru` to authenticate and save the authorization token.
2.  **Organizations**:
    -   Run `Create Org.bru` to initialize a test organization.
    -   Run `List Orgs.bru` to verify listing logic.
    -   Run `Get Org.bru` to verify retrieval.
    -   Run `Update Org.bru` to test metadata updates.
    -   Run `Get Org Stats.bru` to verify stats retrieval.
3.  **Members**:
    -   Run `Add Member.bru` to assign the test user to the organization.
    -   Run `Update Member Role.bru` to promote the user's membership role.
    -   Run `List Members.bru` to list organization members.
4.  **Courses**:
    -   Run `Create Org Course.bru` to create an organization-isolated course (`ORG_ONLY`).
    -   Run `List Visible Courses.bru` to verify visibility filtering logic.
    -   Run `Toggle Visibility.bru` to change visibility to `PUBLIC` using the course update payload.
5.  **User Orgs**:
    -   Run `Get My Orgs.bru` to verify user organization retrieval.
6.  **Cleanup**:
    -   Run `Remove Member.bru` to remove the test user.
    -   Run `Deactivate Org.bru` to deactivate the test organization.
