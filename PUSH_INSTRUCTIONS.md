# Push Instructions — OpsIQ

## 1. Install Git for Windows

Download and install from: https://git-scm.com/download/win

During installation, keep all defaults (Git Bash, PATH, etc.)

## 2. Open a NEW terminal (Git Bash or PowerShell) and run:

```bash
cd "C:\Users\Ismail Sajid\Downloads\ecom-ops-automation-system-main\ecom-ops-automation-system-main"

# Initialize repo
git init
git remote add origin https://github.com/Ismail-2001/ecom-ops-automation-system.git
git branch -M main

# Configure git
git config user.name "Ismail-2001"
git config user.email "ismail@example.com"

# Stage and commit files
git add .
git commit -m "feat: complete CI/CD, PostgreSQL, and monitoring setup"

# Push (will prompt for credentials)
git push -u origin main
```

When prompted:
- Username: `Ismail-2001`
- Password: paste your GitHub Personal Access Token (create a new one at GitHub Settings → Developer Settings → Personal Access Tokens)

## 3. After push, each commit workflow will auto-run on GitHub Actions.
