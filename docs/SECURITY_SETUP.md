# Security Setup Guide

Complete guide for securing your Kahani deployment for production use.

## Table of Contents

- [Quick Start](#quick-start)
- [Generating Secrets](#generating-secrets)
- [CORS Configuration](#cors-configuration)
- [Environment Variables](#environment-variables)
- [Deployment Scenarios](#deployment-scenarios)
- [Security Best Practices](#security-best-practices)

---

## Quick Start

### 1. Generate Strong Secrets

**Required for all deployments:**

```bash
# Linux/macOS - Generate secrets
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(32))"
python3 -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_urlsafe(32))"

# Alternative: Using OpenSSL
openssl rand -base64 32
openssl rand -base64 32
```

**Windows (PowerShell):**

```powershell
# Generate random secrets
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(32))"
python -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_urlsafe(32))"
```

**Copy the output** and add to your `.env` file (see below).

### 2. Create .env File

Copy the example file and add your secrets:

```bash
# Copy template
cp .env.example .env

# Edit with your secrets
nano .env  # or vim, code, etc.
```

### 3. Configure CORS

Set CORS to match where users access your app:

```bash
# In .env file
CORS_ORIGINS=["https://kahani.yourdomain.com"]
```

See [CORS Configuration](#cors-configuration) for detailed examples.

---

## Generating Secrets

### What Are These Secrets?

- **SECRET_KEY**: General application encryption (future use)
- **JWT_SECRET_KEY**: Signs authentication tokens (critical!)

**Important:** Never use default values in production!

### Generation Methods

#### Method 1: Python (Recommended)

```bash
# Generate both secrets at once
python3 << 'EOF'
import secrets
print("# Add these to your .env file:")
print(f"SECRET_KEY={secrets.token_urlsafe(32)}")
print(f"JWT_SECRET_KEY={secrets.token_urlsafe(32)}")
EOF
```

#### Method 2: OpenSSL

```bash
echo "SECRET_KEY=$(openssl rand -base64 32)"
echo "JWT_SECRET_KEY=$(openssl rand -base64 32)"
```

#### Method 3: Online Generator

Visit: https://www.random.org/strings/
- Generate 2 strings
- 32 characters minimum
- Use alphanumeric + special characters

**⚠️ Warning:** Online generators are less secure than local generation.

### Secret Requirements

✅ **Good Secrets:**
- At least 32 characters
- Random, unpredictable
- Unique per deployment
- Never committed to git

❌ **Bad Secrets:**
```
SECRET_KEY=change-this-secret-key
JWT_SECRET_KEY=password123
SECRET_KEY=mysecret
```

---

## CORS Configuration

### What is CORS?

Cross-Origin Resource Sharing controls which domains can access your API.

### Common Scenarios

#### Scenario 1: Reverse Proxy (Most Common)

**Setup:** Nginx/Caddy on `https://kahani.yourdomain.com`

```bash
# .env
CORS_ORIGINS=["https://kahani.yourdomain.com"]
```

#### Scenario 2: Homelab with Local Domain

**Setup:** mDNS or local DNS at `http://kahani.local`

```bash
# .env
CORS_ORIGINS=["http://kahani.local", "http://kahani.local:6789"]
```

#### Scenario 3: IP Address Access

**Setup:** Access via `http://192.168.1.100`

```bash
# .env
CORS_ORIGINS=["http://192.168.1.100", "http://192.168.1.100:6789"]
```

#### Scenario 4: Multiple Access Points

**Setup:** Domain + IP + localhost for development

```bash
# .env
CORS_ORIGINS=["https://kahani.yourdomain.com", "http://192.168.1.100", "http://localhost:6789"]
```

#### Scenario 5: Tailscale/VPN

**Setup:** Access via Tailscale hostname

```bash
# .env
CORS_ORIGINS=["http://kahani.tailnet-name.ts.net", "https://kahani.tailnet-name.ts.net"]
```

### CORS Format

**Array Format (Recommended):**
```bash
CORS_ORIGINS=["https://example.com", "https://www.example.com"]
```

**Comma-Separated Format:**
```bash
CORS_ORIGINS=https://example.com,https://www.example.com
```

**Allow All (Development Only):**
```bash
CORS_ORIGINS=*
```

⚠️ **Never use `*` in production!** It allows any website to access your API.

### Testing CORS

```bash
# Test from your browser's console
fetch('http://your-kahani-ip:9876/health')
  .then(r => r.json())
  .then(console.log)
  .catch(console.error)

# Should see: {status: "healthy", app: "Kahani", ...}
# If CORS error: Update CORS_ORIGINS
```

---

## Environment Variables

### Required Variables

```bash
# Security (REQUIRED - no defaults)
SECRET_KEY=your-generated-secret-here
JWT_SECRET_KEY=your-generated-jwt-secret-here

# Database (REQUIRED)
DATABASE_URL=postgresql://kahani:kahani@localhost:5432/kahani
```

### Optional Variables

```bash
# Network Configuration
CORS_ORIGINS=["http://localhost:6789"]
PORT=9876

# Feature Flags
ENABLE_REGISTRATION=true
DEBUG=false

# Token Expiration (minutes/days)
ACCESS_TOKEN_EXPIRE_MINUTES=120
REFRESH_TOKEN_EXPIRE_DAYS=30

# Semantic Memory
ENABLE_SEMANTIC_MEMORY=true
```

### Security-Related Variables

```bash
# Disable registration after first user
ENABLE_REGISTRATION=false

# Disable debug mode in production
DEBUG=false

# Shorter token expiration for higher security
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

---

## Deployment Scenarios

### Homelab - Behind Reverse Proxy

**Architecture:**
```
Internet → Router → Reverse Proxy (HTTPS) → Kahani (HTTP localhost)
```

**Requirements:**
- Reverse proxy with SSL (Nginx/Caddy/NPM)
- Domain name or local DNS
- Firewall rules (80/443 open)

**Configuration:**

```bash
# .env
SECRET_KEY=<generated>
JWT_SECRET_KEY=<generated>
DATABASE_URL=postgresql://kahani:kahani@localhost:5432/kahani
CORS_ORIGINS=["https://kahani.yourdomain.com"]
DEBUG=false
```

**Reverse Proxy handles:**
- SSL/TLS termination
- HTTPS enforcement
- Rate limiting (optional)

**Kahani handles:**
- Authentication
- Authorization
- API logic

**Security Level:** ⭐⭐⭐⭐ High (recommended)

---

### Homelab - Direct Access (No Proxy)

**Architecture:**
```
Local Network → Kahani (HTTP)
```

**Requirements:**
- Kahani running on local network
- Access via IP or hostname
- Not exposed to internet

**Configuration:**

```bash
# .env
SECRET_KEY=<generated>
JWT_SECRET_KEY=<generated>
DATABASE_URL=postgresql://kahani:kahani@localhost:5432/kahani
CORS_ORIGINS=["http://192.168.1.100", "http://192.168.1.100:6789"]
DEBUG=false
```

**Security Considerations:**
- HTTP acceptable (local network only)
- Still use strong secrets
- Enable firewall on host
- Don't port forward to internet

**Security Level:** ⭐⭐⭐ Medium (local network only)

---

### VPS/Cloud - Production Deployment

**Architecture:**
```
Internet → Reverse Proxy (HTTPS) → Kahani (HTTP localhost)
```

**Requirements:**
- VPS or cloud server
- Domain name with valid SSL
- Reverse proxy (Nginx/Caddy)
- Firewall configured

**Configuration:**

```bash
# .env
SECRET_KEY=<generated>
JWT_SECRET_KEY=<generated>
DATABASE_URL=postgresql://user:pass@localhost:5432/kahani
CORS_ORIGINS=["https://kahani.yourdomain.com"]
DEBUG=false
ENABLE_REGISTRATION=false  # Disable after creating accounts
ACCESS_TOKEN_EXPIRE_MINUTES=30  # Shorter for security
```

**Additional Security:**
- Regular backups
- Monitoring and alerts
- Fail2ban for brute force protection
- Regular security updates

**Security Level:** ⭐⭐⭐⭐⭐ Production (full security)

---

### Docker Deployment

**Important:** Docker Compose **requires** `.env` file with secrets.

```bash
# 1. Create .env file
cp .env.example .env

# 2. Generate and add secrets
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(32))" >> .env
python3 -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_urlsafe(32))" >> .env

# 3. Configure CORS
echo 'CORS_ORIGINS=["https://your-domain.com"]' >> .env

# 4. Start containers
docker compose up -d

# ❌ This will FAIL (intentionally):
# docker compose up -d  # Without .env
# Error: SECRET_KEY environment variable is required
```

---

## Security Best Practices

### ✅ Do This

1. **Generate unique secrets** for each deployment
2. **Use strong secrets** (32+ characters, random)
3. **Restrict CORS** to your actual domain/IP
4. **Disable debug mode** in production (`DEBUG=false`)
5. **Use HTTPS** via reverse proxy
6. **Regular backups** of database
7. **Keep software updated** (docker pull, git pull)
8. **Use PostgreSQL** for production deployments
9. **Monitor logs** for suspicious activity
10. **Limit registration** after creating accounts

### ❌ Don't Do This

1. ❌ Use default/example secrets
2. ❌ Use `CORS_ORIGINS=*` in production
3. ❌ Expose port 9876 to internet directly
4. ❌ Enable debug mode in production
5. ❌ Commit `.env` to git
6. ❌ Share secrets in chat/email
7. ❌ Use HTTP without reverse proxy on internet
8. ❌ Reuse secrets across deployments
9. ❌ Skip backups
10. ❌ Ignore security updates

---

## First-Time Setup Checklist

Follow this checklist for your first deployment:

- [ ] Generate strong SECRET_KEY
- [ ] Generate strong JWT_SECRET_KEY
- [ ] Create .env file with secrets
- [ ] Configure CORS_ORIGINS for your domain/IP
- [ ] Set DEBUG=false for production
- [ ] Install and configure reverse proxy (if applicable)
- [ ] Obtain SSL certificate (Let's Encrypt)
- [ ] Configure firewall rules
- [ ] Test access from browser
- [ ] Register first user (becomes admin)
- [ ] Disable registration (optional): `ENABLE_REGISTRATION=false`
- [ ] Set up database backups
- [ ] Review [SECURITY_CHECKLIST.md](SECURITY_CHECKLIST.md)

---

## Troubleshooting

### Docker Compose Fails to Start

**Error:** `SECRET_KEY environment variable is required`

**Solution:**
```bash
# Create .env file with secrets
cp .env.example .env
# Edit .env and add your generated secrets
```

### CORS Errors in Browser

**Error:** `Access to fetch at 'http://...' from origin 'http://...' has been blocked by CORS policy`

**Solution:**
```bash
# Update CORS_ORIGINS in .env
CORS_ORIGINS=["http://your-actual-domain-or-ip"]
# Restart application
docker compose restart  # or restart manually
```

### Can't Access /docs or /redoc

**Behavior:** API documentation not loading

**Explanation:** Disabled in production mode (`DEBUG=false`)

**Solution (if needed for testing):**
```bash
# Temporarily enable debug mode
DEBUG=true
# Restart application
# Remember to disable again: DEBUG=false
```

---

## Getting Help

- **Documentation:** Check [PRODUCTION_DEPLOYMENT.md](../PRODUCTION_DEPLOYMENT.md)
- **Reverse Proxy:** See [REVERSE_PROXY_GUIDE.md](REVERSE_PROXY_GUIDE.md)
- **Security Checklist:** Review [SECURITY_CHECKLIST.md](SECURITY_CHECKLIST.md)
- **Issues:** Open an issue on GitHub with `[SECURITY]` tag

---

## Security Updates

Check for security updates regularly:

```bash
# Update Kahani
cd /path/to/kahani
git pull
docker compose pull  # For Docker deployments
docker compose up -d --build

# Or for baremetal
./build-prod.sh
./start-prod.sh
```

**Subscribe to security advisories** on GitHub to receive notifications.

