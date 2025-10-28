# Reverse Proxy Integration Guide

**Quick Start Guide** - Deploy Kahani behind a reverse proxy with **zero app changes required**.

## 🚀 Quick Start

Kahani is **reverse proxy ready** out of the box! Just configure your reverse proxy to forward traffic:

- **Frontend:** `http://your-server:6789`
- **Backend API:** `http://your-server:9876/api/`
- **WebSocket:** `http://your-server:9876/ws/`

## 📋 Table of Contents

- [Quick Setup](#quick-setup)
- [Nginx](#nginx-configuration)
- [Caddy](#caddy-configuration)
- [Nginx Proxy Manager (NPM)](#nginx-proxy-manager-npm)
- [Docker Deployments](#docker-deployments)
- [Troubleshooting](#troubleshooting)

---

## Quick Setup

### Prerequisites
- Kahani running (Docker or baremetal)
- Domain name pointed to your server
- Reverse proxy installed

### Verify Kahani is Running
```bash
# Check backend
curl http://localhost:9876/health

# Check frontend  
curl http://localhost:6789
```

### Architecture
```
Internet → Reverse Proxy (80/443) → Frontend (6789)
                                   → Backend (9876)
                                   → WebSocket (9876/ws)
```

---

## Nginx Configuration

### Installation
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install nginx

# CentOS/RHEL
sudo yum install nginx
```

### Configuration File

Create `/etc/nginx/sites-available/kahani`:

```nginx
server {
    listen 80;
    server_name kahani.yourdomain.com;

    # Frontend
    location / {
        proxy_pass http://localhost:6789;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Backend API
    location /api/ {
        proxy_pass http://localhost:9876/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket for TTS streaming
    location /ws/ {
        proxy_pass http://localhost:9876/ws/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # API Documentation
    location /docs {
        proxy_pass http://localhost:9876/docs;
    }

    location /redoc {
        proxy_pass http://localhost:9876/redoc;
    }

    # Health check
    location /health {
        proxy_pass http://localhost:9876/health;
    }
}
```

### Enable and Test

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/kahani /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Reload nginx
sudo systemctl reload nginx
```

### SSL Certificate (Optional)

```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx

# Get certificate
sudo certbot --nginx -d kahani.yourdomain.com
```

---

## Caddy Configuration

Caddy automatically handles SSL certificates via Let's Encrypt!

### Installation

```bash
# Ubuntu/Debian
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy
```

### Configuration File

Create/edit `/etc/caddy/Caddyfile`:

```caddy
kahani.yourdomain.com {
    # Frontend
    handle /* {
        reverse_proxy localhost:6789
    }

    # Backend API
    handle /api/* {
        reverse_proxy localhost:9876
    }

    # WebSocket for TTS
    handle /ws/* {
        reverse_proxy localhost:9876
    }

    # API Documentation
    handle /docs {
        reverse_proxy localhost:9876
    }

    handle /redoc {
        reverse_proxy localhost:9876
    }

    # Health check
    handle /health {
        reverse_proxy localhost:9876
    }
}
```

### Start Caddy

```bash
# Reload configuration
sudo systemctl reload caddy

# Check status
sudo systemctl status caddy

# View logs
sudo journalctl -u caddy -f
```

---

## Nginx Proxy Manager (NPM)

NPM provides a web UI for managing nginx reverse proxies.

### Setup Steps

1. **Access NPM Web UI** (usually at http://your-server:81)

2. **Add Proxy Host**
   - Click "Proxy Hosts" → "Add Proxy Host"
   
3. **Details Tab:**
   - **Domain Names:** `kahani.yourdomain.com`
   - **Scheme:** `http`
   - **Forward Hostname/IP:** Your server IP or `localhost`
   - **Forward Port:** `6789` (frontend port)
   - **Websockets Support:** ✅

4. **Custom Locations:**

   Click "Custom Locations" tab and add:

   **Backend API:**
   ```
   Location: /api/
   Forward Hostname/IP: localhost
   Forward Port: 9876
   ```

   **WebSocket:**
   ```
   Location: /ws/
   Forward Hostname/IP: localhost
   Forward Port: 9876
   ```

   **API Docs:**
   ```
   Location: /docs
   Forward Hostname/IP: localhost
   Forward Port: 9876
   ```

   **Health Check:**
   ```
   Location: /health
   Forward Hostname/IP: localhost
   Forward Port: 9876
   ```

5. **SSL Tab:** Request SSL certificate and enable HTTPS

6. **Save** and test your configuration

---

## Docker Deployments

### External Reverse Proxy

Configure your reverse proxy to point to:
- **Frontend:** `your-server-ip:6789`
- **Backend:** `your-server-ip:9876`

### Internal Nginx Container

Add nginx to your `docker-compose.yml`:

```yaml
services:
  nginx:
    image: nginx:alpine
    container_name: kahani-nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.prod.conf:/etc/nginx/nginx.conf:ro
    depends_on:
      - backend
      - frontend
    networks:
      - kahani-network
```

---

## Troubleshooting

### Common Issues

**Frontend Can't Connect to Backend:**
- Check browser console for API URL being called
- Verify reverse proxy is forwarding `/api/` correctly
- Test: `curl http://localhost:6789` and `curl http://localhost:9876/health`

**WebSocket Connection Fails:**
- Ensure proxy supports WebSocket upgrades
- Check proxy headers include `Upgrade` and `Connection`
- Test: `wscat -c ws://localhost:9876/ws/tts/test-session-id`

**502 Bad Gateway:**
- Check if backend/frontend services are running
- Verify port numbers in proxy config
- Check nginx error logs: `sudo tail -f /var/log/nginx/error.log`

**SSL Certificate Errors:**
- Verify domain DNS is correct
- Renew certificates: `sudo certbot renew`

---

## Testing Your Setup

1. **Health Check:** `curl https://kahani.yourdomain.com/health`
2. **API Test:** `curl https://kahani.yourdomain.com/api/stories`
3. **Frontend:** Open browser to `https://kahani.yourdomain.com`
4. **WebSocket:** Test TTS functionality in the app

---

**That's it!** Your Kahani app is now ready for reverse proxy deployment. 🚀

