# StockPulse — Cloud Shop Inventory & Stock Tracker
### Round 2 Practical Cloud Architecture & Application Deployment Assessment

A production-grade, 3-tier cloud web application designed for AWS, featuring Role-Based Access Control, Insecure Direct Object Reference (IDOR) prevention, and hardened Docker containerization.

---

## 📁 Folder Structure

```
task2/
├── app.py                      # Main Python 3.11 Flask Application (CRUD, Roles, Notes, RDS PostgreSQL/SQLite)
├── requirements.txt            # Python dependencies (Flask, Gunicorn, psycopg2-binary)
├── Dockerfile                  # Hardened Dockerfile (runs as non-root user: appuser)
├── .dockerignore               # Ignores local venv, SQLite db, cache from Docker build
├── run_local.sh                # Local execution helper script
│
├── templates/                  # Frontend Web UI (Tailwind CSS, Humanized Retail Design)
│   ├── layout.html             # Base layout with humanized store sidebar, logged-in badge & Sign Out
│   ├── index.html              # Store inventory dashboard (Valuation, KPIs, Restock queue, Staff notes)
│   ├── products.html           # Inventory Catalog (Search, filters, inline [+] / [-] buttons, modal)
│   ├── product_notes.html      # Relational Notes / Comments (1-to-many DB relation & IDOR defense)
│   ├── roles.html              # Store Team Directory & Role Management (Store Manager only)
│   ├── login.html              # Clean Store Sign-in with 1-click demo account switcher
│   └── error.html              # Clean "Permission Required" 403 page
│
└── docs/                       # Official Assessment Deliverables
    ├── manual_aws_deployment_guide.md # Step-by-step AWS Management Console setup guide
    ├── architecture_diagram.html # High-resolution visual AWS architecture diagram
    ├── architecture_diagram.md   # Full technical specification & network topology document
    └── interview_defense_guide.md# Top 10 interview questions & model answers cheat sheet
```

---

## 🐳 How to Build & Run with Docker (Manually)

### 1. Build the Docker Image Locally
```bash
cd task2
docker build -t stockpulse:latest .
```

### 2. Run the Container Locally (SQLite Mode)
```bash
docker run -d \
  --name stockpulse-app \
  -p 5000:5000 \
  stockpulse:latest
```

### 3. Or Run the Container Connected to an AWS RDS PostgreSQL Database
```bash
docker run -d \
  --name stockpulse-app \
  -p 5000:5000 \
  -e DB_HOST="your-rds-endpoint.rds.amazonaws.com" \
  -e DB_PORT="5432" \
  -e DB_NAME="stockpulse" \
  -e DB_USER="postgres" \
  -e DB_PASSWORD="YourPasswordHere" \
  -e AWS_REGION="us-east-1" \
  -e FLASK_SECRET_KEY="stockpulse-secret-key-123" \
  stockpulse:latest
```

### 4. Verify Local Container:
- Open `http://localhost:5000/`
- Test health diagnostics: `http://localhost:5000/api/health`

---

## 💻 How to Run Locally with Python Virtualenv

1. Create and activate a Python virtual environment:
   ```bash
   cd task2
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Start the application:
   ```bash
   python3 app.py
   # or with Gunicorn:
   gunicorn --workers 2 --bind 0.0.0.0:5000 app:app
   ```

3. Open your browser to:
   - **Login**: `http://localhost:5000/login`
   - **Dashboard**: `http://localhost:5000/`
   - **Catalog**: `http://localhost:5000/products`
   - **Store Team**: `http://localhost:5000/roles`
   - **Health Check**: `http://localhost:5000/api/health`

---

## ☁️ How to Deploy to AWS (Manual Console Walkthrough)

> For full, step-by-step click instructions with exact field values, see [docs/manual_aws_deployment_guide.md](docs/manual_aws_deployment_guide.md).

### Summary of Manual AWS Console Steps:
1. **Network (VPC & Subnets)**:
   - Create VPC `10.0.0.0/16`.
   - Create 6 Subnets across 2 AZs (2 Public for ALB, 2 Private for EC2, 2 Isolated Private for RDS).
   - Create Internet Gateway & attach to VPC. Add default route (`0.0.0.0/0` ➔ IGW) to Public Subnets.

2. **Security Groups (Chained Zero-Trust Model)**:
   - `stockpulse-alb-sg`: Allows port `80`/`443` from `0.0.0.0/0`.
   - `stockpulse-app-sg`: Allows port `5000` **ONLY** from `stockpulse-alb-sg`, plus port `22` from My IP.
   - `stockpulse-db-sg`: Allows port `5432` **ONLY** from `stockpulse-app-sg`.

3. **Database Tier (Amazon RDS PostgreSQL)**:
   - Create DB Subnet Group with the 2 isolated DB subnets.
   - Launch PostgreSQL (`db.t3.micro` Free Tier), Public Access: **No**, Security Group: `stockpulse-db-sg`.

4. **Compute Tier (EC2 App Server + Docker)**:
   - Launch Amazon Linux 2023 (`t3.micro`) with `stockpulse-app-sg`.
   - SSH into the instance, install Docker & Git.
   - Clone repo and build Docker image manually:
     ```bash
     git clone https://github.com/maddysai7/devsecops_learn.git
     cd devsecops_learn/task2
     docker build -t stockpulse:latest .
     docker run -d --name stockpulse-app -p 5000:5000 \
       -e DB_HOST=<RDS_ENDPOINT> -e DB_NAME=stockpulse -e DB_USER=postgres -e DB_PASSWORD=<PASS> \
       stockpulse:latest
     ```

5. **Load Balancer Tier (Application Load Balancer)**:
   - Create Target Group on port 5000 with Health Check `/api/health`. Register the EC2 instance.
   - Create Internet-facing ALB in Public Subnets with `stockpulse-alb-sg`. Forward port 80 to Target Group.
   - Obtain the public ALB DNS URL (e.g. `http://stockpulse-alb-xxxx.us-east-1.elb.amazonaws.com`).

---

## 🛡️ Key Architecture & Security Justifications

1. **True 3-Tier Multi-AZ Architecture**:
   - **Tier 1 (Public)**: Application Load Balancer across 2 AZs.
   - **Tier 2 (Compute)**: Hardened Docker container running Gunicorn WSGI as non-root `appuser`.
   - **Tier 3 (Data)**: Amazon RDS PostgreSQL isolated with zero internet access.
2. **Security Group Chaining**:
   - Web traffic enters strictly via ALB.
   - EC2 allows port 5000 strictly from ALB Security Group.
   - RDS allows port 5432 strictly from EC2 Security Group.
3. **AppSec Defenses**:
   - **Broken Access Control**: Only Store Managers can delete products or change roles. Floor staff and auditors receive HTTP 403 Forbidden on tamper attempts.
   - **IDOR Prevention**: Staff can only edit/delete their own inspection notes.
   - **Container Hardening**: Runs as unprivileged non-root user (`USER appuser`) adhering to CIS Docker Benchmarks.
