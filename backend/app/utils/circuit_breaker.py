"""
Circuit Breaker Pattern Implementation

Provides fast-fail behavior for external service calls (LLM, TTS) to prevent
application-wide hangs when services are down or slow.

Circuit States:
- CLOSED: Normal operation, requests pass through
- OPEN: Service is failing, requests fail immediately
- HALF_OPEN: Testing if service has recovered
"""

import logging
import time
import asyncio
from enum import Enum
from typing import Callable, Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreaker:
    """
    Circuit breaker for external service calls.
    
    Prevents cascading failures by failing fast when a service is down.
    
    Args:
        failure_threshold: Number of failures before opening circuit (default: 5)
        recovery_timeout: Seconds to wait before attempting recovery (default: 60)
        success_threshold: Successful calls needed to close circuit from half-open (default: 2)
        timeout: Request timeout in seconds (default: 30)
    """
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        success_threshold: int = 2,
        timeout: int = 30
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        self.timeout = timeout
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.last_state_change: datetime = datetime.utcnow()
        
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt recovery"""
        if self.state != CircuitState.OPEN:
            return False
        
        if not self.last_failure_time:
            return True
        
        time_since_failure = (datetime.utcnow() - self.last_failure_time).total_seconds()
        return time_since_failure >= self.recovery_timeout
    
    def _record_success(self):
        """Record a successful call"""
        self.failure_count = 0
        
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            logger.info(f"[CIRCUIT-BREAKER] {self.name}: Success in HALF_OPEN state ({self.success_count}/{self.success_threshold})")
            
            if self.success_count >= self.success_threshold:
                self._close_circuit()
        elif self.state == CircuitState.OPEN:
            # Should not happen, but handle gracefully
            self._close_circuit()
    
    def _record_failure(self, error: Exception):
        """Record a failed call"""
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()
        self.success_count = 0  # Reset success count on any failure
        
        logger.warning(f"[CIRCUIT-BREAKER] {self.name}: Failure recorded ({self.failure_count}/{self.failure_threshold}): {error}")
        
        if self.state == CircuitState.HALF_OPEN:
            # Failure in half-open state immediately reopens circuit
            self._open_circuit()
        elif self.state == CircuitState.CLOSED:
            if self.failure_count >= self.failure_threshold:
                self._open_circuit()
    
    def _open_circuit(self):
        """Open the circuit (fail fast mode)"""
        if self.state != CircuitState.OPEN:
            self.state = CircuitState.OPEN
            self.last_state_change = datetime.utcnow()
            logger.error(f"[CIRCUIT-BREAKER] {self.name}: Circuit OPENED - failing fast for {self.recovery_timeout}s")
    
    def _close_circuit(self):
        """Close the circuit (normal operation)"""
        if self.state != CircuitState.CLOSED:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            self.last_state_change = datetime.utcnow()
            logger.info(f"[CIRCUIT-BREAKER] {self.name}: Circuit CLOSED - resuming normal operation")
    
    def _half_open_circuit(self):
        """Half-open the circuit (testing recovery)"""
        if self.state != CircuitState.HALF_OPEN:
            self.state = CircuitState.HALF_OPEN
            self.success_count = 0
            self.last_state_change = datetime.utcnow()
            logger.info(f"[CIRCUIT-BREAKER] {self.name}: Circuit HALF_OPEN - testing recovery")
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute a function through the circuit breaker.
        
        Args:
            func: Async function to call
            *args, **kwargs: Arguments to pass to the function
            
        Returns:
            Result of the function call
            
        Raises:
            CircuitBreakerOpenError: If circuit is open
            TimeoutError: If call exceeds timeout
            Exception: Original exception from the function
        """
        # Check if we should attempt recovery
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self._half_open_circuit()
            else:
                time_remaining = self.recovery_timeout - (datetime.utcnow() - self.last_failure_time).total_seconds()
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{self.name}' is OPEN. "
                    f"Service unavailable. Retry in {time_remaining:.0f}s"
                )
        
        # Execute the call with timeout
        try:
            result = await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=self.timeout
            )
            self._record_success()
            return result
            
        except asyncio.TimeoutError as e:
            logger.error(f"[CIRCUIT-BREAKER] {self.name}: Timeout after {self.timeout}s")
            self._record_failure(e)
            raise TimeoutError(f"Request to {self.name} timed out after {self.timeout}s")
            
        except Exception as e:
            self._record_failure(e)
            raise
    
    def get_state(self) -> dict:
        """Get current circuit breaker state for monitoring"""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time.isoformat() if self.last_failure_time else None,
            "last_state_change": self.last_state_change.isoformat(),
            "time_in_current_state": (datetime.utcnow() - self.last_state_change).total_seconds()
        }


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and rejects requests"""
    pass


# Global circuit breakers for external services
_circuit_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: int = 60,
    success_threshold: int = 2,
    timeout: int = 30
) -> CircuitBreaker:
    """
    Get or create a circuit breaker for a service.
    
    Args:
        name: Unique name for the service
        failure_threshold: Number of failures before opening circuit
        recovery_timeout: Seconds to wait before attempting recovery
        success_threshold: Successful calls needed to close circuit
        timeout: Request timeout in seconds
        
    Returns:
        CircuitBreaker instance
    """
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            success_threshold=success_threshold,
            timeout=timeout
        )
    return _circuit_breakers[name]


def get_all_circuit_breakers() -> dict[str, dict]:
    """Get state of all circuit breakers for monitoring"""
    return {name: cb.get_state() for name, cb in _circuit_breakers.items()}
