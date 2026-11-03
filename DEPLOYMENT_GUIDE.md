# Deployment Guide - Coal Mine System

## Prerequisites on New PC
- [ ] Install Python (Add to PATH)
- [ ] Install PostgreSQL 18 (Set password to match .env)
- [ ] Install Git

## Setup Steps
1. Clone the project: `git clone <your-github-link>`
2. Copy the `.env` file from the old PC (Crucial!)
3. Run `setup.bat` (This installs packages, migrates DB, collects static, and sets up Task Scheduler).
4. Install NSSM and set up the `CoalMineServer` Windows Service.
5. Add Firewall Rule: `netsh advfirewall firewall add rule name="Django Waitress" dir=in action=allow protocol=TCP localport=8000`
6. Access via `http://<NEW_PC_IP>:8000`

## Important Security Note
- NEVER commit the `.env` file to GitHub. 
- Backups are located in `E:\CoalMiningProject\backups`. Copy them to a USB weekly.