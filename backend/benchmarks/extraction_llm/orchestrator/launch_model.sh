#!/usr/bin/env bash
# Launch a GGUF model via ik_llama.cpp.
#
# Usage: launch_model.sh <gguf-path> [ctx-size] [port]
#
# Defaults match production extraction-LLM config:
#   ctx=32768, KV q8_0, FA on, single GPU 0, port 5002, jinja chat template.
#
# Configurable via env vars (export before calling):
#   IK_LLAMA_BIN   path to llama-server binary (default: $HOME/App/ik_llama.cpp/build/bin/llama-server)
#   CUDA_DEVICE    GPU index (default: 0)

set -euo pipefail

MODEL_PATH="${1:?usage: launch_model.sh <gguf-path> [ctx-size] [port]}"
CTX_SIZE="${2:-32768}"
PORT="${3:-5002}"

if [[ ! -f "$MODEL_PATH" ]]; then
  echo "ERROR: model file not found: $MODEL_PATH" >&2
  exit 1
fi

export CUDA_VISIBLE_DEVICES="${CUDA_DEVICE:-0}"
BIN="${IK_LLAMA_BIN:-$HOME/App/ik_llama.cpp/build/bin/llama-server}"

if [[ ! -x "$BIN" ]]; then
  echo "ERROR: ik_llama llama-server binary not found at $BIN" >&2
  echo "       Set IK_LLAMA_BIN env var to override." >&2
  exit 1
fi

echo "Launching $MODEL_PATH on port $PORT (ctx=$CTX_SIZE)"
exec "$BIN" \
  --model        "$MODEL_PATH" \
  --ctx-size     "$CTX_SIZE" \
  --n-gpu-layers 999 \
  --split-mode   none \
  --main-gpu     0 \
  --flash-attn   on \
  --cache-type-k q8_0 \
  --cache-type-v q8_0 \
  --context-shift on \
  --batch-size   2048 \
  --ubatch-size  512 \
  --threads      13 \
  --parallel     1 \
  --host         0.0.0.0 \
  --port         "$PORT" \
  --jinja
