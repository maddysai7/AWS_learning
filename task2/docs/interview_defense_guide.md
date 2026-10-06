# Round 2 Technical Interview Walkthrough & Defense Pack
**Candidate:** Sai  
**Assessment:** Practical Cloud Architecture and Application Deployment  
**Project:** StockPulse Cloud Shop Inventory Tracker  

---

## 1. The 60-Second Elevator Pitch

> *"For this assessment, I designed and deployed **StockPulse** — an interactive, multi-employee Shop Inventory and Stock Tracking platform built on a production-grade **3-Tier AWS Architecture**.*
>
> *I approached this not just as a deployment task, but as an end-to-end cloud architecture and security exercise:*
> 1. *At the **Network Tier**, I isolated the database in private subnets with zero internet route, enforced Multi-AZ redundancy, and used **Security Group Chaining** to guarantee least privilege.*
> 2. *At the **Compute Tier**, the application runs as an unprivileged non-root user, continuously monitored by the Application Load Balancer via `/api/health`.*
> 3. *At the **Application Tier**, I implemented a **Zero Trust Authentication Barrier** with PBKDF2 password hashing. All state-changing requests are validated strictly on the server side: if traffic is intercepted in a proxy like Burp Suite to tamper with product IDs or user roles, the server intercepts and blocks the attack with HTTP 403 Forbidden.*
> *The infrastructure is deployed across AWS using 3-tier security group chaining with hardened Docker containerization and health diagnostics."*

---

## 2. Burp Suite Penetration Testing & Traffic Capture Defense

If an attacker or evaluator intercepts traffic in **Burp Suite** and attempts manual tampering, here is how the server handles each attack:

| Attack Scenario in Burp Suite | Intercepted Request | Server Defense Mechanism | Burp Result |
| :--- | :--- | :--- | :--- |
| **BAC: Clerk deletes a product** | `POST /products/1/delete`<br>`Cookie: session=<Bob_Clerk>` | `@require_roles(["admin"])` checks server-side session user in the database. Bob's role is `clerk`. | **403 Forbidden** (Blocked) |
| **BAC: Clerk edits product details** | `POST /products/1/edit`<br>`Cookie: session=<Bob_Clerk>` | Endpoint enforces `@require_roles(["admin"])`. Only Store Managers can update product names, prices, or locations. | **403 Forbidden** (Blocked) |
| **BAC: Privilege Escalation** | `POST /roles/assign-role`<br>`user_id=2&role=admin` | Endpoint enforces `@require_roles(["admin"])`. Only verified Store Managers can modify user records. | **403 Forbidden** (Blocked) |
| **IDOR: Cross-User Note Tampering** | `POST /notes/3/delete`<br>(Where Note 3 was authored by Alex) | `delete_note()` verifies `note["user_id"] == current_user["id"]`. Bob's ID (`2`) does not match author ID (`1`). | **403 Forbidden** (Blocked) |
| **BAC: Auditor adjusts stock** | `POST /products/1/adjust-stock`<br>`action=inc` | `@require_roles(["admin", "clerk"])` checks Clara's role (`auditor`). | **403 Forbidden** (Blocked) |
| **Cookie Manipulation** | Manually editing `user_id` inside the session cookie | Flask signs cookies cryptographically using HMAC with `FLASK_SECRET_KEY`. Any tampered cookie fails signature verification and is discarded. | **302 Redirect to /login** (Invalid Session) |
| **Session Replay After Logout** | Attacker captures cookie/JWT token in Burp, waits for user to click Logout, then replays captured token in Burp Repeater | Server-Side Revocation: When `/logout` is triggered, the server immediately sets `session_token = NULL` in the database. When the replayed token arrives, the server checks the DB, finds no matching active session, and rejects the request. | **302 Redirect to /login** or **401 Unauthorized** (Replay Blocked) |

---

## 3. Top 10 Interview Questions & Model Answers

