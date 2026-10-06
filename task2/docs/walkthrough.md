# Round 2 Cloud Architecture & Application Assessment — Complete Walkthrough

**Candidate:** Sai  
**Assessment:** Round 2 Practical Cloud Architecture and Application Deployment  
**Project:** StockPulse — Cloud Shop Inventory & Stock Tracker  

---

## 1. What We Accomplished

### 1. Dedicated Login Gate (`/login`) & Session Security
* **Authentication Barrier**: Unauthenticated visitors cannot access store inventory. Unauthenticated requests to `/`, `/products`, or `/roles` immediately redirect to `/login`.
* **Password Hashing**: Passwords hashed using PBKDF2 with SHA-256 (`werkzeug.security`).
* **Zero Hardcoded Secrets (CWE-798 Compliance)**:
  * Removed all hardcoded credentials from application source code.
  * `FLASK_SECRET_KEY`: Dynamically generated using `secrets.token_hex(32)` if not injected via environment variables.
  * Passwords (`ADMIN_INIT_PASSWORD`, `CLERK_INIT_PASSWORD`, `AUDITOR_INIT_PASSWORD`) are dynamically driven by environment variables (`os.environ`).
  * Creating a new employee without a password dynamically generates an ephemeral random password (`secrets.token_urlsafe(8)`).
* **Token Invalidation on Logout (Replay Attack Defense)**:
  * When a user clicks **Sign Out** (`/logout`), the server immediately sets `session_token = NULL` in the database.
  * Intercepted session tokens or cookies replayed in Burp Suite after logout are instantly rejected with **302 Redirect / 401 Unauthorized**.

### 2. Admin Role Assignment & Team Management (`/roles`)
* **Role Reassignment**: The Store Manager (`admin`) can reassign employee roles between `Admin`, `Clerk`, and `Auditor` directly from the UI.
* **Invite New Team Members**: Store Manager can invite new employees with assigned roles.
* **BAC Enforcement**: If a Clerk or Auditor attempts to assign roles or create users, the backend intercepts the request and blocks it with **HTTP 403 Forbidden**.

### 3. Public AWS ALB Health Check (`/api/health`)
* Stays unauthenticated so the AWS Application Load Balancer can continuously verify container and database health without requiring login sessions.

---

## 2. Automated Test Results

```
[AUTH 1] Unauthenticated / -> HTTP 302 Location: /login?next=http://localhost/ (PASSED)
[AUTH 2] Failed login attempt -> HTTP 200 Invalid credentials error shown (PASSED)
[AUTH 3] Successful login as Alex (Admin) -> HTTP 200 Welcome message (PASSED)
[AUTH 4] Admin assigns role to Bob -> HTTP 200 Role updated in database (PASSED)
[AUTH 5] Admin invites David Vance -> HTTP 200 New employee created with dynamic temp password (PASSED)
[AUTH 6] Logout -> HTTP 200 Session token invalidated in DB, redirected to login (PASSED)
[AUTH 7] Burp Suite Replay Attack with captured token after logout -> BLOCKED (PASSED)
[AUTH 8] Clerk attempts to assign roles -> HTTP 403 Forbidden (BAC Blocked) (PASSED)
[AUTH 9] Public /api/health -> HTTP 200 healthy, DB connected (PASSED)
```

---

## 3. Deliverables Status

All code and documents are cleanly organized in **`task2/`**:
* App & Auth: [`task2/app.py`](file:///Users/mac/Documents/antigravity/dazzling-mendel/task2/app.py)
* Environment Template: [`task2/.env.example`](file:///Users/mac/Documents/antigravity/dazzling-mendel/task2/.env.example)
* Login Screen: [`task2/templates/login.html`](file:///Users/mac/Documents/antigravity/dazzling-mendel/task2/templates/login.html)
* Role Management: [`task2/templates/roles.html`](file:///Users/mac/Documents/antigravity/dazzling-mendel/task2/templates/roles.html)
* Dockerfile & Container Config: [`task2/Dockerfile`](file:///Users/mac/Documents/antigravity/dazzling-mendel/task2/Dockerfile)
* Manual AWS Deployment Guide: [`task2/docs/manual_aws_deployment_guide.md`](file:///Users/mac/Documents/antigravity/dazzling-mendel/task2/docs/manual_aws_deployment_guide.md)
* Interview Defense Guide: [`task2/docs/interview_defense_guide.md`](file:///Users/mac/Documents/antigravity/dazzling-mendel/task2/docs/interview_defense_guide.md)
