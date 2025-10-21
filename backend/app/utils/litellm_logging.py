"""
LiteLLM Logging Configuration

Aggressively suppresses LiteLLM debug output and warnings.
"""

import logging
import os
import sys

def configure_litellm_logging():
    """Configure LiteLLM to suppress all debug output"""
    
    # Set environment variables before any imports
    os.environ["LITELLM_LOG"] = "ERROR"
    os.environ["LITELLM_LOG_LEVEL"] = "ERROR"
    os.environ["LITELLM_SUPPRESS_DEBUG_INFO"] = "true"
    os.environ["LITELLM_DROP_PARAMS"] = "true"
    os.environ["LITELLM_SET_VERBOSE"] = "false"
    
    # Suppress specific LiteLLM loggers
    litellm_loggers = [
        'litellm',
        'litellm.http_handler',
        'litellm.litellm_logging',
        'litellm.cost_calculator',
        'litellm.utils',
        'openai._base_client',
        'httpcore.connection',
        'httpcore.http11'
    ]
    
    for logger_name in litellm_loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.ERROR)
        logger.disabled = True
        
        # Remove all handlers
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
    
    # Also suppress root logger for these modules
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if hasattr(handler, 'setLevel'):
            handler.setLevel(logging.ERROR)
    
    # Try to import and configure litellm directly
    try:
        import litellm
        
        # Set all possible debug suppression flags
        litellm.set_verbose = False
        litellm.suppress_debug_info = True
        litellm.drop_params = True
        
        # Disable cost calculation
        try:
            litellm.cost_calculator = None
        except:
            pass
        
        # Monkey patch cost calculation
        try:
            def dummy_cost_calculator(*args, **kwargs):
                return None
            litellm.response_cost_calculator = dummy_cost_calculator
        except:
            pass
            
    except ImportError:
        pass

def suppress_httpcore_logging():
    """Suppress httpcore debug logging"""
    import logging
    
    # Suppress httpcore loggers
    httpcore_loggers = [
        'httpcore.connection',
        'httpcore.http11',
        'httpcore'
    ]
    
    for logger_name in httpcore_loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.ERROR)
        logger.disabled = True
        
        # Remove all handlers
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

# Configure logging immediately when this module is imported
configure_litellm_logging()
suppress_httpcore_logging()
