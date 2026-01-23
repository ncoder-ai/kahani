"""
Base classes for image generation providers.

This module defines the abstract interface that all image generation
providers must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class GenerationStatus(str, Enum):
    """Status of an image generation job"""
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class GenerationResult:
    """Result of an image generation request"""
    success: bool
    status: GenerationStatus
    job_id: Optional[str] = None
    image_data: Optional[bytes] = None
    image_path: Optional[str] = None
    filename: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    seed: Optional[int] = None
    error_message: Optional[str] = None
    progress: float = 0.0  # 0.0 to 1.0
    current_step: int = 0
    total_steps: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationRequest:
    """Request for image generation"""
    prompt: str
    negative_prompt: str = ""
    width: int = 1024
    height: int = 1024
    steps: int = 4
    cfg_scale: float = 1.5
    seed: Optional[int] = None
    sampler: str = "euler"
    scheduler: str = "normal"
    checkpoint: Optional[str] = None

    # For character consistency (IP-Adapter/PuLID)
    reference_images: List[str] = field(default_factory=list)  # Paths to reference images
    reference_weight: float = 0.7

    # Style preset
    style_preset: Optional[str] = None

    # Workflow type
    workflow_type: str = "txt2img"  # "txt2img", "img2img", "ipadapter", "pulid"

    # Additional parameters for advanced workflows
    extra_params: Dict[str, Any] = field(default_factory=dict)


class ImageGenerationProvider(ABC):
    """Abstract base class for image generation providers"""

    def __init__(self, server_url: str, api_key: Optional[str] = None, timeout: int = 300):
        self.server_url = server_url.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout
        self._connected = False

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the name of this provider (e.g., 'comfyui')"""
        pass

    @abstractmethod
    async def check_connection(self) -> bool:
        """
        Check if the provider server is reachable and ready.

        Returns:
            True if connected and ready, False otherwise
        """
        pass

    @abstractmethod
    async def get_server_status(self) -> Dict[str, Any]:
        """
        Get detailed server status information.

        Returns:
            Dictionary with server status info (online, queue_size, gpu_memory, etc.)
        """
        pass

    @abstractmethod
    async def get_available_checkpoints(self) -> List[str]:
        """
        Get list of available model checkpoints on the server.

        Returns:
            List of checkpoint names
        """
        pass

    @abstractmethod
    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """
        Start an image generation job.

        Args:
            request: The generation request parameters

        Returns:
            GenerationResult with job_id and initial status
        """
        pass

    @abstractmethod
    async def get_job_status(self, job_id: str) -> GenerationResult:
        """
        Get the current status of a generation job.

        Args:
            job_id: The job identifier

        Returns:
            GenerationResult with current status and progress
        """
        pass

    @abstractmethod
    async def get_result(self, job_id: str) -> GenerationResult:
        """
        Get the result of a completed generation job.

        Args:
            job_id: The job identifier

        Returns:
            GenerationResult with image data/path if completed
        """
        pass

    @abstractmethod
    async def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a pending or in-progress job.

        Args:
            job_id: The job identifier

        Returns:
            True if cancellation was successful
        """
        pass

    @abstractmethod
    async def upload_image(self, image_data: bytes, filename: str) -> str:
        """
        Upload an image to the server for use as a reference.

        Args:
            image_data: The image bytes
            filename: Name to use for the uploaded file

        Returns:
            The filename/path to use in workflows
        """
        pass

    async def generate_and_wait(
        self,
        request: GenerationRequest,
        poll_interval: float = 2.0,
        max_wait: float = 300.0
    ) -> GenerationResult:
        """
        Generate an image and wait for completion.

        This is a convenience method that starts generation and polls
        until complete or timeout.

        Args:
            request: The generation request parameters
            poll_interval: Seconds between status checks
            max_wait: Maximum seconds to wait

        Returns:
            GenerationResult with final status and image if successful
        """
        import asyncio

        # Start the generation
        result = await self.generate(request)
        if not result.success or result.status == GenerationStatus.FAILED:
            return result

        job_id = result.job_id
        if not job_id:
            return GenerationResult(
                success=False,
                status=GenerationStatus.FAILED,
                error_message="No job ID returned from generation request"
            )

        # Poll for completion
        elapsed = 0.0
        while elapsed < max_wait:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            result = await self.get_job_status(job_id)
            logger.debug(f"Job {job_id} status: {result.status}, elapsed: {elapsed}s")

            if result.status == GenerationStatus.COMPLETED:
                logger.info(f"Job {job_id} completed, fetching result")
                return await self.get_result(job_id)
            elif result.status == GenerationStatus.FAILED:
                logger.warning(f"Job {job_id} failed: {result.error_message}")
                return result
            elif result.status == GenerationStatus.CANCELLED:
                logger.info(f"Job {job_id} was cancelled")
                return result

        # Timeout
        return GenerationResult(
            success=False,
            status=GenerationStatus.FAILED,
            job_id=job_id,
            error_message=f"Generation timed out after {max_wait} seconds"
        )
