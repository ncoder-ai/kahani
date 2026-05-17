# Text Completion API Guide

## Overview

Kahani supports two modes for interacting with language models:
1. **Chat Completion API** - Standard message-based format (default)
2. **Text Completion API** - Raw prompt format with custom templates (new)

This guide covers everything you need to know about using Text Completion mode.

## Why Text Completion?

### Use Text Completion When:
- Your model doesn't support Chat Completion API properly
- You're using instruction-tuned local models (Llama, Mistral, Qwen, GLM)
- You need full control over prompt formatting
- Chat mode produces poor results or errors
- Your backend only exposes `/v1/completions` endpoint
- You want to use models with specific prompt templates

### Use Chat Completion When:
- Using OpenAI, Anthropic, or other major API providers
- Your model explicitly supports the Chat Completion format
- Using Ollama (it handles formatting automatically)
- You prefer standardized message-based interactions

## Getting Started

### 1. Enable Text Completion Mode

**In Settings Modal** (Quick Settings):
1. Click the Settings icon in the story interface
2. Navigate to LLM Settings section
3. Find "Completion API Mode"
4. Select "Text Completion API"
5. Choose a template preset or customize

**In Settings Page** (Full Settings):
1. Go to Settings from the main menu
2. Select "LLM Settings" tab
3. Scroll to "Completion API Mode"
4. Select "Text Completion API"
5. Configure your template

### 2. Choose a Template Preset

Kahani includes 5 pre-built templates:

#### **Llama 3** (Recommended for Llama 3.x Instruct)
```
<|begin_of_text|><|start_header_id|>system<|end_header_id|>

{system_prompt}<|eot_id|><|start_header_id|>user<|end_header_id|>

{user_instruction}<|eot_id|><|start_header_id|>assistant<|end_header_id|>

```

**Compatible Models:**
- Llama 3, 3.1, 3.2 Instruct
- Llama 3.3 Instruct
- Fine-tunes based on Llama 3 architecture

#### **Mistral** (For Mistral Instruct models)
```
<s>[INST] {system_prompt}

{user_instruction} [/INST]
```

**Compatible Models:**
- Mistral 7B Instruct
- Mixtral 8x7B Instruct
- Mistral Small/Medium/Large Instruct

#### **Qwen** (For Qwen2/2.5 Instruct)
```
<|im_start|>system
{system_prompt}<|im_end|>
<|im_start|>user
{user_instruction}<|im_end|>
<|im_start|>assistant

```

**Compatible Models:**
- Qwen2 Instruct (all sizes)
- Qwen2.5 Instruct (all sizes)
- QwQ (reasoning model)

#### **GLM** (For ChatGLM models)
```
[gMASK]<sop><|system|>
{system_prompt}<|user|>
{user_instruction}<|assistant|>

```

**Compatible Models:**
- ChatGLM2
- ChatGLM3
- GLM-4

#### **Generic** (Basic instruction format)
```
### System:
{system_prompt}

### Instruction:
{user_instruction}

### Response:

```

**Compatible Models:**
- Alpaca-style models
- Vicuna models
- Other instruction-tuned models without specific formatting

### 3. Customize Template (Optional)

If the presets don't match your model, create a custom template:

1. Select "Custom" from the preset dropdown
2. Click "Customize" to edit the template
3. Configure these fields:

**Template Components:**

| Field | Description | Example |
|-------|-------------|---------|
| `bos_token` | Beginning of sequence token | `<|begin_of_text|>` |
| `eos_token` | End of sequence token | `<|eot_id|>` |
| `system_prefix` | Text before system prompt | `<|start_header_id|>system<|end_header_id|>\n\n` |
| `system_suffix` | Text after system prompt | `<|eot_id|>` |
| `instruction_prefix` | Text before user instruction | `<|start_header_id|>user<|end_header_id|>\n\n` |
| `instruction_suffix` | Text after user instruction | `<|eot_id|>` |
| `response_prefix` | Text before assistant response | `<|start_header_id|>assistant<|end_header_id|>\n\n` |

**Available Variables:**
- `{{system}}` - System prompt content
- `{{user_prompt}}` - User instruction content
- `{{bos}}` - Beginning of sequence token
- `{{eos}}` - End of sequence token

### 4. Test Your Template

Before using in production:

