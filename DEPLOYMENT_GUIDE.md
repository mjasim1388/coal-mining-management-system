# 🚀 Deployment Guide - Coal Mine Management System

This guide explains how to install and run the Coal Mine System on a new Windows PC. 

---

## 📋 Prerequisites (What you need before starting)
1. **The Project Folder:** Ensure you have the complete `CoalMiningProject` folder (containing `.env`, `db_password.txt`, `backups/`, and `Servy/`).
2. **Internet Connection:** Required to download Python, PostgreSQL, and required packages.
3. **Administrator Access:** You must be logged in as a Windows Administrator.

---

## ⚡ Method 1: The "One-Click" Installer (Recommended)

This method uses our automated script (`install.bat`) to do everything for you.

### Step 1: Copy the Folder
Copy the entire `CoalMiningProject` folder to the new PC. (We recommend placing it exactly at `E:\CoalMiningProject` so the paths match).

### Step 2: Run the Installer
1. Open the `E:\CoalMiningProject` folder.
2. Right-click on **`install.bat`** and select **Run as Administrator**.
3. A black command window will open and start downloading Python and PostgreSQL.
4. The script will automatically:
   * Install Python & PostgreSQL.
   * Install all required Python packages.
   * Restore the latest database backup (using the password in `db_password.txt`).
   * Collect static files (CSS/JS).
   * Open Windows Firewall on port 8000.
   * Install and start the background Windows Service (Servy).

### Step 3: Verify
1. Wait for the script to say **"INSTALLATION COMPLETE!"**.
2. Open your browser and go to `http://localhost:8000`. 
3. The system should be live!

---

## 🛠️ Method 2: Manual Installation (If the script fails)

If `install.bat` fails for any reason (e.g., `winget` is blocked by antivirus), follow these manual steps:

1. **Install Python:** Download from python.org. **Crucial:** Check "Add Python to PATH".
2. **Install PostgreSQL:** Download the installer. When prompted, set the password to match the one in your `db_password.txt`.
3. **Open PowerShell** in `E:\CoalMiningProject` and run:
   ```powershell
   pip install -r requirements.txt