### Q1: "Can you walk us through the end-to-end request flow when a clerk updates stock?"
**Your Answer:**
> *"When a store employee clicks `+` to increment an item's stock on the web page:*
> 1. *The browser sends an HTTP POST request to the **Application Load Balancer (ALB)** DNS endpoint in the public subnet over port 80/443.*
> 2. *The ALB verifies instance health via `/api/health` and forwards the request over port 5000 to the **App Server** in the private application subnet.*
> 3. *The Flask backend verifies the session cookie to confirm the active role has permission (`@require_roles(['admin', 'clerk'])`).*
> 4. *The backend opens a private connection over port 5432 to the **Amazon RDS PostgreSQL** instance in the isolated database subnet and executes a parameterized SQL UPDATE query.*
> 5. *RDS updates the record, commits, and returns success back through the App Server and ALB to the client UI with zero direct exposure of the database."*

---

### Q2: "Why did you choose a 3-Tier Architecture instead of a single EC2 instance?"
**Your Answer:**
> *"A single-instance deployment creates a single point of failure (SPOF) and violates the principle of separation of concerns. If the web server is compromised, the attacker immediately has root access to the database.*
> 
> *By decoupling into 3 tiers:*
> * **Security Isolation**: The database has no public IP and no route to the Internet Gateway.
> * **Independent Scaling**: If web traffic spikes, we can horizontally scale the web/app tier via an Auto Scaling Group without resizing the database.
> * **Operational Resilience**: Database maintenance, automated backups, and OS patching are handled independently by AWS RDS without taking down the web server."*

---

### Q3: "What is Security Group Chaining, and why is it superior to IP-based firewall rules?"
**Your Answer:**
> *"In beginner setups, people often allow traffic from broad CIDR blocks (like `10.0.0.0/16` or `0.0.0.0/0`).*
> 
> *Instead, I implemented **Security Group Chaining**:*
> * *The Application Load Balancer belongs to `alb-sg`.*
> * *The App Server belongs to `app-sg`, and its ingress rule allows port 5000 **strictly from the source ID of `alb-sg`**.*
> * *The RDS Database belongs to `db-sg`, and its ingress rule allows port 5432 **strictly from the source ID of `app-sg`**.*
> 
> *This ensures that even if another instance is launched inside the same VPC, it cannot connect to the database unless it specifically holds the `app-sg` security group."*

---

### Q4: "How is the database protected from internet-based attacks?"
**Your Answer:**
> *"The database has 3 layers of defense:*
> 1. **Network Layer**: It is assigned to `Isolated DB Subnets` which have NO route to the Internet Gateway (`igw`) or NAT Gateway. It has no public IP address (`publicly_accessible = false`).
> 2. **Transport Layer**: The database security group only accepts TCP traffic on port 5432 from the App Server's security group.
> 3. **Storage Layer**: The database storage volume is encrypted at rest using **AWS KMS (AES-256)**."*

---

### Q5: "How does the Application Load Balancer know when the application is healthy?"
**Your Answer:**
> *"I implemented a custom diagnostics endpoint at `/api/health`. Every 15 seconds, the ALB sends an HTTP GET request to this endpoint.*
> 
> *The endpoint doesn't just return a static 200 string — it runs an active `SELECT 1` query to verify that the database connection pool is alive and measures the round-trip latency. If the database crashes or the server hangs, the health check fails, and the ALB automatically stops routing traffic to that instance."*

---

### Q6: "Why did you implement authentication and server-side authorization checks?"
**Your Answer:**
> *"Hiding buttons on the frontend is never security — an attacker using a tool like Burp Suite or curl can simply craft raw HTTP requests directly to the endpoints.*
> 
> *In StockPulse, all authorization checks occur **strictly on the backend**:*
> * *Even if an unprivileged clerk captures a request in Burp Suite and hits `POST /products/1/delete` or `POST /roles/assign-role`, the server intercepts the request, checks their role in the database, and returns HTTP 403.*
> * *Similarly, object-level authorization on inspection notes prevents an employee from modifying or deleting notes authored by other staff members (IDOR prevention)."*

---

### Q7: "How did you prevent SQL Injection?"
**Your Answer:**
> *"Every single database interaction in `app.py` uses 100% **parameterized queries** (`?` for SQLite, `%s` for PostgreSQL). User inputs are treated strictly as data literals and are never concatenated into raw SQL strings, preventing SQL Injection (OWASP Top 3)."*

---

