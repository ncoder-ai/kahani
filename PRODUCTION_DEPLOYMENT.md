# Kahani Production Deployment Guide

This guide covers deploying Kahani on baremetal servers for production use.

**🔒 Security First:** Before deploying, review the [Security Setup Guide](docs/SECURITY_SETUP.md) and [Security Checklist](docs/SECURITY_CHECKLIST.md).

## Quick Start

### 1. Initial Setup
```bash
# Clone and install
git clone <repository-url> /opt/kahani
cd /opt/kahani
./install.sh

# Build for production
./build-prod.sh

# Start production server
./start-prod.sh
```

### 2. System Service (Recommended)
```bash
# Create system user
sudo useradd -r -s /bin/false -d /opt/kahani kahani

# Set ownership
sudo chown -R kahani:kahani /opt/kahani

# Install systemd service
sudo cp kahani.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable kahani
sudo systemctl start kahani

# Check status
sudo systemctl status kahani
```

## Production Scripts

### `start-prod.sh`
Production startup script with optimizations:
- ✅ Builds frontend if not already built
- ✅ Runs database migrations
- ✅ Uses production Next.js server (`next start`)
- ✅ Runs backend with multiple workers (4 workers)
- ✅ No hot reload (better performance)
- ✅ Health checks and verification
- ✅ Process monitoring

### `build-prod.sh`
Production build script:
- ✅ Runs database migrations
- ✅ Downloads AI models
- ✅ Builds frontend for production
- ✅ Verifies build success

## Production vs Development

| Feature | Development (`start-dev.sh`) | Production (`start-prod.sh`) |
|---------|------------------------------|------------------------------|
| Frontend | `npm run dev` (hot reload) | `next start` (built app) |
| Backend | Single worker + reload | 4 workers, no reload |
| Build | Not required | Required (`build-prod.sh`) |
| Performance | Optimized for development | Optimized for production |
| Monitoring | Basic | Enhanced with PIDs |

## Configuration

### Environment Variables

**⚠️ Important:** Generate strong secrets before deploying!

```bash
# 1. Copy template
cp .env.example .env

# 2. Generate strong secrets (see docs/SECURITY_SETUP.md for details)
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(32))"
python3 -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_urlsafe(32))"

# 3. Edit .env and add your generated secrets
nano .env
```

**Minimum required configuration:**
```bash
# Security - REQUIRED (no defaults!)
SECRET_KEY=<your-generated-secret-here>
JWT_SECRET_KEY=<your-generated-jwt-secret-here>

# Database
DATABASE_URL=sqlite:///opt/kahani/backend/data/kahani.db

# CORS - Set to your actual domain/IP
CORS_ORIGINS=["https://kahani.yourdomain.com"]

# Production mode
DEBUG=false

# Optional: External LLM service
LLM_BASE_URL=http://your-llm-server:1234
LLM_API_KEY=your-api-key
```

**📖 For detailed configuration guide, see:**
- [Security Setup Guide](docs/SECURITY_SETUP.md) - Generate secrets, configure CORS
- [Configuration Guide](CONFIGURATION_GUIDE.md) - All available options

### Port Configuration
Default ports (configurable in `config.yaml`):
- Frontend: `6789`
- Backend API: `9876`

### Firewall Setup
```bash
# Allow HTTP/HTTPS traffic
sudo ufw allow 80
sudo ufw allow 443

# Allow Kahani ports (if not using reverse proxy)
sudo ufw allow 6789
sudo ufw allow 9876
```

## Reverse Proxy (Nginx)

### Install Nginx
```bash
sudo apt update
sudo apt install nginx
```

### Nginx Configuration
Create `/etc/nginx/sites-available/kahani`:
```nginx
server {
    listen 80;
    server_name your-domain.com;

    # Frontend
    location / {
        proxy_pass http://localhost:6789;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }

    # Backend API
    location /api/ {
        proxy_pass http://localhost:9876;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }

    # WebSocket support for streaming
    location /ws/ {
        proxy_pass http://localhost:9876;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Enable Site
```bash
sudo ln -s /etc/nginx/sites-available/kahani /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## SSL/HTTPS (Let's Encrypt)

### Install Certbot
```bash
sudo apt install certbot python3-certbot-nginx
```

### Get SSL Certificate
```bash
sudo certbot --nginx -d your-domain.com
```

## Monitoring and Logs

### View Logs
```bash
# System service logs
sudo journalctl -u kahani -f

# Application logs
tail -f /opt/kahani/backend/logs/kahani.log
```

### Health Checks
```bash
# Backend health
curl http://localhost:9876/health

# Frontend
curl http://localhost:6789
```

### Process Monitoring
```bash
# Check running processes
ps aux | grep -E "(uvicorn|next)"

# Check port usage
sudo netstat -tlnp | grep -E "(6789|9876)"
```

## Performance Optimization

### Backend Workers
The production script uses 4 workers by default. Adjust based on your server:
```bash
# In start-prod.sh, modify:
uvicorn app.main:app --host 0.0.0.0 --port "$BACKEND_PORT" --workers 4
```

### Database Optimization
For high-traffic deployments, consider:
- Moving to PostgreSQL
- Adding database connection pooling
- Implementing Redis for caching

### Resource Limits
The systemd service includes resource limits:
- Max memory: 2GB
- Max file descriptors: 65536

## Backup Strategy

### Database Backup
```bash
# Create backup
cp /opt/kahani/backend/data/kahani.db /opt/kahani/backups/kahani-$(date +%Y%m%d).db

# Automated backup (add to crontab)
0 2 * * * cp /opt/kahani/backend/data/kahani.db /opt/kahani/backups/kahani-$(date +\%Y\%m\%d).db
```

### Full Application Backup
```bash
# Backup entire application
tar -czf kahani-backup-$(date +%Y%m%d).tar.gz /opt/kahani --exclude=node_modules --exclude=.venv
```

## Troubleshooting

### Common Issues

1. **Port already in use**
   ```bash
   sudo lsof -i :6789
   sudo lsof -i :9876
   ```

2. **Permission denied**
   ```bash
   sudo chown -R kahani:kahani /opt/kahani
   ```

3. **Frontend build fails**
   ```bash
   cd frontend
   rm -rf .next node_modules
   npm install
   npm run build
   ```

4. **Database migration errors**
   ```bash
   cd backend
   source ../.venv/bin/activate
   python repair_alembic_version.py
   alembic upgrade head
   ```

### Log Locations
- Application logs: `/opt/kahani/backend/logs/kahani.log`
- System logs: `journalctl -u kahani`
- Nginx logs: `/var/log/nginx/`

## Security Considerations

1. **Firewall**: Only open necessary ports
2. **SSL**: Always use HTTPS in production
3. **Updates**: Keep system and dependencies updated
4. **Backups**: Regular automated backups
5. **Monitoring**: Set up monitoring and alerting
6. **User permissions**: Run as non-root user

## Scaling

For high-traffic deployments:
1. Use a load balancer (HAProxy, Nginx)
2. Deploy multiple backend instances
3. Use a shared database (PostgreSQL)
4. Implement Redis for session storage
5. Use CDN for static assets

## Support

For issues and questions:
- Check logs first
- Review this documentation
- Check GitHub issues
- Contact support team
