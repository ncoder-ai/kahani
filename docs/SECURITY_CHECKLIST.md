# Security Deployment Checklist

Quick reference checklist for secure Kahani deployment.

## Pre-Deployment Checklist

### 🔐 Secrets & Authentication

- [ ] **Generated strong SECRET_KEY** (32+ characters)
  ```bash
  python3 -c "import secrets; print(secrets.token_urlsafe(32))"
  ```

- [ ] **Generated strong JWT_SECRET_KEY** (32+ characters)
  ```bash
  python3 -c "import secrets; print(secrets.token_urlsafe(32))"
  ```

- [ ] **Created .env file** with generated secrets
  ```bash
  cp .env.example .env
  # Add your secrets to .env
  ```

- [ ] **Verified .env not tracked by git**
  ```bash
  git status  # .env should not appear
  ```

- [ ] **Set appropriate token expiration**
  - Homelab: 120 minutes (default) ✅
  - Production: 30 minutes recommended
  ```bash
  ACCESS_TOKEN_EXPIRE_MINUTES=30
  ```

---

### 🌐 Network & CORS

- [ ] **Configured CORS_ORIGINS** for your domain/IP
  - ❌ Not using `CORS_ORIGINS=*`
  - ✅ Using specific domain: `["https://kahani.yourdomain.com"]`
  
  ```bash
  # Examples:
  CORS_ORIGINS=["https://kahani.yourdomain.com"]  # Reverse proxy
  CORS_ORIGINS=["http://192.168.1.100"]           # Local IP
  CORS_ORIGINS=["http://kahani.local"]            # mDNS
  ```

- [ ] **Firewall configured**
  ```bash
  # Allow only necessary ports
  sudo ufw allow 80/tcp    # HTTP (redirects to HTTPS)
  sudo ufw allow 443/tcp   # HTTPS
  sudo ufw deny 9876/tcp   # Block direct backend access
  sudo ufw deny 6789/tcp   # Block direct frontend access
  sudo ufw enable
  ```

- [ ] **Reverse proxy configured** (if applicable)
  - [ ] Nginx/Caddy/NPM installed
  - [ ] SSL certificate obtained
  - [ ] HTTPS redirect enabled
  - [ ] WebSocket support enabled

---

### 🔒 SSL/TLS (If Using Reverse Proxy)

- [ ] **SSL certificate obtained**
  ```bash
  # Let's Encrypt example:
  sudo certbot --nginx -d kahani.yourdomain.com
  ```

- [ ] **HTTPS redirect enabled** in reverse proxy
  ```nginx
  # Nginx example:
  return 301 https://$server_name$request_uri;
  ```

- [ ] **Certificate auto-renewal configured**
  ```bash
  # Test renewal
  sudo certbot renew --dry-run
  ```

---

### ⚙️ Application Configuration

- [ ] **Debug mode disabled for production**
  ```bash
  DEBUG=false
  ```

- [ ] **Database configured properly**
  - SQLite: `DATABASE_URL=sqlite:///./data/kahani.db`
  - PostgreSQL: `DATABASE_URL=postgresql://user:pass@localhost:5432/kahani`

- [ ] **Registration settings configured**
  ```bash
  ENABLE_REGISTRATION=true   # Initially
  # Disable after creating accounts if desired
  ```

- [ ] **LLM provider configured** (if using external)
  ```bash
  LLM_BASE_URL=http://your-llm-server:1234/v1
  LLM_API_KEY=your-api-key
  ```

---

### 🐳 Docker-Specific (If Using Docker)

- [ ] **.env file created** in project root
- [ ] **Secrets defined** in .env (not in docker-compose.yml)
- [ ] **Volumes configured** for persistence
  - `./data:/app/data`
  - `./logs:/app/logs`
- [ ] **Container networking** verified
  ```bash
  docker-compose ps  # All services running
  ```

---

## Post-Deployment Verification

### ✅ Basic Functionality

- [ ] **Application accessible** via your URL
  ```bash
  curl https://kahani.yourdomain.com
  # or
  curl http://192.168.1.100:6789
  ```

- [ ] **Backend API responding**
  ```bash
  curl https://kahani.yourdomain.com/health
  # Expected: {"status":"healthy","app":"Kahani",...}
  ```

- [ ] **Frontend loading** in browser
  - Open https://kahani.yourdomain.com
  - Should see login/register page

- [ ] **Can register first user**
  - First user becomes admin automatically
  - Login successful

---

### 🔐 Security Verification

- [ ] **HTTPS working** (if using reverse proxy)
  - Padlock icon in browser
  - Certificate valid
  - No mixed content warnings

- [ ] **CORS properly restricted**
  - Open browser console on different domain
  - Try: `fetch('https://your-kahani.com/health')`
  - Should fail with CORS error (this is good!)

- [ ] **API docs disabled** in production (if DEBUG=false)
  - Visit: `https://your-kahani.com/docs`
  - Should return 404 or redirect
  - ⚠️ If accessible, check DEBUG setting

- [ ] **JWT tokens working**
  - Login as user
  - Verify access to authenticated endpoints
  - Logout works

- [ ] **Authentication required** for protected endpoints
  ```bash
  # Without token - should fail
  curl https://your-kahani.com/api/stories
  # Expected: 401 Unauthorized
  ```

---

### 📊 Monitoring

- [ ] **Logs accessible**
  ```bash
  # Docker
  docker-compose logs -f backend
  
  # Systemd
  sudo journalctl -u kahani -f
  
  # Direct
  tail -f backend/logs/kahani.log
  ```

