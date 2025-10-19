# DailyDelights Flask App - AWS EC2 Deployment Guide

Complete guide to dockerize and deploy the DailyDelights inventory management Flask application on AWS EC2.

---

## Prerequisites

### Local Machine:
- Docker installed ([Install Docker](https://docs.docker.com/get-docker/))
- Docker Compose installed
- AWS Account with EC2 access
- SSH key pair for EC2 access

### Required Files:
- `credentials.json` (Google Drive OAuth)
- `token.json` (Google Drive token - will be generated)
- `.env` file with your API keys and configuration

---

## Part 1: Local Testing with Docker

### Step 1: Prepare Environment Variables

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env and add your actual values
nano .env
```

**Required values to update in `.env`:**
```
SECRET_KEY=<generate-a-random-secret-key>
TOGETHER_API_KEY=<your-together-ai-api-key>
TELEGRAM_BOT_TOKEN=<your-telegram-bot-token>
```

**Generate a secure SECRET_KEY:**
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### Step 2: Ensure Required Files Exist

Make sure these files are in the InventoryManagement directory:
```
✓ credentials.json
✓ dailydelights.db
✓ .env
```

### Step 3: Build and Test Locally

```bash
# Build the Docker image
docker-compose build

# Start the container
docker-compose up -d

# Check logs
docker-compose logs -f

# Access the app
open http://localhost:5000
```

### Step 4: Test the Application

1. Open browser to `http://localhost:5000`
2. Login with your credentials
3. Test uploading invoices
4. Test daily book closing
5. Verify all features work

### Step 5: Stop the Container

```bash
docker-compose down
```

---

## Part 2: AWS EC2 Setup

### Step 1: Launch EC2 Instance

1. **Go to AWS Console** → EC2 → Launch Instance

2. **Configure Instance:**
   - **Name**: `dailydelights-flask-app`
   - **AMI**: Ubuntu Server 22.04 LTS (Free tier eligible)
   - **Instance Type**: `t2.micro` (1 vCPU, 1GB RAM) or `t3.small` (2 vCPU, 2GB RAM) - recommended
   - **Key Pair**: Create new or use existing SSH key pair
   - **Network Settings**:
     - Allow SSH (port 22) from your IP
     - Allow HTTP (port 80) from anywhere (0.0.0.0/0)
     - Allow HTTPS (port 443) from anywhere (0.0.0.0/0)
     - Allow Custom TCP (port 5000) from anywhere (for testing)
   - **Storage**: 20 GB gp3 (minimum recommended)

3. **Launch Instance**

4. **Note the Public IP**: `xx.xx.xx.xx`

### Step 2: Connect to EC2 Instance

```bash
# SSH into your EC2 instance
ssh -i /path/to/your-key.pem ubuntu@<EC2-PUBLIC-IP>
```

---

## Part 3: Install Docker on EC2

```bash
# Update system packages
sudo apt-get update
sudo apt-get upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add ubuntu user to docker group
sudo usermod -aG docker ubuntu

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Verify installation
docker --version
docker-compose --version

# Log out and back in for group changes to take effect
exit
```

**Reconnect to EC2:**
```bash
ssh -i /path/to/your-key.pem ubuntu@<EC2-PUBLIC-IP>
```

---

## Part 4: Deploy Application to EC2

### Step 1: Transfer Files to EC2

**On your local machine:**

```bash
# Create a deployment package
cd /path/to/InventoryManagement
tar -czf dailydelights-app.tar.gz \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.DS_Store' \
  --exclude='venv' \
  --exclude='Product_Inventory_Backup_Original' \
  --exclude='logs/*.log' \
  .

# Transfer to EC2
scp -i /path/to/your-key.pem dailydelights-app.tar.gz ubuntu@<EC2-PUBLIC-IP>:~/
```

### Step 2: Extract and Setup on EC2

**On EC2 instance:**

```bash
# Create app directory
mkdir -p ~/dailydelights-app
cd ~/dailydelights-app

# Extract files
tar -xzf ~/dailydelights-app.tar.gz

# Create necessary directories
mkdir -p logs gdrive_invoices

# Set permissions
chmod +x *.py
```

### Step 3: Configure Environment

```bash
# Edit .env file
nano .env

# Make sure all values are correct, especially:
# - SECRET_KEY
# - TOGETHER_API_KEY
# - TELEGRAM_BOT_TOKEN
```

### Step 4: Build and Run Docker Container

```bash
# Build the image
docker-compose build

# Start the container
docker-compose up -d

# Check if container is running
docker ps

# Check logs
docker-compose logs -f flask-app
```

---

## Part 5: Access Your Application

### Test Access

```bash
# From EC2 instance
curl http://localhost:5000

# From your browser
http://<EC2-PUBLIC-IP>:5000
```

**Success!** Your app should now be accessible at `http://<EC2-PUBLIC-IP>:5000`

---

## Part 6: Setup Nginx Reverse Proxy (Optional but Recommended)

### Why Nginx?
- Runs on standard port 80 (HTTP) and 443 (HTTPS)
- Better performance and security
- SSL/TLS certificate support
- Load balancing capability

### Install and Configure Nginx

```bash
# Install Nginx
sudo apt-get install nginx -y

# Create Nginx configuration
sudo nano /etc/nginx/sites-available/dailydelights
```

**Add this configuration:**

```nginx
server {
    listen 80;
    server_name <EC2-PUBLIC-IP>;  # Replace with your domain if you have one

    client_max_body_size 100M;  # Allow large file uploads

    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support (if needed)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Timeouts for long-running processes
        proxy_connect_timeout 600;
        proxy_send_timeout 600;
        proxy_read_timeout 600;
        send_timeout 600;
    }
}
```

**Enable the configuration:**

```bash
# Create symbolic link
sudo ln -s /etc/nginx/sites-available/dailydelights /etc/nginx/sites-enabled/

# Remove default site
sudo rm /etc/nginx/sites-enabled/default

# Test configuration
sudo nginx -t

# Restart Nginx
sudo systemctl restart nginx
sudo systemctl enable nginx
```

**Now access your app at:** `http://<EC2-PUBLIC-IP>`

---

## Part 7: Setup SSL Certificate (Optional - For HTTPS)

### Using Let's Encrypt (Free SSL)

**Prerequisites:**
- You need a domain name (e.g., `dailydelights.yourdomain.com`)
- Point your domain's A record to EC2 Public IP

```bash
# Install Certbot
sudo apt-get install certbot python3-certbot-nginx -y

# Get SSL certificate
sudo certbot --nginx -d dailydelights.yourdomain.com

# Certbot will automatically configure Nginx for HTTPS
# Follow the prompts

# Test auto-renewal
sudo certbot renew --dry-run
```

**Now access your app at:** `https://dailydelights.yourdomain.com`

---

## Part 8: Application Management

### Useful Docker Commands

```bash
# View running containers
docker ps

# View all containers
docker ps -a

# Check logs
docker-compose logs -f

# Restart application
docker-compose restart

# Stop application
docker-compose down

# Rebuild and restart
docker-compose up -d --build

# Execute command in container
docker-compose exec flask-app bash

# View container resource usage
docker stats
```

### Application Updates

```bash
# On local machine - create new package
cd /path/to/InventoryManagement
tar -czf dailydelights-app.tar.gz \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.DS_Store' \
  --exclude='venv' \
  .

# Transfer to EC2
scp -i /path/to/your-key.pem dailydelights-app.tar.gz ubuntu@<EC2-PUBLIC-IP>:~/

# On EC2 - deploy update
cd ~/dailydelights-app
docker-compose down
tar -xzf ~/dailydelights-app.tar.gz
docker-compose up -d --build
```

### Database Backup

```bash
# Backup database
docker-compose exec flask-app sqlite3 /app/dailydelights.db ".backup '/app/backup.db'"

# Copy backup to host
docker cp dailydelights-flask:/app/backup.db ./backup-$(date +%Y%m%d).db

# Download to local machine
scp -i /path/to/your-key.pem ubuntu@<EC2-PUBLIC-IP>:~/dailydelights-app/backup-*.db ./
```

---

## Part 9: Monitoring and Maintenance

### Check Application Status

```bash
# Check if container is running
docker ps

# Check Nginx status
sudo systemctl status nginx

# Check disk space
df -h

# Check memory usage
free -h

# Check application logs
docker-compose logs -f --tail=100
```

### Set Up Auto-Restart

The `docker-compose.yml` already has `restart: unless-stopped`, so containers will auto-restart on failure or server reboot.

### Enable Docker to Start on Boot

```bash
sudo systemctl enable docker
```

---

## Part 10: Security Recommendations

### 1. Update Security Group Rules

In AWS Console → EC2 → Security Groups:
- Remove port 5000 access once Nginx is setup
- Restrict SSH (port 22) to your IP only
- Keep HTTP (80) and HTTPS (443) open to all

### 2. Setup Firewall (UFW)

```bash
# Enable firewall
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable

# Check status
sudo ufw status
```

### 3. Keep System Updated

```bash
# Set up automatic security updates
sudo apt-get install unattended-upgrades -y
sudo dpkg-reconfigure -plow unattended-upgrades
```

### 4. Secure Sensitive Files

```bash
# Set proper permissions
chmod 600 .env
chmod 600 credentials.json
chmod 600 token.json
```

---

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker-compose logs flask-app

# Check if port 5000 is in use
sudo lsof -i :5000

# Rebuild from scratch
docker-compose down
docker system prune -a
docker-compose up -d --build
```

### Database Issues

```bash
# Access database directly
docker-compose exec flask-app sqlite3 /app/dailydelights.db

# Check database integrity
docker-compose exec flask-app sqlite3 /app/dailydelights.db "PRAGMA integrity_check;"
```

### Out of Memory

```bash
# Check memory usage
free -h

# Consider upgrading to t3.small or t3.medium instance
```

### Permission Denied Errors

```bash
# Fix ownership
sudo chown -R ubuntu:ubuntu ~/dailydelights-app

# Restart Docker
sudo systemctl restart docker
```

---

## Cost Estimation (AWS)

### EC2 Instance (Basic t2.micro - Free Tier)
- **1 year free**: $0/month (if eligible for free tier)
- **After free tier**: ~$8-10/month

### EC2 Instance (Recommended t3.small)
- **Cost**: ~$15-20/month
- **2 vCPU, 2GB RAM** - Better performance

### Data Transfer
- **First 1 GB/month**: Free
- **Up to 10 TB/month**: $0.09/GB

### Elastic IP (Static IP)
- **Free while instance is running**
- **$0.005/hour if not attached**: ~$3.60/month

**Estimated Total: $15-25/month** (with t3.small instance)

---

## Next Steps

1. ✅ Test locally with Docker
2. ✅ Launch EC2 instance
3. ✅ Deploy application
4. ✅ Setup Nginx reverse proxy
5. ✅ Configure domain name (optional)
6. ✅ Setup SSL certificate (optional)
7. ✅ Setup monitoring and backups
8. ✅ Test all features
9. ✅ Share access with team

---

## Support

If you encounter issues:
1. Check application logs: `docker-compose logs -f`
2. Check Nginx logs: `sudo tail -f /var/log/nginx/error.log`
3. Verify all credentials are correct in `.env`
4. Ensure all required files are present

**Application is now live and accessible globally!** 🎉
