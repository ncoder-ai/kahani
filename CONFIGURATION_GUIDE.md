# Kahani Configuration Guide

This guide ensures that all configuration files are consistent and that anyone can pull the repository and have it work immediately.

## 🎯 **Configuration Philosophy**

- **No hard-coded values**: All configuration uses environment variables or auto-detection
- **Template-based**: All configuration files have templates for easy setup
- **Environment-aware**: Different configurations for development, Docker, and production
- **Auto-detection**: Network configuration is automatically detected
- **Validation**: Configuration is validated before startup

## 📁 **Configuration Files Structure**

```
kahani/
├── config.yaml              # Main application configuration
├── .env.example             # Environment variables template
├── setup-env.sh            # Environment setup script
├── validate-config.sh       # Configuration validation script
├── .env                     # Environment variables (created by setup)
├── backend/
│   ├── app/
│   │   ├── config.py        # Backend settings
│   │   ├── main.py          # FastAPI application
│   │   └── utils/
│   │       └── network_config.py  # Network configuration utility
└── frontend/
    ├── package.json         # Frontend dependencies
    └── next.config.js       # Next.js configuration
```

## 🔧 **Configuration Files**

### **1. config.yaml**
Main application configuration with environment-specific settings:

```yaml
server:
  backend:
    port: 9876
    host: 0.0.0.0  # Bind to all interfaces for network access
  
  frontend:
    port: 6789
    # API URL will be auto-detected

deployment:
  environment: development
  debug: true

paths:
  data: ./data
  exports: ./exports
  logs: ./logs
```

### **2. .env.example**
Template for environment variables with all possible settings:

```bash
# Core settings
KAHANI_ENV=development
JWT_SECRET_KEY=your-super-secret-jwt-key-change-this-in-production

# Network (auto-detected if not set)
# KAHANI_API_URL=http://localhost:9876
# KAHANI_FRONTEND_URL=http://localhost:6789
# KAHANI_CORS_ORIGINS=["*"]

# Database
DATABASE_URL=sqlite:///./data/kahani.db

# LLM Configuration
LLM_BASE_URL=http://localhost:1234/v1
LLM_MODEL=local-model

# Semantic Memory
ENABLE_SEMANTIC_MEMORY=true
SEMANTIC_DB_PATH=./data/chromadb
```

### **3. backend/app/config.py**
Backend settings with environment variable support:

```python
class Settings(BaseSettings):
    # All settings with environment variable support
    cors_origins: List[str] = ["*"]  # Auto-configured by network config
    
    class Config:
        env_file = ".env"  # Flexible path
        case_sensitive = False
```

### **4. backend/app/utils/network_config.py**
Automatic network configuration utility:

```python
class NetworkConfig:
    @staticmethod
    def get_network_ip() -> Optional[str]:
        # Auto-detects network IP using multiple methods
    
    @staticmethod
    def get_api_url(backend_port: int = 9876) -> str:
        # Returns appropriate API URL for environment
    
    @staticmethod
    def get_cors_origins() -> list:
        # Returns CORS origins based on environment
```

## 🚀 **Setup Process**

### **For New Users (First Time Setup)**

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd kahani
   ```

2. **Run the setup script**:
   ```bash
   ./setup-env.sh
   ```

3. **Validate configuration**:
   ```bash
   ./validate-config.sh
   ```

4. **Start the application**:
   ```bash
   ./start-dev.sh
   ```

### **For Existing Users (Updates)**

1. **Pull latest changes**:
   ```bash
   git pull
   ```

2. **Validate configuration**:
   ```bash
   ./validate-config.sh
   ```

3. **Start the application**:
   ```bash
   ./start-dev.sh
   ```

## 🌐 **Network Configuration**

### **Automatic Detection**
The system automatically detects network configuration:

- **Development**: Auto-detects network IP
- **Docker**: Uses container networking
- **Production**: Uses environment variables

### **Manual Override**
If needed, you can override auto-detection:

```bash
# Set explicit API URL
export KAHANI_API_URL=http://192.168.1.100:9876

# Set explicit frontend URL
export KAHANI_FRONTEND_URL=http://192.168.1.100:6789

# Set CORS origins
export KAHANI_CORS_ORIGINS='["http://localhost:6789", "https://yourdomain.com"]'
```

## 🐳 **Docker Configuration**

### **Docker Compose**
Use the provided `docker-compose.network.yml`:

```bash
# Set Docker environment
export KAHANI_ENV=docker
export DOCKER_CONTAINER=true

# Run with Docker Compose
docker-compose -f docker-compose.network.yml up
```

### **Docker Environment Variables**
```bash
# Docker-specific settings
DOCKER_CONTAINER=true
CONTAINER_IP=172.17.0.2  # Optional: specific container IP
```

## 🏭 **Production Configuration**

### **Environment Variables**
```bash
# Production settings
KAHANI_ENV=production
KAHANI_API_URL=https://api.yourdomain.com
KAHANI_FRONTEND_URL=https://yourdomain.com
KAHANI_CORS_ORIGINS=["https://yourdomain.com"]

# Security
JWT_SECRET_KEY=your-production-secret-key
```

### **Database Configuration**
```bash
# Production database
DATABASE_URL=postgresql://user:password@localhost:5432/kahani
```

## 🔍 **Validation and Troubleshooting**

### **Configuration Validation**
```bash
# Validate all configuration
./validate-config.sh
```

### **Network Testing**
```bash
# Test network configuration
python3 -c "
import sys
sys.path.append('backend')
from backend.app.utils.network_config import NetworkConfig
config = NetworkConfig.get_deployment_config()
print(f'Network IP: {config[\"network_ip\"]}')
print(f'API URL: {config[\"api_url\"]}')
print(f'Frontend URL: {config[\"frontend_url\"]}')
"
```

### **Common Issues**

1. **Network not accessible from other machines**:
   - Check if backend is binding to `0.0.0.0`
   - Verify CORS origins include `["*"]` for development
   - Ensure firewall allows connections

2. **Environment variables not loading**:
   - Check if `.env` file exists
   - Run `./setup-env.sh` to create it
   - Verify file permissions

3. **Configuration conflicts**:
   - Run `./validate-config.sh` to check for issues
   - Check for duplicate environment variables
   - Verify YAML/JSON syntax

## 📋 **Best Practices**

1. **Never commit .env files**: Use `env.template` instead
2. **Use environment variables**: Override defaults as needed
3. **Validate configuration**: Run validation before deployment
4. **Test network access**: Verify from different machines
5. **Keep templates updated**: Ensure templates match current configuration

## 🎉 **Benefits**

- ✅ **Consistent setup**: Same configuration for all users
- ✅ **Auto-detection**: Minimal configuration needed
- ✅ **Environment-aware**: Different configs for different scenarios
- ✅ **Validation**: Catches configuration issues early
- ✅ **Templates**: Easy to understand and modify
- ✅ **No hard-coding**: Works on any network
