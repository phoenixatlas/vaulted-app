# Deploy-Time Env Values (DO NOT COMMIT TO GIT)

> This file is in `/app/memory/` which is workspace-only and not pushed to GitHub.
> These values will be entered into Railway/Vercel dashboards by the user.

## MongoDB Atlas
- **MONGO_URL** = `mongodb+srv://oumarsanii_db_user:YW8sEKGSBeJPnQSj@cluster0.s9r8j83.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0`
- **DB_NAME** = `vaulted`
- Username: `oumarsanii_db_user`
- IP Allowlist: `0.0.0.0/0` (set during cluster creation)
- Created: 2026-06-26
- **TODO after deploy**: rotate password & tighten IP allowlist to Railway's egress range
