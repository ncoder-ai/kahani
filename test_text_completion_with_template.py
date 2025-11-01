#!/usr/bin/env python3
"""
Test text completion with Qwen template formatting.
This tests if the template is being applied correctly.
"""

import httpx
import json
import sys

# Configuration
API_URL = "http://localhost:1234"  # Change to your LM Studio URL
MODEL_NAME = "qwen3-coder-30b-a3b-instruct-mlx"  # Change to your model name

# Qwen template format
QWEN_TEMPLATE = {
    "bos_token": "<|im_start|>",
    "eos_token": "<|im_end|>",
    "system_prefix": "<|im_start|>system\n",
    "system_suffix": "<|im_end|>\n",
    "instruction_prefix": "<|im_start|>user\n",
    "instruction_suffix": "<|im_end|>\n",
    "response_prefix": "<|im_start|>assistant\n"
}

def render_template(system_prompt, user_prompt):
    """Render the Qwen template with prompts"""
    parts = []
    
    # Add BOS token
    if QWEN_TEMPLATE["bos_token"]:
        parts.append(QWEN_TEMPLATE["bos_token"])
    
    # Add system prompt
    if system_prompt:
        parts.append(QWEN_TEMPLATE["system_prefix"])
        parts.append(system_prompt)
        parts.append(QWEN_TEMPLATE["system_suffix"])
    
    # Add user instruction
    parts.append(QWEN_TEMPLATE["instruction_prefix"])
    parts.append(user_prompt)
    parts.append(QWEN_TEMPLATE["instruction_suffix"])
    
    # Add response prefix
    parts.append(QWEN_TEMPLATE["response_prefix"])
    
    return ''.join(parts)

def test_with_template():
    """Test text completion with proper Qwen template"""
    
    system_prompt = "You are a creative storyteller. Write engaging narrative text."
    user_prompt = "Write a short paragraph about a mysterious forest."
    
    # Render the template
    full_prompt = render_template(system_prompt, user_prompt)
    
    # Determine endpoint URL
    if API_URL.endswith("/v1"):
        endpoint_url = f"{API_URL}/completions"
    else:
        endpoint_url = f"{API_URL}/v1/completions"
    
    # Prepare payload
    payload = {
        "model": MODEL_NAME,
        "prompt": full_prompt,
        "max_tokens": 200,
        "temperature": 0.7,
        "stop": [QWEN_TEMPLATE["eos_token"]],  # Stop at end token
        "stream": False
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    print("=" * 80)
    print("TEXT COMPLETION WITH QWEN TEMPLATE TEST")
    print("=" * 80)
    print(f"\nEndpoint: {endpoint_url}")
    print(f"Model: {MODEL_NAME}")
    print(f"\nSystem Prompt: {system_prompt}")
    print(f"User Prompt: {user_prompt}")
    print("\n" + "-" * 80)
    print("RENDERED TEMPLATE:")
    print("-" * 80)
    print(full_prompt)
    print("-" * 80)
    print("\nSending request...")
    
    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                endpoint_url,
                json=payload,
                headers=headers
            )
            
            print(f"\nStatus Code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print("\n✅ SUCCESS!")
                
                if "choices" in data and len(data["choices"]) > 0:
                    generated_text = data["choices"][0].get("text", "")
                    
                    print("\n" + "=" * 80)
                    print("RAW GENERATED TEXT:")
                    print("=" * 80)
                    print(repr(generated_text))
                    print("=" * 80)
                    
                    print("\n" + "=" * 80)
                    print("CLEANED GENERATED TEXT:")
                    print("=" * 80)
                    # Remove any remaining template tokens
                    cleaned = generated_text.replace(QWEN_TEMPLATE["eos_token"], "").strip()
                    print(cleaned)
                    print("=" * 80)
                    
                    # Analyze the output
                    print("\n" + "=" * 80)
                    print("ANALYSIS:")
                    print("=" * 80)
                    print(f"Length: {len(generated_text)} characters")
                    print(f"Cleaned length: {len(cleaned)} characters")
                    print(f"Contains template tokens: {QWEN_TEMPLATE['eos_token'] in generated_text}")
                    print(f"Looks like narrative text: {len(cleaned.split()) > 10}")
                    
                    if len(cleaned) > 20 and len(cleaned.split()) > 10:
                        print("\n✅ Text generation appears successful!")
                        return True
                    else:
                        print("\n❌ Generated text seems problematic!")
                        return False
                else:
                    print("\n❌ No choices in response!")
                    return False
            else:
                print(f"\n❌ FAILED with status {response.status_code}")
                print("Response body:")
                print(response.text)
                return False
                
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_with_template()
    sys.exit(0 if success else 1)

