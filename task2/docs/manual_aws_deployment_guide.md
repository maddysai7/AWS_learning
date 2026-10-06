# StockPulse — Manual AWS Console Deployment Guide
### Complete Step-by-Step 3-Tier Production Setup Without Terraform

This guide provides the exact click-by-click instructions to manually deploy the **StockPulse** Store Inventory Management application on AWS using the **AWS Management Console** and a manually built **Docker** container.

---

## 🏗️ Architecture Blueprint Overview

```
                      INTERNET / USERS
                            │
                            ▼
              ┌───────────────────────────┐
              │ Application Load Balancer │  (Public Subnets across 2 AZs)
              │   stockpulse-alb-sg       │  Port: 80 / 443 (from 0.0.0.0/0)
              └─────────────┬─────────────┘
                            │ Target Group: Port 5000 (Health Check: /api/health)
                            ▼
              ┌───────────────────────────┐
              │   EC2 Compute Engine      │  (App Subnet)
              │   stockpulse-app-sg       │  Port: 5000 (ONLY from alb-sg)
              │   Docker Container        │  Non-root user (appuser)
              └─────────────┬─────────────┘
                            │ SQL Connection: Port 5432 (pg_hba / TCP)
                            ▼
              ┌───────────────────────────┐
              │   Amazon RDS PostgreSQL   │  (Isolated DB Subnets, No Public IP)
              │   stockpulse-db-sg        │  Port: 5432 (ONLY from app-sg)
              └───────────────────────────┘
```

---

## 📋 Prerequisites Checklist
1. An AWS Account with administrative access.
2. AWS Region: `us-east-1` (N. Virginia) or your preferred region (e.g., `ap-south-1`).
3. An EC2 Key Pair created in your selected region (e.g., `stockpulse-key.pem`).
4. Git repository URL containing the `task2/` code: `https://github.com/maddysai7/devsecops_learn.git`

---

## STEP 1: Create the VPC & Subnets (Network Tier)

### 1.1 Create the VPC
1. Go to **AWS Console** ➔ **VPC** ➔ Click **Create VPC**.
2. Select **VPC only**.
3. **Name tag**: `stockpulse-vpc`
4. **IPv4 CIDR block**: `10.0.0.0/16`
5. Click **Create VPC**.

### 1.2 Create 6 Subnets across 2 Availability Zones (AZs)
Go to **VPC** ➔ **Subnets** ➔ Click **Create subnet** (Select `stockpulse-vpc`):

| Subnet Name | Availability Zone | CIDR Block | Purpose |
|---|---|---|---|
| `stockpulse-public-1` | `us-east-1a` | `10.0.1.0/24` | ALB (AZ 1) |
| `stockpulse-public-2` | `us-east-1b` | `10.0.2.0/24` | ALB (AZ 2) |
| `stockpulse-app-1` | `us-east-1a` | `10.0.10.0/24` | EC2 App Server (AZ 1) |
| `stockpulse-app-2` | `us-east-1b` | `10.0.20.0/24` | EC2 Standby (AZ 2) |
| `stockpulse-db-1` | `us-east-1a` | `10.0.30.0/24` | RDS PostgreSQL Primary |
| `stockpulse-db-2` | `us-east-1b` | `10.0.40.0/24` | RDS PostgreSQL Secondary |

> **Tip for Public Subnets**: Select `stockpulse-public-1` ➔ **Actions** ➔ **Edit subnet settings** ➔ Check **Enable auto-assign public IPv4 address** ➔ Save. Repeat for `stockpulse-public-2`.

### 1.3 Create & Attach Internet Gateway (IGW)
1. Go to **VPC** ➔ **Internet gateways** ➔ Click **Create internet gateway**.
2. **Name tag**: `stockpulse-igw` ➔ Click **Create internet gateway**.
3. Click **Actions** ➔ **Attach to VPC** ➔ Select `stockpulse-vpc` ➔ Click **Attach internet gateway**.

