# Network Configuration Guide

This guide explains how to configure Kahani for different deployment scenarios, with Docker as the recommended approach.

## 🐳 **Docker Deployment (Recommended)**

Docker handles networking automatically - no manual configuration needed!

### **Default Docker Setup**
```bash
# Clone and start
git clone https://github.com/ncoder-ai/kahani.git
cd kahani
docker-compose up -d
```

**Access**: http://localhost:6789

### **Docker Network Benefits**
- ✅ **Automatic networking** between frontend and backend
- ✅ **No port conflicts** with your system
- ✅ **Isolated environment** - no system dependencies
- ✅ **Easy updates** with `git pull` and `docker-compose up`

### **Custom Docker Configuration**
```bash
# For custom ports
docker-compose up -d -p 3000:6789 -p 8000:9876

# For production with domain
# Edit .env file with your domain
docker-compose up -d
```

## 🖥️ **Baremetal Deployment (Advanced)**

For development or custom deployments:

### **Development Setup**
```bash
# Clone and install
git clone https://github.com/ncoder-ai/kahani.git
cd kahani
./install.sh

# Start development server
./start-dev.sh
```

**Access**: http://localhost:6789

### **Production Setup**
```bash
# Clone and install
git clone https://github.com/ncoder-ai/kahani.git
cd kahani
./install.sh

# Start production server
./start-prod.sh
```

## ⚙️ **Environment Configuration**

### **Docker Environment**
Docker automatically handles all networking. No manual configuration needed.

### **Baremetal Environment**
Edit `.env` file for custom configuration:

```bash
# API Configuration
NEXT_PUBLIC_API_URL=http://localhost:9876
INTERNAL_API_URL=http://localhost:9876

# CORS Configuration
CORS_ORIGINS=*

# Database Configuration
DATABASE_URL=sqlite:///./data/kahani.db
```

## 🌐 **Remote Access**

### **Docker with Remote Access**
```bash
# Access from other machines on your network
# Replace localhost with your server IP
http://192.168.1.100:6789
```

### **Baremetal with Remote Access**
```bash
# The app auto-detects network IP
# Access from other machines
http://192.168.1.100:6789
```

## 🔧 **Troubleshooting**

### **Docker Issues**
```bash
# View logs
docker-compose logs -f

# Restart services
docker-compose restart

# Rebuild if needed
docker-compose build --no-cache
```

### **Baremetal Issues**
```bash
# Check backend logs
tail -f backend/logs/kahani.log

# Verify configuration
./validate-config.sh
```

### **Common Issues**
- **Port conflicts**: Change ports in `.env` file
- **CORS errors**: Check `CORS_ORIGINS` setting
- **Network access**: Ensure firewall allows ports 6789 and 9876

## 📚 **Next Steps**

- **Quick Start**: See `QUICK_START.md` for step-by-step setup
- **Configuration**: See `CONFIGURATION_GUIDE.md` for detailed settings
- **Documentation**: Check `docs/` folder for feature guides

---

**Docker is the recommended approach for most users!** 🐳