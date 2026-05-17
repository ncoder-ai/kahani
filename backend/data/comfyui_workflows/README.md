# ComfyUI Workflow Templates

This directory contains JSON workflow templates for ComfyUI image generation.

## Available Workflows

| Template | Purpose | Model Type | Requirements |
|----------|---------|------------|--------------|
| `txt2img_portrait_sdxl.json` | Character portrait generation | SDXL | Basic ComfyUI |
| `txt2img_scene_sdxl.json` | Scene generation (no character refs) | SDXL | Basic ComfyUI |
| `ipadapter_scene_sdxl.json` | Scene with character consistency | SDXL | IPAdapter_plus |
| `txt2img_portrait_flux.json` | Character portrait generation | Flux | Flux nodes |

## Placeholders

Each workflow template includes a `placeholders` section that defines which values can be dynamically replaced at runtime:

- `POSITIVE_PROMPT` - The main generation prompt
- `NEGATIVE_PROMPT` - Things to avoid in the generation
- `SEED` - Random seed for reproducibility
- `CHECKPOINT` - Model checkpoint file name
- `WIDTH` / `HEIGHT` - Image dimensions
- `STEPS` - Number of sampling steps
- `CFG` - Classifier-free guidance scale
- `CHARACTER_IMAGE` - Reference image for IP-Adapter workflows
- `IPADAPTER_WEIGHT` - Weight for character likeness (0-1)

## Model Requirements

### SDXL Workflows
- **Checkpoint**: Any SDXL-compatible checkpoint (e.g., `sdxl_lightning_4step.safetensors`)
- **IP-Adapter**: For character consistency workflows, install [ComfyUI_IPAdapter_plus](https://github.com/cubiq/ComfyUI_IPAdapter_plus) and download the IP-Adapter model files.

### Flux Workflows
- **Checkpoint**: Flux Schnell or Flux Dev (e.g., `flux_schnell.safetensors`)
- **Note**: Flux models use different nodes and don't support IP-Adapter. For character consistency with Flux, consider using PuLID.

## Custom Workflows

Users can create their own workflows in the ComfyUI web interface, export them as JSON, and either:
1. Place them in this directory with appropriate placeholders
2. Upload them via the Kahani settings interface (future feature)

## How It Works

1. Kahani selects a workflow based on user settings and model type
2. Placeholders are replaced with actual values (prompt, seed, dimensions, etc.)
3. The workflow is submitted to ComfyUI via its API
4. Results are retrieved and stored in the Kahani database

## Recommended Checkpoints

### SDXL (Best for IP-Adapter support)
- **SDXL Lightning 4-step** - Fast, good quality, great IP-Adapter support
- **SDXL Turbo** - Very fast, lower resolution
- **Hyper-SDXL** - Similar to Lightning

### Flux (Higher quality, no IP-Adapter)
- **Flux Schnell** - Fast (4 steps)
- **Flux Dev** - Higher quality (20+ steps)

## IP-Adapter Models

For character consistency in SDXL workflows:
- `ip-adapter-plus-face_sdxl_vit-h.safetensors` - Face-focused consistency
- `CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors` - Required CLIP model