- [ ] **No errors in logs** on startup
- [ ] **Health endpoint responding**
  ```bash
  watch -n 5 'curl -s http://localhost:9876/health | jq'
  ```

---

### 💾 Backup Configuration

- [ ] **Database backup script created**
  ```bash
  # Example backup script
  #!/bin/bash
  DATE=$(date +%Y%m%d)
  cp /path/to/kahani.db /path/to/backups/kahani-$DATE.db
  ```

- [ ] **Automated backup scheduled**
  ```bash
  # Crontab example (daily at 2 AM)
  0 2 * * * /path/to/backup-script.sh
  ```

- [ ] **Backup restoration tested**
  ```bash
  # Test restore in dev environment
  cp backup.db kahani.db
  # Verify application works
  ```

---

## Security Hardening (Optional)

### 🛡️ Additional Security Measures

- [ ] **Fail2ban configured** (for SSH protection)
  ```bash
  sudo apt install fail2ban
  sudo systemctl enable fail2ban
  ```

- [ ] **Rate limiting enabled** in reverse proxy
  ```nginx
  # Nginx example in nginx.prod.conf
  limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
  limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;
  ```

- [ ] **Intrusion detection** installed (optional)
  ```bash
  sudo apt install aide  # or OSSEC
  ```

- [ ] **Log monitoring** configured (optional)
  - Centralized logging (ELK, Graylog)
  - Alert on suspicious activity

- [ ] **Regular security updates** scheduled
  ```bash
  # Check for updates weekly
  git pull
  docker-compose pull
  ```

---

## Homelab-Specific Considerations

### ✅ Homelab Deployment (Lower Risk)

If deploying on local network only:

- [ ] Firewall blocks external access to ports 6789, 9876
- [ ] Router does NOT port forward Kahani
- [ ] Network segmentation (optional): Kahani on isolated VLAN
- [ ] Access restricted to VPN only (optional)

**Acceptable for homelab:**
- ✅ HTTP instead of HTTPS (on local network)
- ✅ SQLite instead of PostgreSQL
- ✅ 120-minute token expiration
- ✅ Debug mode enabled temporarily for troubleshooting

**Still required:**
- ✅ Strong secrets (SECRET_KEY, JWT_SECRET_KEY)
- ✅ CORS restricted to your IP/domain
- ✅ Regular backups

---

## Production Deployment (High Risk)

### ✅ Internet-Facing Deployment

If exposing to internet:

- [ ] **SSL/TLS mandatory** (valid certificate)
- [ ] **PostgreSQL recommended** (instead of SQLite)
- [ ] **Shorter token expiration** (30 minutes)
- [ ] **Debug mode disabled** (DEBUG=false)
- [ ] **Registration disabled** after account creation
- [ ] **Regular security audits**
- [ ] **Monitoring and alerting** configured
- [ ] **Incident response plan** documented
- [ ] **DDoS protection** (Cloudflare, etc.)

---

## Ongoing Maintenance Checklist

### 📅 Weekly

- [ ] Check logs for errors/warnings
- [ ] Verify backups completed
- [ ] Check disk space usage

### 📅 Monthly

- [ ] Update Kahani (git pull + rebuild)
- [ ] Update system packages
- [ ] Review access logs for suspicious activity
- [ ] Test backup restoration

### 📅 Quarterly

- [ ] Rotate secrets (if paranoid)
- [ ] Security audit review
- [ ] Update SSL certificates (if manual)
- [ ] Review user accounts and permissions

---

## Emergency Procedures

### 🚨 If Security Breach Suspected

1. **Immediately:**
   ```bash
   # Stop application
   docker-compose down
   # or
   sudo systemctl stop kahani
   ```

2. **Investigate:**
   - Check logs: `tail -f backend/logs/kahani.log`
   - Review recent logins
   - Check database for unauthorized changes

3. **Remediate:**
   - Change all secrets
   - Force all users to re-login (tokens expire)
   - Review and update CORS settings
   - Patch any vulnerabilities

4. **Restore:**
   ```bash
   # Backup current state
   cp -r /path/to/kahani /path/to/kahani-compromised
   
   # Restore from backup if needed
   cp /path/to/backups/kahani-last-known-good.db data/kahani.db
   
   # Start with new secrets
   ```

---

## Quick Reference

### Essential Commands

```bash
# View logs
docker-compose logs -f backend          # Docker
tail -f backend/logs/kahani.log         # Direct

# Restart application
docker-compose restart                   # Docker
sudo systemctl restart kahani           # Systemd

# Check health
curl http://localhost:9876/health

# Generate secrets
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Database backup
cp backend/data/kahani.db backups/kahani-$(date +%Y%m%d).db
```

---

## Resources

- **Setup Guide:** [SECURITY_SETUP.md](SECURITY_SETUP.md)
- **Production Deployment:** [PRODUCTION_DEPLOYMENT.md](../PRODUCTION_DEPLOYMENT.md)
- **Reverse Proxy:** [REVERSE_PROXY_GUIDE.md](REVERSE_PROXY_GUIDE.md)
- **Configuration:** [CONFIGURATION_GUIDE.md](../CONFIGURATION_GUIDE.md)

---

## Need Help?

If you're unsure about any security aspect:

1. Review documentation links above
2. Check existing GitHub issues
3. Open new issue with `[SECURITY]` tag
4. **Never share secrets in issues/chat**

---

**Last Updated:** 2025-01-28
**Version:** 1.0

