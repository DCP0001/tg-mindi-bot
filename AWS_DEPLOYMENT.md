# AWS EC2 Deployment Guide

This guide walks you through provisioning an Amazon Web Services (AWS) EC2 Virtual Machine, configuring networking, securing your access key, cloning the project, and launching the **Mindi Telegram Bot** via Docker Compose.

---

## Part 1: Provision an EC2 VM Instance on AWS

To run your bot on a stable virtual machine within the AWS Free Tier, follow these steps:

1. Log in to your **[AWS Management Console](https://console.aws.amazon.com/)**.
2. Search for and navigate to the **EC2 Console** dashboard.
3. Click the orange **Launch instance** button.
4. Configure the instance details:
   * **Name**: `mindi-bot-server`
   * **Application and OS Images (Amazon Machine Image)**:
     * Search for **Ubuntu**.
     * Select **Ubuntu Server 22.04 LTS (HVM), SSD Volume Type** (Make sure it is marked as *Free tier eligible*).
     * **Architecture**: `64-bit (x86)`
   * **Instance Type**:
     * Choose `t2.micro` (or `t3.micro` depending on your region's Free Tier availability).
   * **Key Pair (login)**:
     * Click **Create new key pair**.
     * **Key pair name**: `mindi-aws-key`
     * **Key pair type**: `RSA`
     * **Private key file format**: `.pem`
     * Click **Create key pair**.
     * **CRITICAL**: The key file will automatically download (e.g. `mindi-aws-key.pem`). Save it to a secure place on your Windows PC, such as your user profile or documents directory (e.g., `C:\Users\dhruv\Documents\mindi-aws-key.pem`).
   * **Network Settings**:
     * Under **Firewall (security groups)**, select **Create security group**.
     * Check **Allow SSH traffic from** -> Select **Anywhere (0.0.0.0/0)** or your specific IP address for maximum security.
     * Keep other defaults as-is.
5. Click **Launch Instance** in the Summary panel on the right.
6. Click **View all instances** at the bottom. Once the instance state turns green (**Running**), select it and copy its **Public IPv4 address** (e.g., `54.210.X.Y`).

---

## Part 2: Open Ports in AWS Security Group

By default, AWS blocks all incoming ports except SSH (22). To let players or external tools access your FastAPI leaderboard/health check endpoints on port `8000`:

1. Select your EC2 instance in the list, click the **Security** tab in the details pane below.
2. Click on the link under **Security groups** (e.g. `sg-xxxxxxxxxxxxxx`).
3. Click the **Inbound rules** tab and select **Edit inbound rules**.
4. Click **Add rule**:
   * **Type**: `Custom TCP`
   * **Port range**: `8000`
   * **Source**: `Anywhere-IPv4` (`0.0.0.0/0`)
   * **Description**: `FastAPI Port (Mindi Bot)`
5. Click **Save rules**.

---

## Part 3: Connect to the EC2 Instance via Windows PowerShell

### 1. Fix SSH Key Permissions on Windows
Windows requires strict permissions on private key files to prevent unauthorized reading. Run the following command in PowerShell on your local computer to restrict permission to just your user:

```powershell
icacls "C:\Users\dhruv\Documents\mindi-aws-key.pem" /inheritance:r /grant:r "${env:USERNAME}:(R)"
```

### 2. Connect via SSH
Connect to your EC2 instance (replace `<EC2_PUBLIC_IP>` with the public IP you copied earlier):

```powershell
ssh -i "C:\Users\dhruv\Documents\mindi-aws-key.pem" ubuntu@<EC2_PUBLIC_IP>
```

---

## Part 4: Clone the Repository on the Server

Once logged into your Ubuntu EC2 instance, install Git, clone the code, and navigate to the project directory:

```bash
# Update local packages
sudo apt update && sudo apt install -y git

# Clone the repository
# (If public)
git clone https://github.com/DCP0001/tg-mindi-bot.git

# (If private, authenticate using your GitHub Username and Personal Access Token)
# git clone https://DCP0001:YOUR_PAT_TOKEN@github.com/DCP0001/tg-mindi-bot.git

# Enter workspace
cd tg-mindi-bot
```

---

## Part 5: Initialize the VM & Deploy

1. **Make scripts executable and run the setup script**:
   ```bash
   chmod +x setup_vm.sh deploy.sh
   sudo ./setup_vm.sh
   ```
   *This script automatically updates the system, installs Docker & Docker Compose, sets up permissions, and configures UFW/iptables.*

2. **Re-establish the SSH Session**:
   Since the setup script added your user to the `docker` group, you must log out and reconnect for group changes to apply:
   ```bash
   exit
   ```
   
   Reconnect using PowerShell:
   ```powershell
   ssh -i "C:\Users\dhruv\Documents\mindi-aws-key.pem" ubuntu@<EC2_PUBLIC_IP>
   cd tg-mindi-bot
   ```

3. **Configure Environment Variables**:
   Create a `.env` file from the example template and open it:
   ```bash
   cp .env.example .env
   nano .env
   ```
   Provide your specific Telegram API and bot details:
   ```env
   TELEGRAM_API_ID=XXXXXX
   TELEGRAM_API_HASH=XXXXXXXXXXXXXXXXXX
   TELEGRAM_BOT_TOKEN=XXXXXX:XXXXXXXXXXXXXXXXX
   ```
   *To save and close in nano: Press `Ctrl + O`, hit `Enter`, and press `Ctrl + X`.*

4. **Deploy the application**:
   ```bash
   ./deploy.sh
   ```
   The docker containers will build and start in the background. The deployment script will wait and confirm the bot's health check status.

---

## Verification & Maintenance

* **Check Health Status**:
  In your local browser, check the health endpoint: `http://<EC2_PUBLIC_IP>:8000/health`
  It should return:
  ```json
  {"status":"online","bot_connected":true,"database":"connected"}
  ```
* **View Container Logs**:
  To monitor your bot's behavior and inspect running operations:
  ```bash
  docker compose logs -f web
  ```
* **Shutdown Containers**:
  To stop the application and clean resources:
  ```bash
  docker compose down
  ```
* **Pulling Updates**:
  If you push new commits to GitHub from your local PC, pull them on the server and redeploy:
  ```bash
  git pull
  ./deploy.sh
  ```