### Q8: "How are database credentials managed?"
**Your Answer:**
> *"Database credentials are never hardcoded in source code or committed to GitHub. In production, credentials are injected at instance startup via environment variables or retrieved securely from **AWS SSM Parameter Store / AWS Secrets Manager** using an IAM Instance Profile with least-privilege permissions."*

---

### Q9: "If the application received 100,000 visitors tomorrow, how would you scale this?"
**Your Answer:**
> *"1. **Compute Layer**: Convert the EC2 instance into an Auto Scaling Group (ASG) behind the ALB, scaling out based on CPU utilization or target request count.*
> *2. **Database Layer**: Add RDS Read Replicas across multiple AZs to offload heavy read queries (like catalog browsing and search), while directing write queries to the Primary DB.*
> *3. **Edge Layer**: Place **Amazon CloudFront** in front of the ALB to cache static assets (CSS, JS, icons) globally and provide DDoS mitigation via AWS Shield."*

---

### Q10: "What would you add if you had an additional week?"
**Your Answer:**
> *"1. **AWS WAF**: Attach AWS Web Application Firewall to the ALB to block SQLi, XSS, and rate-limit aggressive bots.*
> *2. **Custom Domain with HTTPS (ACM)**: Provision a domain on Route 53 with an SSL/TLS certificate via AWS Certificate Manager for end-to-end TLS encryption.*
> *3. **Container Orchestration**: Migrate the app from EC2 to **AWS ECS Fargate** for true serverless container operations, eliminating OS patching overhead.*
> *4. **CI/CD Pipeline**: Implement a GitHub Actions pipeline with automated security gates (Gitleaks for secrets, Semgrep for SAST, Trivy for container scanning) before deploying to AWS."*

---

### Q11: "When a user logs out, does their JWT or session token automatically expire? How do you prevent replay attacks in Burp Suite?"
**Your Answer:**
> *"In a pure stateless JWT setup, **by default no**: because the token signature is self-contained, client-side logout merely discards the token in the browser. If an attacker intercepted the token in Burp Suite before logout, they could replay it until its `exp` timestamp.*
> 
> *To solve this in StockPulse, we implemented **Server-Side Token Revocation**:*
> * 1. Upon login, a unique cryptographically random `session_token` is generated, saved in the database, and stored in the session/Bearer token.*
> * 2. On `/logout`, the server explicitly sets `session_token = NULL` in the database for that user.*
> * 3. Every subsequent request checks the database to verify that the incoming token matches the user's active session. If an attacker replays the captured token in Burp Suite after the user logged out, the server sees that the active session was destroyed and instantly rejects the request with **302 Redirect to /login** or **HTTP 401 Unauthorized**."*

---

## 4. Live Demo Script (Step-by-Step for the Call)

When they ask you to demonstrate the application:

1. **Show the Security Gate**:
   * Visit the Public URL: Show that unauthenticated visitors are automatically directed to the **Sign In** screen.
   * Sign in as **Bob Jenkins (Floor Staff)** using `bob_clerk` / `clerk123`.
2. **Demonstrate Role Boundaries**:
   * Show that Bob can adjust inventory stock counts using the **`+`** / **`-`** buttons.
   * Go to **Store Team (`/roles`)**: Point out that Bob **cannot** reassign roles or add employees.
   * Attempt to delete a product: Show the **403 Forbidden** permission notice screen!
3. **Demonstrate Relational Comments & Author Ownership**:
   * Open `/products/2/notes`.
   * Add a note as Bob: *"Shelf count verified by floor team"*.
   * Note that Bob only has a delete button on notes he personally created — notes by Alex do not show a delete button, and any tampered delete request is blocked server-side with 403 Forbidden.
4. **Sign Out & Sign in as Alex Mercer (Store Manager)**:
   * Click **Sign Out** and log in with `alex_manager` / `admin123`.
   * Go to **Store Team (`/roles`)**:
     * Show that the Store Manager now has the **Reassign Role dropdown** active.
     * Click **`[ + Invite Team Member ]`** and add a new clerk.
5. **Show the Cloud Architecture**:
   * Open `/api/health` in a new tab: Show the live AWS ALB JSON response with database latency.
   * Open `architecture_diagram.html` to walk through the 3-Tier Multi-AZ architecture, isolated RDS subnets, and security group chaining.
