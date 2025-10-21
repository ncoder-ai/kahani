"""
Network Configuration Utility

Handles automatic network detection and configuration for different deployment scenarios.
"""

import os
import socket
import subprocess
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class NetworkConfig:
    """Handles network configuration for different deployment scenarios"""
    
    @staticmethod
    def get_network_ip() -> Optional[str]:
        """
        Automatically detect the primary network IP address.
        
        Returns:
            Primary network IP address or None if detection fails
        """
        try:
            # Method 1: Connect to a remote address to determine local IP
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                # Connect to a remote address (doesn't actually send data)
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
                logger.info(f"Detected network IP: {local_ip}")
                return local_ip
        except Exception as e:
            logger.warning(f"Failed to detect IP via socket method: {e}")
        
        try:
            # Method 2: Use ifconfig/ipconfig command
            if os.name == 'nt':  # Windows
                result = subprocess.run(['ipconfig'], capture_output=True, text=True)
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'IPv4' in line and '192.168.' in line:
                        ip = line.split(':')[-1].strip()
                        logger.info(f"Detected network IP via ipconfig: {ip}")
                        return ip
            else:  # Unix-like systems
                result = subprocess.run(['ifconfig'], capture_output=True, text=True)
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'inet ' in line and '127.0.0.1' not in line and '192.168.' in line:
                        ip = line.split()[1]
                        logger.info(f"Detected network IP via ifconfig: {ip}")
                        return ip
        except Exception as e:
            logger.warning(f"Failed to detect IP via system commands: {e}")
        
        logger.error("Could not detect network IP address")
        return None
    
    @staticmethod
    def get_api_url(backend_port: int = 9876) -> str:
        """
        Get the API URL for the backend service.
        
        Args:
            backend_port: Backend server port
            
        Returns:
            API URL string
        """
        # Check for explicit configuration
        api_url = os.getenv('KAHANI_API_URL')
        if api_url:
            logger.info(f"Using explicit API URL: {api_url}")
            return api_url
        
        # Check for Docker environment
        if os.getenv('DOCKER_CONTAINER'):
            # In Docker, use the container's network IP
            container_ip = os.getenv('CONTAINER_IP')
            if container_ip:
                return f"http://{container_ip}:{backend_port}"
            # Fallback to host.docker.internal for Docker Desktop
            return f"http://host.docker.internal:{backend_port}"
        
        # Check for production environment
        if os.getenv('KAHANI_ENV') == 'production':
            # In production, use environment variable or localhost
            return os.getenv('KAHANI_API_URL', f"http://localhost:{backend_port}")
        
        # Development environment - auto-detect network IP
        network_ip = NetworkConfig.get_network_ip()
        if network_ip:
            return f"http://{network_ip}:{backend_port}"
        
        # Fallback to localhost
        logger.warning("Falling back to localhost for API URL")
        return f"http://localhost:{backend_port}"
    
    @staticmethod
    def get_frontend_url(frontend_port: int = 6789) -> str:
        """
        Get the frontend URL for network access.
        
        Args:
            frontend_port: Frontend server port
            
        Returns:
            Frontend URL string
        """
        # Check for explicit configuration
        frontend_url = os.getenv('KAHANI_FRONTEND_URL')
        if frontend_url:
            return frontend_url
        
        # Check for Docker environment
        if os.getenv('DOCKER_CONTAINER'):
            container_ip = os.getenv('CONTAINER_IP')
            if container_ip:
                return f"http://{container_ip}:{frontend_port}"
            return f"http://host.docker.internal:{frontend_port}"
        
        # Check for production environment
        if os.getenv('KAHANI_ENV') == 'production':
            return os.getenv('KAHANI_FRONTEND_URL', f"http://localhost:{frontend_port}")
        
        # Development environment - auto-detect network IP
        network_ip = NetworkConfig.get_network_ip()
        if network_ip:
            return f"http://{network_ip}:{frontend_port}"
        
        # Fallback to localhost
        return f"http://localhost:{frontend_port}"
    
    @staticmethod
    def get_cors_origins() -> list:
        """
        Get CORS origins based on deployment environment.
        
        Returns:
            List of allowed CORS origins
        """
        # Check for explicit configuration
        cors_origins = os.getenv('KAHANI_CORS_ORIGINS')
        if cors_origins:
            try:
                import json
                return json.loads(cors_origins)
            except json.JSONDecodeError:
                logger.warning(f"Invalid CORS_ORIGINS format: {cors_origins}")
        
        # Production environment
        if os.getenv('KAHANI_ENV') == 'production':
            # In production, be more restrictive
            return [
                os.getenv('KAHANI_FRONTEND_URL', 'http://localhost:6789'),
                os.getenv('KAHANI_DOMAIN', 'https://kahani.app')
            ]
        
        # Development environment - allow all origins for local network access
        return ["*"]
    
    @staticmethod
    def get_deployment_config() -> Dict[str, Any]:
        """
        Get deployment-specific configuration.
        
        Returns:
            Dictionary with deployment configuration
        """
        env = os.getenv('KAHANI_ENV', 'development')
        
        config = {
            'environment': env,
            'network_ip': NetworkConfig.get_network_ip(),
            'api_url': NetworkConfig.get_api_url(),
            'frontend_url': NetworkConfig.get_frontend_url(),
            'cors_origins': NetworkConfig.get_cors_origins(),
            'is_docker': bool(os.getenv('DOCKER_CONTAINER')),
            'is_production': env == 'production'
        }
        
        logger.info(f"Deployment config: {config}")
        return config