### 1.4 Configure Route Tables
1. **Public Route Table**:
   - Go to **VPC** ➔ **Route tables** ➔ Click **Create route table**.
   - **Name**: `stockpulse-public-rt`, VPC: `stockpulse-vpc`.
   - Click **Routes** tab ➔ **Edit routes** ➔ **Add route**:
     - Destination: `0.0.0.0/0`
     - Target: **Internet Gateway** ➔ Select `stockpulse-igw`.
   - Click **Subnet associations** tab ➔ **Edit subnet associations** ➔ Select both `stockpulse-public-1` and `stockpulse-public-2` ➔ Click **Save associations**.

---

## STEP 2: Configure Chained Security Groups (Zero Trust)

Create 3 distinct Security Groups in `stockpulse-vpc` under **EC2** ➔ **Security Groups**:

### 2.1 ALB Security Group (`stockpulse-alb-sg`)
- **VPC**: `stockpulse-vpc`
- **Description**: `Public internet ingress for ALB`
- **Inbound Rules**:
  - Type: **HTTP** | Port: `80` | Source: `Anywhere-IPv4` (`0.0.0.0/0`)
  - Type: **HTTPS** | Port: `443` | Source: `Anywhere-IPv4` (`0.0.0.0/0`)

### 2.2 App Server Security Group (`stockpulse-app-sg`)
- **VPC**: `stockpulse-vpc`
- **Description**: `Compute engine ingress strictly from ALB`
- **Inbound Rules**:
  - Type: **Custom TCP** | Port: `5000` | Source: Select **Custom** ➔ Type `stockpulse-alb-sg` (Select the ALB Security Group ID)
  - Type: **SSH** | Port: `22` | Source: **My IP** (for secure administrative SSH access)

### 2.3 Database Security Group (`stockpulse-db-sg`)
- **VPC**: `stockpulse-vpc`
- **Description**: `PostgreSQL database ingress strictly from App Server`
- **Inbound Rules**:
  - Type: **PostgreSQL** | Port: `5432` | Source: Select **Custom** ➔ Type `stockpulse-app-sg` (Select the App Security Group ID)

> 💡 **Interview Talking Point**: Notice how `stockpulse-db-sg` accepts traffic **ONLY** from `stockpulse-app-sg`, and `stockpulse-app-sg` accepts traffic **ONLY** from `stockpulse-alb-sg`. Direct public traffic to the App Server or Database is mathematically impossible at the hypervisor layer.

---

## STEP 3: Create Amazon RDS PostgreSQL Database (Tier 3)

### 3.1 Create DB Subnet Group
1. Go to **RDS** ➔ **Subnet groups** ➔ Click **Create DB subnet group**.
2. **Name**: `stockpulse-db-subnet-group`
3. **VPC**: `stockpulse-vpc`
4. **Availability Zones**: Select your 2 AZs (e.g. `us-east-1a` and `us-east-1b`).
5. **Subnets**: Select `10.0.30.0/24` (`stockpulse-db-1`) and `10.0.40.0/24` (`stockpulse-db-2`).
6. Click **Create**.

### 3.2 Launch the PostgreSQL Database
1. Go to **RDS** ➔ **Databases** ➔ Click **Create database**.
2. Choose **Standard create**.
3. **Engine type**: **PostgreSQL** (Version: 15.x or 16.x).
4. **Templates**: **Free tier**.
5. **Settings**:
   - DB instance identifier: `stockpulse-db`
   - Master username: `postgres`
   - Master password: `StockPulseSecure2026!` (or your chosen password)
6. **Instance configuration**: `db.t3.micro` or `db.t4g.micro`.
7. **Storage**: General Purpose SSD (`gp3`), 20 GiB.
8. **Connectivity**:
   - VPC: `stockpulse-vpc`
   - DB Subnet group: `stockpulse-db-subnet-group`
   - **Public access**: **No** (Strict security: Zero internet access)
   - Existing VPC security groups: Select `stockpulse-db-sg` (Remove `default`).