1. Click "Test Template" in the editor
2. Enter sample system and user prompts
3. Review the assembled prompt in the preview pane
4. Verify it matches your model's expected format
5. Test with actual generation to confirm

## Thinking Tag Removal

### What Are Thinking Tags?

Some models (especially reasoning models) include internal "thinking" or "reasoning" in their output:

```
<think>
Let me analyze the user's request...
The story needs more tension...
</think>

The character stepped into the dark room...
```

### Automatic Removal

Kahani automatically detects and strips these tags:

**Supported Patterns:**
- `<think>...</think>` (DeepSeek)
- `<reasoning>...</reasoning>` (Qwen)
- `[THINKING]...[/THINKING]`
- `[System]...[/System]`
- `[no_think]...[/no_think]`
- And more...

**Result:**
```
The character stepped into the dark room...
```

### Adding Custom Patterns

If your model uses different thinking tags:

1. Open `backend/app/services/llm/thinking_parser.py`
2. Add your pattern to the `THINKING_PATTERNS` list:
```python
THINKING_PATTERNS = [
    # ... existing patterns ...
    (r'<your_tag>.*?</your_tag>', re.DOTALL | re.IGNORECASE),
]
```
3. Restart the backend

## Advanced Configuration

### Template JSON Format

Templates are stored as JSON in the database:

```json
{
  "name": "Llama 3 Instruct",
  "bos_token": "<|begin_of_text|>",
  "eos_token": "<|eot_id|>",
  "system_prefix": "<|start_header_id|>system<|end_header_id|>\n\n",
  "system_suffix": "<|eot_id|>",
  "instruction_prefix": "<|start_header_id|>user<|end_header_id|>\n\n",
  "instruction_suffix": "<|eot_id|>",
  "response_prefix": "<|start_header_id|>assistant<|end_header_id|>\n\n"
}
```

### API Endpoints

For programmatic access:

**Get Available Presets:**
```bash
GET /api/settings/text-completion/presets
Authorization: Bearer YOUR_TOKEN
```

**Get Preset Template:**
```bash
GET /api/settings/text-completion/template/{preset_name}
Authorization: Bearer YOUR_TOKEN
```

**Test Template Rendering:**
```bash
POST /api/settings/text-completion/test-render
Authorization: Bearer YOUR_TOKEN
Content-Type: application/json

{
  "template": {...},
  "test_system": "You are a storyteller",
  "test_user": "Write a scene"
}
```

## Troubleshooting

### Problem: Model generates gibberish

**Symptoms:**
- Output doesn't make sense
- Model ignores instructions
- Produces random tokens

**Solutions:**
1. Verify template matches model's training format
2. Check model documentation for correct prompt format
3. Try a different preset template
4. Ensure you're using the instruction-tuned version of the model

### Problem: Generation stops immediately

**Symptoms:**
- Empty or very short output
- Generation ends after a few tokens

**Solutions:**
1. Check `response_prefix` is correct
2. Verify BOS/EOS tokens match the model's tokenizer
3. Some models are sensitive to exact spacing and newlines
4. Try removing or adjusting the `response_prefix`

### Problem: Thinking tags in output

**Symptoms:**
- Model's reasoning appears in the story
- Tags like `<think>` visible to users

**Solutions:**
1. Thinking tags should be auto-stripped
2. Check `backend/logs/kahani.log` for parser errors
3. Add custom pattern in `thinking_parser.py`
4. Report the pattern so we can add it to defaults

### Problem: Connection failed

**Symptoms:**
- "Connection failed" error
- "Invalid response format" error

**Solutions:**
1. Verify your backend supports `/v1/completions` endpoint
2. Test endpoint: `curl http://your-api/v1/completions`
3. Check if backend requires specific headers
4. Try Chat Completion mode instead
5. For TabbyAPI/LM Studio, ensure text completion is enabled

### Problem: Inconsistent results

**Symptoms:**
- Sometimes works, sometimes doesn't
- Quality varies significantly

**Solutions:**
1. Check generation parameters (temperature, top_p, etc.)
2. Verify template is consistently applied
3. Test with simpler prompts first
4. Check model's context length isn't exceeded

## Best Practices

### 1. Start with Presets
- Always try a preset template first
- Only customize if necessary
- Document any custom templates you create

