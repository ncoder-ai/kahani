# Local Extraction Model Setup Guide

## Overview

Kahani supports using small local models for plot event extraction to reduce costs and API usage. This feature allows you to use any OpenAI-compatible inference server (LM Studio, Ollama, llama.cpp, etc.) for extraction tasks while keeping story generation on your main LLM.

## Benefits

- **Cost Savings**: Free local inference vs paid API calls
- **Speed**: Local models can be faster than API calls, especially for batch extraction
- **Privacy**: All extraction stays local on your machine
- **Reduced Rate Limits**: No more worrying about hitting provider limits
- **Flexibility**: Works with any OpenAI-compatible endpoint

## Supported Inference Servers

Kahani works with **any OpenAI-compatible API endpoint**. Popular options include:

### LM Studio (Recommended for Beginners)
- **Platform**: Mac, Windows, Linux
- **Setup**: Download from [lmstudio.ai](https://lmstudio.ai)
- **Default URL**: `http://localhost:1234/v1`
- **Pros**: GUI-based, easy model management, no command line needed
- **Cons**: Requires GUI (not ideal for headless servers)

### Ollama
- **Platform**: Mac, Windows, Linux
- **Setup**: Install via [ollama.com](https://ollama.com) or package manager
- **Default URL**: `http://localhost:11434/v1`
- **Pros**: CLI-based, lightweight, auto-downloads models
- **Cons**: Requires command line usage

### llama.cpp Server
- **Platform**: Mac, Windows, Linux
- **Setup**: Build from source or use pre-built binaries
- **Default URL**: `http://localhost:8080/v1`
- **Pros**: Minimal, direct model loading, very fast
- **Cons**: Requires manual setup

### Text Generation WebUI
- **Platform**: Mac, Windows, Linux
- **Setup**: Install via pip or download
- **Default URL**: `http://localhost:5000/v1` (if configured)
- **Pros**: Full-featured, many options
- **Cons**: More complex setup

### Custom Endpoints
Any server that exposes an OpenAI-compatible API will work. Just provide the URL and model name.

## Recommended Models

For extraction tasks, we recommend small (3B-8B parameter) uncensored models:

### qwen2.5-3b-instruct (Recommended)
- **Size**: ~3B parameters
- **Quality**: Excellent instruction following, good JSON output
- **Speed**: Fast on CPU (3-5 seconds per scene)
- **Availability**: Available on HuggingFace, works with all inference servers

### ministral-3b-instruct
- **Size**: ~3B parameters
- **Quality**: Inherently uncensored, good for NSFW content
- **Speed**: Very fast on CPU
- **Availability**: Available on HuggingFace

### phi-3-mini
- **Size**: ~3.8B parameters
- **Quality**: Strong reasoning for its size
- **Speed**: Moderate on CPU
- **Availability**: Available on HuggingFace

## Setup Instructions

### Option 1: LM Studio (Easiest)

1. **Download and Install LM Studio**
   - Visit [lmstudio.ai](https://lmstudio.ai)
   - Download for your platform
   - Install and launch

2. **Download a Model**
   - In LM Studio, go to the "Search" tab
   - Search for "Qwen2.5-3B-Instruct" or "ministral-3b-instruct"
   - Click "Download" and wait for download to complete

3. **Load the Model**
   - Go to the "Chat" tab
   - Select your downloaded model from the dropdown
   - Click "Load Model"
   - The model will start running on `http://localhost:1234`

4. **Configure in Kahani**
   - Go to Settings → Context Settings → Local Extraction Model
   - Select "LM Studio" preset
   - Enter model name (e.g., "qwen2.5-3b-instruct")
   - Click "Test Connection"
   - Enable extraction model

### Option 2: Ollama

1. **Install Ollama**
   ```bash
   # macOS/Linux
   curl -fsSL https://ollama.com/install.sh | sh
   
   # Or via Homebrew (macOS)
   brew install ollama
   ```

2. **Download a Model**
   ```bash
   ollama pull qwen2.5:3b
   # or
   ollama pull ministral-3b-instruct
   ```

3. **Start Ollama** (if not running)
   ```bash
   ollama serve
   ```

4. **Configure in Kahani**
   - Go to Settings → Context Settings → Local Extraction Model
   - Select "Ollama" preset
   - Enter model name (e.g., "qwen2.5:3b")
   - Click "Test Connection"
   - Enable extraction model

### Option 3: Custom Endpoint

1. **Set up your inference server** (follow server-specific instructions)

2. **Configure in Kahani**
   - Go to Settings → Context Settings → Local Extraction Model
   - Select "Custom" preset
   - Enter your endpoint URL (must end with `/v1`)
   - Enter API key if required (leave empty for local servers)
   - Enter model name
   - Click "Test Connection"
   - Enable extraction model

## Configuration

### Settings

- **Enabled**: Toggle to enable/disable local extraction model
- **URL**: OpenAI-compatible endpoint URL (default: `http://localhost:1234/v1`)
- **API Key**: Optional, only needed for secured endpoints
- **Model Name**: Name of the model as recognized by your inference server
- **Temperature**: Generation temperature (default: 0.3, lower = more deterministic)
- **Max Tokens**: Maximum tokens per extraction (default: 1000)
- **Fallback to Main LLM**: If enabled, falls back to main LLM if extraction model fails

### Testing Connection

Use the "Test Connection" button to verify:
- Endpoint is reachable
- Model is loaded and responding
- Response time

## How It Works

1. When a scene is processed, Kahani checks if extraction model is enabled
2. If enabled, attempts extraction with local model first
3. If local model fails (connection error, timeout, invalid JSON):
   - If fallback enabled: Uses main LLM
   - If fallback disabled: Returns empty results
4. Logs indicate which model was used for each extraction

## Troubleshooting

### Connection Failed

**Problem**: "Cannot connect to endpoint"

**Solutions**:
- Verify inference server is running
- Check URL is correct (should end with `/v1` for OpenAI-compatible)
- Try `http://localhost:1234/v1` for LM Studio
- Try `http://localhost:11434/v1` for Ollama
- Check firewall isn't blocking localhost connections

### Model Not Found

**Problem**: "Model not found" or "404 Not Found"

**Solutions**:
- Verify model name matches exactly what your server expects
- For LM Studio: Check model name in the Chat tab dropdown
- For Ollama: Run `ollama list` to see available models
- Ensure model is loaded/running in your inference server

### Slow Performance

**Problem**: Extraction takes too long

**Solutions**:
- Use a smaller model (3B instead of 7B+)
- Ensure model is running on GPU if available
- Reduce `max_tokens` setting
- Check system resources (CPU/RAM usage)

### Invalid JSON Response

**Problem**: "Invalid JSON response from extraction model"

**Solutions**:
- Model may not be good at structured output
- Try a different model (qwen2.5-3b-instruct is recommended)
- Increase `max_tokens` to allow complete responses
- Enable fallback to main LLM for reliability

### NSFW Content Issues

**Problem**: Model refuses to process NSFW content

**Solutions**:
- Use an uncensored model (ministral-3b-instruct, abliterated models)
- Avoid censored models like base Qwen (use abliterated versions)
- Check model documentation for censorship policies

## Performance Tips

1. **Use GPU if available**: Most inference servers support GPU acceleration
2. **Batch processing**: Extraction model handles batch extraction efficiently
3. **Model selection**: 3B models are fast and sufficient for extraction
4. **Temperature**: Keep low (0.3) for more deterministic, reliable JSON output

## Comparison: Local vs Main LLM

| Aspect | Local Model | Main LLM |
|--------|-------------|----------|
| Cost | Free | API costs |
| Speed | 2-5s/scene (CPU) | 1-3s/scene (API) |
| Privacy | 100% local | Data sent to provider |
| Quality | Good for extraction | Excellent |
| Reliability | Depends on setup | High |
| Rate Limits | None | Provider limits |

## Best Practices

1. **Start with LM Studio**: Easiest setup for beginners
2. **Test before enabling**: Always test connection first
3. **Enable fallback**: Keep fallback enabled for reliability
4. **Monitor logs**: Check which model is being used
5. **Use appropriate models**: 3B models are ideal for extraction
6. **Keep models updated**: Update models periodically for best results

## Advanced Configuration

### Custom Temperature

Lower temperature (0.1-0.3) for more deterministic JSON output.
Higher temperature (0.5-0.7) for more creative extraction (not recommended).

### Custom Max Tokens

- **500-1000**: Single scene extraction
- **1000-2000**: Batch extraction (multiple scenes)
- **2000+**: Large batch extraction (not recommended, may be slow)

### Multiple Models

You can switch between models by changing the model name in settings. No restart required.

## Support

For issues or questions:
1. Check logs in `backend/logs/kahani.log`
2. Test connection using the "Test Connection" button
3. Verify inference server is working independently
4. Check model documentation for specific requirements









