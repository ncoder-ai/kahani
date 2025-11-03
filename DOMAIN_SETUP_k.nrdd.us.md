# Setting up k.nrdd.us with Nginx Proxy Manager

This guide will help you configure `k.nrdd.us` to point to your Kahani app running on `172.16.23.80` using Nginx Proxy Manager (NPM).

## Prerequisites

1. ✅ Nginx Proxy Manager is installed and running (usually accessible at `http://172.16.23.80:81`)
2. ✅ Kahani app is running on `172.16.23.80` (ports 6789 for frontend, 9876 for backend)
3. ✅ You have access to configure DNS for `nrdd.us` domain
4. ✅ You can access the NPM web interface

## Step 1: Configure DNS

At your DNS provider (where `nrdd.us` domain is managed), add an A record:

```
Type: A
Name: k
Value: 172.16.23.80
TTL: 300 (or your preferred TTL)
```

This will point `k.nrdd.us` to `172.16.23.80`.

**Note:** DNS propagation can take a few minutes to a few hours. Verify it's working:
```bash
dig k.nrdd.us
# or
nslookup k.nrdd.us
```

## Step 2: Verify Kahani is Running

Before configuring NPM, verify your app is accessible locally:

```bash
# Check backend
curl http://localhost:9876/health

# Check frontend
curl http://localhost:6789
```

Both should return successful responses.

## Step 3: Configure Nginx Proxy Manager

### 3.1 Access NPM Web UI

1. Open your browser and go to: `http://172.16.23.80:81`
2. Log in with your NPM credentials

### 3.2 Add Proxy Host

1. Click **"Proxy Hosts"** in the top menu
2. Click **"Add Proxy Host"** button

### 3.3 Configure Details Tab

Fill in the following:

- **Domain Names:** `k.nrdd.us`
- **Scheme:** `http`
- **Forward Hostname/IP:** `localhost` (or `127.0.0.1`)
- **Forward Port:** `6789`
- **Cache Assets:** ✅ (optional, recommended)
- **Block Common Exploits:** ✅ (optional, recommended)
- **Websockets Support:** ✅ **IMPORTANT** (required for streaming features)

### 3.4 Add Custom Locations

Click the **"Custom Locations"** tab and add the following locations:

#### Location 1: Backend API
- **Location:** `/api/`
- **Forward Hostname/IP:** `localhost`
- **Forward Port:** `9876`
- **Websockets Support:** ✅ (if available)

#### Location 2: WebSocket Support
- **Location:** `/ws/`
- **Forward Hostname/IP:** `localhost`
- **Forward Port:** `9876`
- **Websockets Support:** ✅ **REQUIRED**

#### Location 3: API Documentation
- **Location:** `/docs`
- **Forward Hostname/IP:** `localhost`
- **Forward Port:** `9876`

#### Location 4: ReDoc Documentation
- **Location:** `/redoc`
- **Forward Hostname/IP:** `localhost`
- **Forward Port:** `9876`

#### Location 5: Health Check
- **Location:** `/health`
- **Forward Hostname/IP:** `localhost`
- **Forward Port:** `9876`

### 3.5 Configure SSL (Recommended)

Click the **"SSL"** tab:

1. **SSL Certificate:** Select "Request a new SSL Certificate"
2. **Force SSL:** ✅ (recommended)
3. **HTTP/2 Support:** ✅ (recommended)
4. **HSTS Enabled:** ✅ (optional, recommended)
5. **HSTS Subdomains:** ✅ (optional)
6. Click **"Save"**

**Note:** SSL certificate will only be issued after DNS is properly configured and propagated.

### 3.6 Save Configuration

Click **"Save"** at the bottom of the page.

## Step 4: Update CORS Settings

Update your Kahani app's CORS configuration to allow the new domain:

### Option A: Using .env file

Edit your `.env` file (in the project root) and update `CORS_ORIGINS`:

```bash
CORS_ORIGINS=["http://k.nrdd.us", "https://k.nrdd.us"]
```

### Option B: Using environment variables

```bash
export CORS_ORIGINS='["http://k.nrdd.us", "https://k.nrdd.us"]'
```

