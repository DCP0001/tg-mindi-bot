# Oracle Cloud Infrastructure (OCI) Deployment Guide

This guide will walk you through provisioning a virtual machine on Oracle Cloud, transferring your code via GitHub, and running your Mindi Telegram Bot.

---

## Part 1: Create a VM Instance on OCI (Step-by-Step)

Since you don't have a VM running yet, follow these steps to create one under Oracle's **Always Free Tier**:

1. Log in to your **Oracle Cloud Infrastructure (OCI) Console**.
2. Open the navigation menu (top-left burger icon) and go to **Compute** -> **Instances**.
3. Click **Create Instance**.
4. Configure the instance:
   * **Name**: `mindi-bot-vm`
   * **Placement**: Keep the default (Availability Domain).
   * **Image and Shape**:
     * Click **Edit** (pencil icon).
     * **Image**: Click **Change Image**, select **Canonical Ubuntu**, and choose **22.04** (standard LTS). Click **Select Image**.
     * **Shape**: Click **Change Shape**.
       * Select **Ampere (ARM-based processor)** -> **VM.Standard.A1.Flex**.
       * Set **OCPUs** to `2` and **Memory (GB)** to `12` (this is fully Always-Free).
       * *Note: If OCI says ARM is out of capacity, select **Specialty and Legacy** -> **VM.Standard.E2.1.Micro** (AMD, 1 OCPU, 1 GB RAM) which is also Always-Free.*
   * **Networking**:
     * Select **Create a new virtual cloud network (VCN)**.
     * Select **Create a new public subnet**.
     * Ensure **Assign a public IPv4 address** is set to **Yes**.
   * **SSH Keys**:
     * Select **Generate a key pair for me**.
     * **CRITICAL**: Click **Save Private Key** and save the `.key`/`.pem` file to your Windows PC (e.g. `C:\Users\dhruv\Documents\mindi_key.key`). You will need this to connect!
5. Click **Create** (at the bottom).
6. Wait 1–2 minutes until the status turns green (**Running**). Note the **Public IP Address** (e.g. `129.153.X.Y`).

---

## Part 2: Open Ports in OCI Console (VCN Ingress List)

By default, OCI blocks all ports except SSH (22). To allow HTTP traffic on port `8000` (FastAPI leaderboard/health):

1. On your VM's details page, look under **Primary VNIC** and click on the **Subnet** link.
2. Under **Security Lists**, click on your **Default Security List for VCN**.
3. Click **Add Ingress Rules**.
4. Configure the rule:
   * **Source Type**: `CIDR`
   * **Source CIDR**: `0.0.0.0/0` (Allows access from anywhere)
   * **IP Protocol**: `TCP`
   * **Source Port Range**: Leave blank (`All`)
   * **Destination Port Range**: `8000`
   * **Description**: `FastAPI Port (Mindi Bot)`
5. Click **Add Ingress Rules**.

---

## Part 3: Push Your Code to GitHub

Make sure your local repository is pushed to GitHub.

1. Create a repository on GitHub (e.g. named `tg-mindi-bot`).
2. Run these commands in your local project folder (`c:\Users\dhruv\OneDrive\Desktop\TG Mindi bot`) using Git Bash or Command Prompt:
   ```bash
   git init
   # Create a .gitignore file if you don't have one to ignore secrets
   echo ".env" >> .gitignore
   echo "__pycache__/" >> .gitignore
   echo "*.session" >> .gitignore
   echo "*.session-journal" >> .gitignore
   
   git add .
   git commit -m "initial commit"
   git branch -M main
   git remote add origin https://github.com/YOUR_GITHUB_USERNAME/tg-mindi-bot.git
   git push -u origin main
   ```

---

## Part 4: Connect to the VM and Clone Your Repository

### 1. Fix SSH Key Permissions on Windows PowerShell
Open Windows PowerShell on your computer and run the following command to secure your private key (required by Windows SSH):
```powershell
icacls "C:\Users\dhruv\Documents\mindi_key.key" /inheritance:r /grant:r "${env:USERNAME}:(R)"
```

### 2. Connect to your VM
Run the following in PowerShell (replace `<VM_PUBLIC_IP>` with your instance's public IP):
```powershell
ssh -i "C:\Users\dhruv\Documents\mindi_key.key" ubuntu@<VM_PUBLIC_IP>
```

### 3. Clone your GitHub repository on the VM
Once logged into the Ubuntu VM, install Git and clone your code:
```bash
sudo apt update && sudo apt install -y git
# If repository is PUBLIC:
git clone https://github.com/YOUR_GITHUB_USERNAME/tg-mindi-bot.git
# If repository is PRIVATE, clone using your Github Username and Personal Access Token (PAT):
# git clone https://USERNAME:TOKEN@github.com/YOUR_GITHUB_USERNAME/tg-mindi-bot.git

cd tg-mindi-bot
```

---

## Part 5: Initialize VM & Deploy

1. **Make scripts executable and run the setup script**:
   ```bash
   chmod +x setup_vm.sh deploy.sh
   sudo ./setup_vm.sh
   ```
   *This installs Docker, Docker Compose, and configures the OS-level firewall rules.*

2. **Re-establish SSH Session**:
   Since the setup script added your user to the `docker` group, you must log out and log back in for changes to apply:
   ```bash
   exit
   ```
   Reconnect:
   ```powershell
   ssh -i "C:\Users\dhruv\Documents\mindi_key.key" ubuntu@<VM_PUBLIC_IP>
   cd tg-mindi-bot
   ```

3. **Configure Environment Variables**:
   Create a `.env` file from the template and open it:
   ```bash
   cp .env.example .env
   nano .env
   ```
   Fill in your actual Telegram credentials:
   ```env
   TELEGRAM_API_ID=XXXXXX
   TELEGRAM_API_HASH=XXXXXXXXXXXXXXXXXX
   TELEGRAM_BOT_TOKEN=XXXXXX:XXXXXXXXXXXXXXXXX
   ```
   *Note: Save by pressing `Ctrl + O` and `Enter`, then exit by pressing `Ctrl + X`.*

4. **Deploy the application**:
   ```bash
   ./deploy.sh
   ```
   The script will boot the bot, database, and Redis cache, then check the health endpoint to confirm everything is running successfully.

---

## Verification & Management

* **Verify it works**:
  In your browser, visit: `http://<VM_PUBLIC_IP>:8000/health`
  It should return `{"status":"online","bot_connected":true,"database":"connected"}`.
* **View bot logs**:
  ```bash
  docker compose logs -f web
  ```
* **Stop the application**:
  ```bash
  docker compose down
  ```
* **Pull updates from GitHub & redeploy**:
  If you push new changes to GitHub, pull them on the server and redeploy:
  ```bash
  git pull
  ./deploy.sh
  ```