### 2. Test Before Production
- Use the "Test Template" feature
- Try with simple prompts first
- Verify output quality with actual story generation

### 3. Monitor Output
- Check for thinking tags leaking through
- Watch for formatting issues
- Adjust template if needed

### 4. Model Selection
- Use instruction-tuned models, not base models
- Match template to model family
- Check model documentation for prompt format

### 5. Fallback Strategy
- Keep Chat Completion as fallback
- Document which mode works best for your setup
- Test both modes when trying new models

## Model Compatibility Matrix

| Model Family | Mode | Preset | Quality | Notes |
|--------------|------|--------|---------|-------|
| GPT-3.5/4 | Chat | N/A | ⭐⭐⭐⭐⭐ | Use Chat mode |
| Claude | Chat | N/A | ⭐⭐⭐⭐⭐ | Use Chat mode |
| Llama 3.x Instruct | Text | Llama 3 | ⭐⭐⭐⭐⭐ | Excellent with template |
| Mistral Instruct | Text | Mistral | ⭐⭐⭐⭐ | Works well |
| Qwen2/2.5 Instruct | Text | Qwen | ⭐⭐⭐⭐⭐ | Excellent with template |
| ChatGLM | Text | GLM | ⭐⭐⭐⭐ | Works well |
| DeepSeek | Text | Generic | ⭐⭐⭐⭐ | Thinking tags auto-removed |
| Ollama (any) | Chat | N/A | ⭐⭐⭐⭐ | Ollama handles formatting |
| Vicuna | Text | Generic | ⭐⭐⭐ | May need custom template |
| Alpaca | Text | Generic | ⭐⭐⭐ | Basic instruction format |

## Examples

### Example 1: Setting up Llama 3.1 Instruct

1. Configure your API endpoint (e.g., LM Studio, TabbyAPI)
2. Load Llama 3.1 Instruct model
3. In Kahani Settings:
   - API Type: OpenAI Compatible
   - API URL: `http://localhost:1234`
   - Model Name: Your model name
   - Completion Mode: Text Completion API
   - Preset: Llama 3
4. Test with a simple scene generation
5. Verify output quality

### Example 2: Custom Template for Vicuna

1. Select "Custom" preset
2. Click "Customize"
3. Configure:
   ```
   bos_token: ""
   eos_token: "</s>"
   system_prefix: "A chat between a curious user and an assistant. "
   system_suffix: "\n\n"
   instruction_prefix: "USER: "
   instruction_suffix: "\n"
   response_prefix: "ASSISTANT: "
   ```
4. Test template
5. Save settings

### Example 3: DeepSeek with Thinking Tags

1. Configure DeepSeek API endpoint
2. Select "Generic" preset
3. Generate content
4. Thinking tags are automatically removed
5. Only the final output is shown to users

## FAQ

**Q: Can I switch between Chat and Text modes?**
A: Yes! You can switch anytime in Settings. Your choice is saved per user.

**Q: Will my existing stories work with Text Completion?**
A: Yes! The mode only affects new generations, not existing content.

**Q: Can I use different templates for different stories?**
A: Currently, the template is a global user setting. All stories use the same mode/template.

**Q: Do I need to restart after changing templates?**
A: No, template changes take effect immediately.

**Q: Can I export/import custom templates?**
A: Not yet, but you can copy the JSON from the editor and save it externally.

**Q: What if my model isn't listed?**
A: Try the Generic preset first, then customize if needed. Check your model's documentation for the correct prompt format.

**Q: Does this work with streaming?**
A: Yes! Text Completion supports streaming just like Chat Completion.

**Q: Are thinking tags removed in real-time during streaming?**
A: Yes, thinking tag removal works for both streaming and non-streaming responses.

## Support

If you encounter issues:

1. Check the troubleshooting section above
2. Review `backend/logs/kahani.log` for errors
3. Test with a known-working preset (e.g., Llama 3)
4. Open an issue on GitHub with:
   - Model name and version
   - Template configuration
   - Error messages
   - Example prompts that fail

## Future Enhancements

Planned features:
- Per-story template selection
- Template import/export
- More pre-built templates
- Template validation UI
- Community template sharing
- Multi-turn conversation templates
- Template versioning

---

**Last Updated:** October 31, 2025
**Version:** 1.0