9. **Additional configuration**:
   - Initial database name: `stockpulse`
   - Enable encryption: Checked (AWS KMS)
10. Click **Create database**.

> ⏳ *RDS provisioning takes ~5–10 minutes. While it creates, proceed to Step 4.*
> When created, copy the **Endpoint** (e.g., `stockpulse-db.cxxxxxxx.us-east-1.rds.amazonaws.com`).

---

## STEP 4: Launch EC2 Instance & Build Docker Image (Tier 2)

### 4.1 Launch the EC2 Instance
1. Go to **EC2** ➔ **Instances** ➔ Click **Launch instances**.
2. **Name**: `stockpulse-app-server`
3. **AMI**: **Amazon Linux 2023** (x86_64) or **Ubuntu 24.04 LTS**.
4. **Instance type**: `t3.micro` or `t2.micro` (Free tier eligible).
5. **Key pair**: Select your existing key pair (e.g. `stockpulse-key`).
6. **Network settings** ➔ Click **Edit**:
   - VPC: `stockpulse-vpc`
   - Subnet: `stockpulse-public-1` *(Enables internet access to run `git clone` & `docker build` without requiring a paid NAT Gateway)*
   - Auto-assign public IP: **Enable**
   - Firewall (security groups): **Select existing security group** ➔ Choose `stockpulse-app-sg`.
7. **Storage**: 20 GiB `gp3` (Encrypted: Yes).
8. Click **Launch instance**.

### 4.2 SSH into EC2 & Install Docker
Connect to your EC2 instance from your terminal:
```bash
ssh -i /path/to/stockpulse-key.pem ec2-user@<EC2-PUBLIC-IP>
```
*(If Ubuntu, use `ubuntu@<EC2-PUBLIC-IP>`)*

Install Docker and Git (Amazon Linux 2023):
```bash
sudo dnf update -y
sudo dnf install -y docker git
sudo systemctl enable --now docker
sudo usermod -aG docker ec2-user
newgrp docker
```
*(Verify Docker runs without sudo: `docker ps`)*

### 4.3 Clone the Repository & Build Docker Image Manually
Run these commands inside your EC2 terminal:

```bash
# 1. Clone the repository
git clone https://github.com/maddysai7/devsecops_learn.git
cd devsecops_learn/task2

# 2. Build the Docker container image locally
docker build -t stockpulse:latest .

# 3. Verify the newly built image
docker images
```

### 4.4 Run the Docker Container Connected to Amazon RDS
Run the container passing your RDS credentials:

```bash
docker run -d \
  --name stockpulse-app \
  -p 5000:5000 \
  -e DB_HOST="<PASTE_YOUR_RDS_ENDPOINT_HERE>" \
  -e DB_PORT="5432" \
  -e DB_NAME="stockpulse" \
  -e DB_USER="postgres" \
  -e DB_PASSWORD="StockPulseSecure2026!" \
  -e AWS_REGION="us-east-1" \
  -e FLASK_SECRET_KEY="stockpulse-cloud-production-secret-9821" \
  --restart unless-stopped \
  stockpulse:latest
```

### 4.5 Verify Local Container Health
Test the health endpoint from inside the EC2 instance:
```bash
curl http://localhost:5000/api/health
```
**Expected Response:**
```json
{
  "status": "healthy",
  "service": "StockPulse Cloud Inventory",
  "version": "2.1.0",
  "cloud_provider": "AWS",
  "database": {
    "engine": "PostgreSQL (RDS)",
    "latency_ms": 3.42,
    "status": "connected"
  }
}
```
> If you see `"engine": "PostgreSQL (RDS)"` and `"status": "connected"`, your App Server and RDS Database are communicating perfectly!

---

