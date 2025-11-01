# Text Completion Test Scripts

These scripts test text completion at different levels to diagnose issues.

## Prerequisites

1. **LM Studio running** with Qwen3-30B model loaded
2. **Update configuration** in each script:
   - `API_URL`: Your LM Studio URL (default: `http://localhost:1234`)
   - `MODEL_NAME`: Your exact model name (default: `qwen3-coder-30b-a3b-instruct-mlx`)

## Test Scripts

### 1. Direct HTTP Test (Simplest)
Tests the `/v1/completions` endpoint directly without any framework.

```bash
cd /Users/user/apps/kahani
python3 test_text_completion_direct.py
```

**What it tests:**
- Basic HTTP connectivity to LM Studio
- `/v1/completions` endpoint availability
- Raw text generation without templates

**Expected output:**
- Status 200
- Generated text that continues "Once upon a time, in a land far away,"

### 2. Template Test (With Qwen Format)
Tests text completion with proper Qwen template formatting.

```bash
python3 test_text_completion_with_template.py
```

**What it tests:**
- Qwen template rendering (`<|im_start|>`, `<|im_end|>` tokens)
- System + user prompt formatting
- Template token cleanup

**Expected output:**
- Properly formatted prompt with Qwen tokens
- Generated narrative text about a forest
- No template tokens in final output

### 3. Kahani Integration Test (Full Stack)
Tests using Kahani's actual LLM service code.

```bash
python3 test_text_completion_kahani.py
```

**What it tests:**
- Full Kahani text completion pipeline
- Template manager integration
- Thinking tag removal
- Both streaming and non-streaming

**Expected output:**
- Generated story text about a library
- Streaming generation working
- No template artifacts

## Interpreting Results

### ✅ Success Indicators
- Status code 200
- Generated text > 50 characters
- Text is coherent narrative
- No template tokens (`<|im_start|>`, `<|im_end|>`) in output
- No excessive line breaks

### ❌ Failure Indicators
- Connection errors → Check LM Studio is running
- 404 errors → Check API URL and endpoint
- Empty/short text → Check model is loaded
- Garbage text → Template formatting issue
- Template tokens in output → Cleanup not working

## Common Issues

### Issue: "Connection refused"
**Solution:** Start LM Studio and load the model

### Issue: "404 Not Found"
**Solution:** Check API URL, try:
- `http://localhost:1234`
- `http://127.0.0.1:1234`

### Issue: Generated text is gibberish
**Possible causes:**
1. **Wrong template** - Qwen3 might need different format
2. **Model not instruction-tuned** - Need instruct variant
3. **Template tokens not stripped** - Check stop sequences

**Debug steps:**
1. Run test 1 (direct) - if this works, template is the issue
2. Check LM Studio logs for the actual request format
3. Try different template preset (generic, llama3)

### Issue: Text contains `<|im_start|>` or `<|im_end|>`
**Solution:** Stop sequences not working, need to add them to the request

## Next Steps After Testing

1. **If test 1 fails:** LM Studio connection issue
2. **If test 1 passes, test 2 fails:** Template format issue for Qwen3
3. **If test 2 passes, test 3 fails:** Kahani integration issue
4. **If all pass but app fails:** Settings not being saved/loaded correctly

## Adjusting for Your Model

If you're using a different model or it's not Qwen3:

1. **Check model's prompt format** in LM Studio or model card
2. **Update template** in `test_text_completion_with_template.py`
3. **Update preset** in `test_text_completion_kahani.py` (line 42)

Common templates:
- **Llama 3**: `<|begin_of_text|><|start_header_id|>system<|end_header_id|>`
- **Mistral**: `<s>[INST] {prompt} [/INST]`
- **Qwen**: `<|im_start|>system\n{prompt}<|im_end|>`
- **Generic**: `### System:\n{system}\n### Instruction:\n{user}\n### Response:\n`