### Restart Kahani App

After updating CORS, restart your app:

```bash
# If using systemd service
sudo systemctl restart kahani

# If running manually
# Stop current process and restart with:
./start-prod.sh
```

## Step 5: Verify Setup

### 5.1 Test DNS Resolution
```bash
curl -I http://k.nrdd.us
# or
ping k.nrdd.us
```

### 5.2 Test Backend Health
```bash
curl https://k.nrdd.us/health
```

### 5.3 Test Frontend
Open `https://k.nrdd.us` in your browser

### 5.4 Test API
```bash
curl https://k.nrdd.us/api/stories
```

## Troubleshooting

### DNS Issues

**Problem:** `k.nrdd.us` doesn't resolve
- **Solution:** Wait for DNS propagation (can take up to 48 hours, usually minutes)
- Verify DNS record: `dig k.nrdd.us` or `nslookup k.nrdd.us`
- Double-check A record is correct at your DNS provider

### 502 Bad Gateway

**Problem:** Getting 502 errors in browser
- **Check:** Kahani app is running: `curl http://localhost:6789` and `curl http://localhost:9876/health`
- **Check:** Ports are correct in NPM (6789 for frontend, 9876 for backend)
- **Check:** Forward hostname/IP is `localhost` or `127.0.0.1`
- **Check:** Firewall allows connections to ports 6789 and 9876

### Connection Refused

**Problem:** Connection refused errors
- **Check:** Kahani app is running on the server
- **Check:** App is listening on `0.0.0.0` or `localhost` (not just external IP)
- **Check:** Firewall settings on the server

### CORS Errors

**Problem:** Browser console shows CORS errors
- **Solution:** Update `CORS_ORIGINS` in `.env` to include `http://k.nrdd.us` and `https://k.nrdd.us`
- **Solution:** Restart Kahani app after updating CORS
- **Verify:** Check backend logs for CORS-related errors

### WebSocket Connection Fails

**Problem:** Streaming/TTS features don't work
- **Check:** "Websockets Support" is enabled in NPM for both main proxy and `/ws/` location
- **Check:** Browser console for WebSocket connection errors
- **Test:** Try accessing WebSocket endpoint directly: `wscat -c ws://k.nrdd.us/ws/tts/test-session-id`

### SSL Certificate Issues

**Problem:** SSL certificate not issuing
- **Check:** DNS is properly configured and propagated (`dig k.nrdd.us`)
- **Check:** Port 80 is accessible from the internet (needed for Let's Encrypt validation)
- **Check:** NPM logs for certificate errors
- **Solution:** Try requesting certificate again after DNS propagates

### 404 Not Found

**Problem:** Frontend loads but API calls return 404
- **Check:** Custom location `/api/` is configured correctly in NPM
- **Check:** Forward port is `9876` (not `6789`)
- **Check:** Trailing slash in location path (`/api/` not `/api`)

## NPM Configuration Summary

Here's what your NPM configuration should look like:

**Main Proxy Host:**
- Domain: `k.nrdd.us`
- Forward to: `localhost:6789`
- Websockets: ✅

**Custom Locations:**
1. `/api/` → `localhost:9876` (Websockets: ✅)
2. `/ws/` → `localhost:9876` (Websockets: ✅)
3. `/docs` → `localhost:9876`
4. `/redoc` → `localhost:9876`
5. `/health` → `localhost:9876`

## Summary

After completing these steps:
- ✅ DNS points `k.nrdd.us` → `172.16.23.80`
- ✅ NPM proxies requests to your Kahani app
- ✅ SSL certificate configured (if DNS propagated)
- ✅ App accessible at `https://k.nrdd.us` (or `http://k.nrdd.us`)

Your Kahani app should now be accessible at `https://k.nrdd.us`! 🚀

## Additional Notes

- **Port Access:** Make sure ports 80 and 443 are open in your firewall for NPM to receive traffic
- **Internal Ports:** Ports 6789 and 9876 don't need to be exposed externally - NPM handles that
- **Updates:** If you change Kahani ports, update the NPM configuration accordingly
- **Monitoring:** Check NPM logs in the web UI for any connection issues

