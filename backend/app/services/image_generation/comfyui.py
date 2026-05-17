"""
ComfyUI Image Generation Provider

Implements the ImageGenerationProvider interface for ComfyUI servers.
Supports both HTTP polling and WebSocket connections for job status.
"""

import asyncio
import json
import logging
import uuid
from typing import Optional, List, Dict, Any
from urllib.parse import urljoin

import httpx

from .base import (
    ImageGenerationProvider,
    GenerationRequest,
    GenerationResult,
    GenerationStatus,
)

logger = logging.getLogger(__name__)


class ComfyUIProvider(ImageGenerationProvider):
    """ComfyUI image generation provider"""

    def __init__(
        self,
        server_url: str,
        api_key: Optional[str] = None,
        timeout: int = 300,
        polling_interval: float = 2.0,
    ):
        super().__init__(server_url, api_key, timeout)
        self.polling_interval = polling_interval
        self._client_id = str(uuid.uuid4())
        self._http_client: Optional[httpx.AsyncClient] = None

    @property
    def provider_name(self) -> str:
        return "comfyui"

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._http_client is None or self._http_client.is_closed:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            self._http_client = httpx.AsyncClient(
                base_url=self.server_url,
                headers=headers,
                timeout=httpx.Timeout(self.timeout, connect=30.0),
            )
        return self._http_client

    async def close(self):
        """Close the HTTP client"""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None

    async def check_connection(self) -> bool:
        """Check if ComfyUI server is reachable"""
        try:
            client = await self._get_client()
            response = await client.get("/system_stats")
            self._connected = response.status_code == 200
            return self._connected
        except Exception as e:
            logger.warning(f"ComfyUI connection check failed: {e}")
            self._connected = False
            return False

    async def get_server_status(self) -> Dict[str, Any]:
        """Get ComfyUI server status"""
        try:
            client = await self._get_client()

            # Get system stats
            stats_response = await client.get("/system_stats")
            if stats_response.status_code != 200:
                return {
                    "online": False,
                    "error": f"Server returned status {stats_response.status_code}"
                }

            stats = stats_response.json()

            # Get queue status
            queue_response = await client.get("/queue")
            queue_data = queue_response.json() if queue_response.status_code == 200 else {}

            # Parse GPU memory info
            gpu_info = {}
            devices = stats.get("devices", [])
            if devices:
                for i, device in enumerate(devices):
                    gpu_info[f"gpu_{i}"] = {
                        "name": device.get("name", "Unknown"),
                        "type": device.get("type", "Unknown"),
                        "vram_total": device.get("vram_total", 0),
                        "vram_free": device.get("vram_free", 0),
                        "torch_vram_total": device.get("torch_vram_total", 0),
                        "torch_vram_free": device.get("torch_vram_free", 0),
                    }

            return {
                "online": True,
                "queue_running": len(queue_data.get("queue_running", [])),
                "queue_pending": len(queue_data.get("queue_pending", [])),
                "gpu_memory": gpu_info,
                "system": stats.get("system", {}),
            }

        except httpx.ConnectError as e:
            logger.warning(f"Failed to connect to ComfyUI server: {e}")
            return {"online": False, "error": "Connection failed"}
        except Exception as e:
            logger.error(f"Error getting ComfyUI server status: {e}")
            return {"online": False, "error": str(e)}

    async def get_available_checkpoints(self) -> List[str]:
        """Get list of available model checkpoints from ComfyUI"""
        try:
            client = await self._get_client()
            response = await client.get("/object_info")

            if response.status_code != 200:
                logger.error(f"Failed to get object_info: {response.status_code}")
                return []

            data = response.json()

            # Get checkpoints from CheckpointLoaderSimple node
            checkpoint_node = data.get("CheckpointLoaderSimple", {})
            inputs = checkpoint_node.get("input", {}).get("required", {})
            checkpoints = inputs.get("ckpt_name", [[]])[0]

            if isinstance(checkpoints, list):
                return sorted(checkpoints)

            return []

        except Exception as e:
            logger.error(f"Error getting available checkpoints: {e}")
            return []

    async def get_available_samplers(self) -> List[str]:
        """Get list of available samplers from ComfyUI"""
        try:
            client = await self._get_client()
            response = await client.get("/object_info")

            if response.status_code != 200:
                return []

            data = response.json()

            # Get samplers from KSampler node
            ksampler_node = data.get("KSampler", {})
            inputs = ksampler_node.get("input", {}).get("required", {})
            samplers = inputs.get("sampler_name", [[]])[0]

            if isinstance(samplers, list):
                return samplers

            return []

        except Exception as e:
            logger.error(f"Error getting available samplers: {e}")
            return []

    async def get_available_schedulers(self) -> List[str]:
        """Get list of available schedulers from ComfyUI"""
        try:
            client = await self._get_client()
            response = await client.get("/object_info")

            if response.status_code != 200:
                return []

            data = response.json()

            # Get schedulers from KSampler node
            ksampler_node = data.get("KSampler", {})
            inputs = ksampler_node.get("input", {}).get("required", {})
            schedulers = inputs.get("scheduler", [[]])[0]

            if isinstance(schedulers, list):
                return schedulers

            return []

        except Exception as e:
            logger.error(f"Error getting available schedulers: {e}")
            return []

    def _build_txt2img_workflow(self, request: GenerationRequest) -> Dict[str, Any]:
        """Build a basic txt2img workflow for ComfyUI"""
        import random
        # ComfyUI requires seed >= 0, so generate a random seed if not provided
        seed = request.seed if request.seed is not None else random.randint(0, 2**32 - 1)

        workflow = {
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed,
                    "steps": request.steps,
                    "cfg": request.cfg_scale,
                    "sampler_name": request.sampler,
                    "scheduler": request.scheduler,
                    "denoise": 1.0,
                    "model": ["4", 0],
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "latent_image": ["5", 0],
                }
            },
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {
                    "ckpt_name": request.checkpoint or "sdxl_lightning_4step.safetensors"
                }
            },
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": request.width,
                    "height": request.height,
                    "batch_size": 1
                }
            },
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": request.prompt,
                    "clip": ["4", 1]
                }
            },
            "7": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": request.negative_prompt,
                    "clip": ["4", 1]
                }
            },
            "8": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["3", 0],
                    "vae": ["4", 2]
                }
            },
            "9": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": "kahani",
                    "images": ["8", 0]
                }
            }
        }

        return workflow

    def _build_lumina2_workflow(self, request: GenerationRequest) -> Dict[str, Any]:
        """Build a workflow for Lumina2/z-image turbo models"""
        import random
        seed = request.seed if request.seed is not None else random.randint(0, 2**32 - 1)

        # Lumina2 models need separate UNET, CLIP, and VAE loaders
        workflow = {
            # Prompt input
            "58": {
                "class_type": "PrimitiveStringMultiline",
                "inputs": {
                    "value": request.prompt
                }
            },
            # Load CLIP (Qwen for Lumina2)
            "57:30": {
                "class_type": "CLIPLoader",
                "inputs": {
                    "clip_name": "qwen_3_4b.safetensors",
                    "type": "lumina2",
                    "device": "default"
                }
            },
            # Load VAE
            "57:29": {
                "class_type": "VAELoader",
                "inputs": {
                    "vae_name": "ae.safetensors"
                }
            },
            # Load diffusion model (UNET)
            "57:28": {
                "class_type": "UNETLoader",
                "inputs": {
                    "unet_name": request.checkpoint or "z_image_turbo_bf16.safetensors",
                    "weight_dtype": "default"
                }
            },
            # Apply AuraFlow sampling
            "57:11": {
                "class_type": "ModelSamplingAuraFlow",
                "inputs": {
                    "shift": 3,
                    "model": ["57:28", 0]
                }
            },
            # Encode positive prompt
            "57:27": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": ["58", 0],
                    "clip": ["57:30", 0]
                }
            },
            # Zero out conditioning for negative (Lumina2 style)
            "57:33": {
                "class_type": "ConditioningZeroOut",
                "inputs": {
                    "conditioning": ["57:27", 0]
                }
            },
            # Empty latent (SD3 style for Lumina2)
            "57:13": {
                "class_type": "EmptySD3LatentImage",
                "inputs": {
                    "width": request.width,
                    "height": request.height,
                    "batch_size": 1
                }
            },
            # KSampler
            "57:3": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed,
                    "steps": request.steps or 4,
                    "cfg": request.cfg_scale or 1,
                    "sampler_name": "res_multistep",
                    "scheduler": "simple",
                    "denoise": 1,
                    "model": ["57:11", 0],
                    "positive": ["57:27", 0],
                    "negative": ["57:33", 0],
                    "latent_image": ["57:13", 0]
                }
            },
            # VAE Decode
            "57:8": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["57:3", 0],
                    "vae": ["57:29", 0]
                }
            },
            # Save Image
            "9": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": "kahani",
                    "images": ["57:8", 0]
                }
            }
        }

        return workflow

    def _is_lumina2_model(self, checkpoint: str) -> bool:
        """Check if the checkpoint is a Lumina2/z-image model"""
        if not checkpoint:
            return False
        checkpoint_lower = checkpoint.lower()
        return any(name in checkpoint_lower for name in [
            "z_image", "z-image", "lumina2", "lumina_2"
        ])

    def _is_flux_klein_model(self, checkpoint: str) -> bool:
        """Check if the checkpoint is a Flux Klein model"""
        if not checkpoint:
            return False
        checkpoint_lower = checkpoint.lower()
        return any(name in checkpoint_lower for name in [
            "flux-2-klein", "flux2-klein", "flux_2_klein", "flux2_klein", "klein"
        ])

    def _build_flux_klein_workflow(self, request: GenerationRequest) -> Dict[str, Any]:
        """Build a workflow for Flux Klein models"""
        import random
        seed = request.seed if request.seed is not None else random.randint(0, 2**63 - 1)

        workflow = {
            # Prompt input
            "76": {
                "class_type": "PrimitiveStringMultiline",
                "inputs": {
                    "value": request.prompt
                }
            },
            # Width primitive
            "77:68": {
                "class_type": "PrimitiveInt",
                "inputs": {
                    "value": request.width
                }
            },
            # Height primitive
            "77:69": {
                "class_type": "PrimitiveInt",
                "inputs": {
                    "value": request.height
                }
            },
            # Load diffusion model (UNET)
            "77:70": {
                "class_type": "UNETLoader",
                "inputs": {
                    "unet_name": request.checkpoint or "flux-2-klein-9b-fp8.safetensors",
                    "weight_dtype": "default"
                }
            },
            # Load CLIP (Qwen for Flux2)
            "77:71": {
                "class_type": "CLIPLoader",
                "inputs": {
                    "clip_name": "qwen_3_8b_fp8mixed.safetensors",
                    "type": "flux2",
                    "device": "default"
                }
            },
            # Load VAE
            "77:72": {
                "class_type": "VAELoader",
                "inputs": {
                    "vae_name": "flux2-vae.safetensors"
                }
            },
            # Encode positive prompt
            "77:74": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": ["76", 0],
                    "clip": ["77:71", 0]
                }
            },
            # Zero out conditioning for negative
            "77:76": {
                "class_type": "ConditioningZeroOut",
                "inputs": {
                    "conditioning": ["77:74", 0]
                }
            },
            # CFG Guider
            "77:63": {
                "class_type": "CFGGuider",
                "inputs": {
                    "cfg": request.cfg_scale or 1,
                    "model": ["77:70", 0],
                    "positive": ["77:74", 0],
                    "negative": ["77:76", 0]
                }
            },
            # Flux2 Scheduler
            "77:62": {
                "class_type": "Flux2Scheduler",
                "inputs": {
                    "steps": request.steps or 4,
                    "width": ["77:68", 0],
                    "height": ["77:69", 0]
                }
            },
            # Sampler select
            "77:61": {
                "class_type": "KSamplerSelect",
                "inputs": {
                    "sampler_name": "euler"
                }
            },
            # Random noise
            "77:73": {
                "class_type": "RandomNoise",
                "inputs": {
                    "noise_seed": seed
                }
            },
            # Empty Flux 2 latent
            "77:66": {
                "class_type": "EmptyFlux2LatentImage",
                "inputs": {
                    "width": ["77:68", 0],
                    "height": ["77:69", 0],
                    "batch_size": 1
                }
            },
            # Sampler Custom Advanced
            "77:64": {
                "class_type": "SamplerCustomAdvanced",
                "inputs": {
                    "noise": ["77:73", 0],
                    "guider": ["77:63", 0],
                    "sampler": ["77:61", 0],
                    "sigmas": ["77:62", 0],
                    "latent_image": ["77:66", 0]
                }
            },
            # VAE Decode
            "77:65": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["77:64", 0],
                    "vae": ["77:72", 0]
                }
            },
            # Save Image
            "78": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": "kahani",
                    "images": ["77:65", 0]
                }
            }
        }

        return workflow

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """Submit a generation request to ComfyUI"""
        try:
            client = await self._get_client()

            # Build the workflow based on request type and model
            if self._is_flux_klein_model(request.checkpoint):
                # Use Flux Klein workflow
                logger.info(f"Using Flux Klein workflow for checkpoint: {request.checkpoint}")
                workflow = self._build_flux_klein_workflow(request)
            elif self._is_lumina2_model(request.checkpoint):
                # Use Lumina2/z-image workflow
                logger.info(f"Using Lumina2 workflow for checkpoint: {request.checkpoint}")
                workflow = self._build_lumina2_workflow(request)
            elif request.workflow_type == "txt2img":
                workflow = self._build_txt2img_workflow(request)
            else:
                # Default to txt2img for SDXL/SD models
                workflow = self._build_txt2img_workflow(request)

            # Submit the prompt
            payload = {
                "prompt": workflow,
                "client_id": self._client_id,
            }

            response = await client.post("/prompt", json=payload)

            if response.status_code != 200:
                error_text = response.text
                logger.error(f"ComfyUI prompt submission failed: {error_text}")
                return GenerationResult(
                    success=False,
                    status=GenerationStatus.FAILED,
                    error_message=f"Failed to submit prompt: {error_text}"
                )

            data = response.json()
            prompt_id = data.get("prompt_id")

            if not prompt_id:
                return GenerationResult(
                    success=False,
                    status=GenerationStatus.FAILED,
                    error_message="No prompt_id returned from ComfyUI"
                )

            logger.info(f"ComfyUI job submitted with prompt_id: {prompt_id}")

            return GenerationResult(
                success=True,
                status=GenerationStatus.QUEUED,
                job_id=prompt_id,
                metadata={
                    "prompt": request.prompt,
                    "negative_prompt": request.negative_prompt,
                    "width": request.width,
                    "height": request.height,
                    "steps": request.steps,
                    "cfg_scale": request.cfg_scale,
                    "sampler": request.sampler,
                    "checkpoint": request.checkpoint,
                }
            )

        except Exception as e:
            logger.error(f"Error submitting generation request: {e}")
            return GenerationResult(
                success=False,
                status=GenerationStatus.FAILED,
                error_message=str(e)
            )

    async def get_job_status(self, job_id: str) -> GenerationResult:
        """Get the status of a generation job"""
        try:
            client = await self._get_client()

            # Check queue status first
            queue_response = await client.get("/queue")
            if queue_response.status_code == 200:
                queue_data = queue_response.json()

                # Check if in running queue
                for item in queue_data.get("queue_running", []):
                    if len(item) > 1 and item[1] == job_id:
                        return GenerationResult(
                            success=True,
                            status=GenerationStatus.PROCESSING,
                            job_id=job_id,
                        )

                # Check if in pending queue
                for item in queue_data.get("queue_pending", []):
                    if len(item) > 1 and item[1] == job_id:
                        return GenerationResult(
                            success=True,
                            status=GenerationStatus.QUEUED,
                            job_id=job_id,
                        )

            # Check history for completion
            history_response = await client.get(f"/history/{job_id}")
            if history_response.status_code == 200:
                history_data = history_response.json()

                if job_id in history_data:
                    job_data = history_data[job_id]
                    status_data = job_data.get("status", {})

                    if status_data.get("status_str") == "error":
                        # Extract error message, ensuring it's a string
                        messages = status_data.get("messages", [])
                        if messages and len(messages) > 0:
                            error_msg = str(messages[0]) if messages[0] else "Generation failed"
                        else:
                            error_msg = "Generation failed"
                        logger.error(f"ComfyUI generation error for job {job_id}: {error_msg}")
                        return GenerationResult(
                            success=False,
                            status=GenerationStatus.FAILED,
                            job_id=job_id,
                            error_message=error_msg
                        )

                    # Check for outputs
                    outputs = job_data.get("outputs", {})
                    if outputs:
                        return GenerationResult(
                            success=True,
                            status=GenerationStatus.COMPLETED,
                            job_id=job_id,
                        )

            # If not found anywhere, might still be pending
            return GenerationResult(
                success=True,
                status=GenerationStatus.PENDING,
                job_id=job_id,
            )

        except Exception as e:
            logger.error(f"Error getting job status: {e}")
            return GenerationResult(
                success=False,
                status=GenerationStatus.FAILED,
                job_id=job_id,
                error_message=str(e)
            )

    async def get_result(self, job_id: str) -> GenerationResult:
        """Get the result of a completed generation job"""
        try:
            client = await self._get_client()

            # Get history
            history_response = await client.get(f"/history/{job_id}")
            if history_response.status_code != 200:
                return GenerationResult(
                    success=False,
                    status=GenerationStatus.FAILED,
                    job_id=job_id,
                    error_message="Failed to get job history"
                )

            history_data = history_response.json()

            if job_id not in history_data:
                return GenerationResult(
                    success=False,
                    status=GenerationStatus.FAILED,
                    job_id=job_id,
                    error_message="Job not found in history"
                )

            job_data = history_data[job_id]
            outputs = job_data.get("outputs", {})

            # Find the SaveImage node output
            for node_id, node_output in outputs.items():
                images = node_output.get("images", [])
                if images:
                    # Get the first image
                    image_info = images[0]
                    filename = image_info.get("filename")
                    subfolder = image_info.get("subfolder", "")
                    image_type = image_info.get("type", "output")

                    if filename:
                        # Download the image
                        params = {
                            "filename": filename,
                            "subfolder": subfolder,
                            "type": image_type,
                        }
                        image_response = await client.get("/view", params=params)

                        if image_response.status_code == 200:
                            return GenerationResult(
                                success=True,
                                status=GenerationStatus.COMPLETED,
                                job_id=job_id,
                                image_data=image_response.content,
                                filename=filename,
                                metadata={
                                    "subfolder": subfolder,
                                    "type": image_type,
                                }
                            )

            return GenerationResult(
                success=False,
                status=GenerationStatus.FAILED,
                job_id=job_id,
                error_message="No images found in job output"
            )

        except Exception as e:
            logger.error(f"Error getting job result: {e}")
            return GenerationResult(
                success=False,
                status=GenerationStatus.FAILED,
                job_id=job_id,
                error_message=str(e)
            )

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending or in-progress job"""
        try:
            client = await self._get_client()

            # ComfyUI uses DELETE /queue to cancel jobs
            response = await client.post(
                "/queue",
                json={"delete": [job_id]}
            )

            return response.status_code == 200

        except Exception as e:
            logger.error(f"Error cancelling job: {e}")
            return False

    async def upload_image(self, image_data: bytes, filename: str) -> str:
        """Upload an image to ComfyUI for use as a reference"""
        try:
            client = await self._get_client()

            files = {
                "image": (filename, image_data, "image/png"),
            }
            data = {
                "overwrite": "true",
            }

            response = await client.post("/upload/image", files=files, data=data)

            if response.status_code != 200:
                raise Exception(f"Upload failed with status {response.status_code}")

            result = response.json()
            return result.get("name", filename)

        except Exception as e:
            logger.error(f"Error uploading image: {e}")
            raise

    async def interrupt(self) -> bool:
        """Interrupt the current generation"""
        try:
            client = await self._get_client()
            response = await client.post("/interrupt")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Error interrupting generation: {e}")
            return False

    async def clear_queue(self) -> bool:
        """Clear all pending jobs in the queue"""
        try:
            client = await self._get_client()
            response = await client.post("/queue", json={"clear": True})
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Error clearing queue: {e}")
            return False