## STEP 5: Create Application Load Balancer & Target Group (Tier 1)

### 5.1 Create Target Group
1. Go to **EC2** ➔ **Target Groups** (under Load Balancing) ➔ Click **Create target group**.
2. **Target type**: **Instances**
3. **Target group name**: `stockpulse-tg`
4. **Protocol**: `HTTP` | **Port**: `5000`
5. **VPC**: Select `stockpulse-vpc`
6. **Health checks**:
   - Health check protocol: `HTTP`
   - Health check path: `/api/health`
7. Expand **Advanced health check settings**:
   - Healthy threshold: `2`
   - Unhealthy threshold: `2`
   - Timeout: `5` seconds
   - Interval: `15` seconds
   - Success codes: `200`
8. Click **Next**.
9. In **Available instances**: Select `stockpulse-app-server` ➔ Click **Include as pending below** (Port 5000).
10. Click **Create target group**.

### 5.2 Create the Application Load Balancer
1. Go to **EC2** ➔ **Load Balancers** ➔ Click **Create load balancer**.
2. Select **Application Load Balancer** ➔ Click **Create**.
3. **Load balancer name**: `stockpulse-alb`
4. **Scheme**: **Internet-facing**
5. **IP address type**: **IPv4**
6. **Network mapping**:
   - VPC: `stockpulse-vpc`
   - Mappings: Select **both** Availability Zones:
     - `us-east-1a`: Select `stockpulse-public-1`
     - `us-east-1b`: Select `stockpulse-public-2`
7. **Security groups**:
   - Select `stockpulse-alb-sg`
   - Deselect `default`
8. **Listeners and routing**:
   - Protocol: `HTTP` | Port: `80`
   - Default action: Forward to **`stockpulse-tg`**
9. Click **Create load balancer**.

---

## STEP 6: Verify Deployment & Obtain Public URL

1. Go to **EC2** ➔ **Target Groups** ➔ Select `stockpulse-tg` ➔ Click the **Targets** tab.
   - Wait ~30–60 seconds.
   - Target status should change to **Healthy (green)**!
2. Go to **EC2** ➔ **Load Balancers** ➔ Select `stockpulse-alb`.
3. Under the **Description** tab, copy the **DNS name**, for example:
   ```
   stockpulse-alb-198273645.us-east-1.elb.amazonaws.com
   ```
4. Open the DNS name in your browser:
   - **Application**: `http://stockpulse-alb-198273645.us-east-1.elb.amazonaws.com/`
   - **Live Health Diagnostics**: `http://stockpulse-alb-198273645.us-east-1.elb.amazonaws.com/api/health`

---

## 🧪 Testing User Logins & Burp Suite Defense

Once live on your ALB URL:

| Role | Username | Password | Permitted Actions | Blocked Actions (Burp Tampering) |
|---|---|---|---|---|
| **Store Manager** | `alex_manager` | `admin123` | Full CRUD, Reassign Roles, Delete Products, Delete any note | None |
| **Floor Staff** | `bob_clerk` | `clerk123` | Adjust stock `[+]`/`[-]`, Add notes, Edit/Delete own notes | Delete Product (HTTP 403), Modify Team Roles (HTTP 403), Delete another's note (HTTP 403) |
| **Auditor** | `clara_auditor` | `auditor123` | Read-only inventory view, Export CSV, Post inspection notes | Adjust Stock (HTTP 403), Add/Delete Product (HTTP 403), Edit Team Roles (HTTP 403) |

---

## 🛠️ Handy Docker Maintenance Commands on EC2

```bash
# View live application logs
docker logs -f stockpulse-app

# Restart the application container
docker restart stockpulse-app

# Rebuild container after pulling fresh code
git pull origin main
docker stop stockpulse-app
docker rm stockpulse-app
docker build -t stockpulse:latest .
docker run -d --name stockpulse-app -p 5000:5000 ... (same run command)
```
