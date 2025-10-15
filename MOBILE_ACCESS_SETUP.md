# Mobile/Tablet Access Setup

## Problem
When accessing the app from mobile devices, iPads, or other computers on the same network, no stories appear even though they're visible on the development machine.

## Root Cause
- The frontend was using hardcoded `localhost:8000` URLs
- `localhost` refers to the device itself, not your development machine
- Mobile/tablet devices couldn't reach the backend API

## Solution

### 1. Find Your Development Machine's IP Address

On macOS/Linux:
```bash
ifconfig | grep "inet " | grep -v 127.0.0.1
```

On Windows:
```bash
ipconfig
```

Look for your local network IP (usually `192.168.x.x` or `172.16.x.x`)

### 2. Update Frontend Environment Variable

Edit `frontend/.env.local`:
```bash
# Replace with your machine's IP address
NEXT_PUBLIC_API_URL=http://YOUR_IP_HERE:8000

# Example:
NEXT_PUBLIC_API_URL=http://192.168.1.100:8000
```

### 3. Configure Backend to Accept External Connections

Make sure your backend is running with `--host 0.0.0.0`:

```bash
# In backend directory
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Or update your VS Code task in `.vscode/tasks.json`:
```json
{
  "label": "Start Backend Server",
  "type": "shell",
  "command": "cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
}
```

### 4. Restart Frontend

After changing `.env.local`, restart your Next.js dev server:
```bash
# Stop the current server (Ctrl+C) and restart
cd frontend
npm run dev
```

### 5. Access from Mobile/Tablet

On your mobile device or tablet, navigate to:
```
http://YOUR_IP_HERE:3000
```

Example:
```
http://192.168.1.100:3000
```

## Verification

1. Check frontend is using correct API URL:
   - Open browser console on mobile device
   - Look for API request logs showing your IP address
   
2. Test backend is accessible:
   - Visit `http://YOUR_IP:8000/docs` from mobile device
   - Should see FastAPI Swagger docs

## Firewall Notes

If you still can't connect:

### macOS
```bash
# Allow incoming connections on ports 3000 and 8000
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --add /path/to/node
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --add /path/to/python
```

### Windows
- Open Windows Firewall
- Allow ports 3000 and 8000 for incoming connections

### Linux
```bash
# Using ufw
sudo ufw allow 3000
sudo ufw allow 8000
```

## Fixed Files

The following files have been updated to use `API_BASE_URL` instead of hardcoded `localhost:8000`:

- ✅ `frontend/src/app/dashboard/page.tsx`
- ✅ `frontend/src/lib/api.ts` (exports API_BASE_URL)
- ✅ `frontend/src/hooks/useTTS.ts` (already using env var)

## Production Deployment

For production, set the environment variable appropriately:

```bash
# Vercel/Netlify
NEXT_PUBLIC_API_URL=https://your-api-domain.com

# Docker Compose
NEXT_PUBLIC_API_URL=http://backend:8000
```

## Testing

1. On development machine:
   ```bash
   curl http://localhost:8000/docs
   # Should work
   ```

2. On mobile device (replace with your IP):
   ```bash
   curl http://192.168.1.100:8000/docs
   # Should work if configured correctly
   ```

3. Check frontend console logs - should see API requests going to your IP, not localhost
