"""
Semantic Trace Logger

Captures and logs all semantic memory operations for debugging and analysis.
Creates detailed trace files showing prompts, embeddings, and model interactions.
"""

import os
import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class SemanticTraceLogger:
    """
    Logger for tracing semantic memory operations.
    Creates markdown files with detailed traces.
    """
    
    def __init__(self, trace_dir: str = "./traces"):
        self.trace_dir = Path(trace_dir)
        self.trace_dir.mkdir(exist_ok=True)
        self.current_trace_file: Optional[Path] = None
        self.trace_data = []
    
    def start_scene_trace(self, story_id: int, scene_sequence: int):
        """Start a new trace for scene generation"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"semantic_trace_story{story_id}_scene{scene_sequence}_{timestamp}.md"
        self.current_trace_file = self.trace_dir / filename
        self.trace_data = []
        
        # Write header
        with open(self.current_trace_file, 'w') as f:
            f.write(f"# Semantic Memory Trace\n\n")
            f.write(f"**Story ID:** {story_id}\n")
            f.write(f"**Scene Sequence:** {scene_sequence}\n")
            f.write(f"**Timestamp:** {datetime.now().isoformat()}\n")
            f.write(f"\n---\n\n")
        
        logger.info(f"Started semantic trace: {self.current_trace_file}")
    
    def log_step(self, step_name: str, content: Dict[str, Any]):
        """Log a step in the trace"""
        if not self.current_trace_file:
            return
        
        self.trace_data.append({
            "step": step_name,
            "timestamp": datetime.now().isoformat(),
            "content": content
        })
        
        with open(self.current_trace_file, 'a') as f:
            f.write(f"## {step_name}\n\n")
            f.write(f"**Time:** {datetime.now().strftime('%H:%M:%S.%f')[:-3]}\n\n")
            
            for key, value in content.items():
                f.write(f"### {key}\n\n")
                
                if isinstance(value, (dict, list)):
                    f.write(f"```json\n{json.dumps(value, indent=2, ensure_ascii=False)}\n```\n\n")
                elif isinstance(value, str) and len(value) > 200:
                    # Long text, use code block
                    f.write(f"```\n{value}\n```\n\n")
                else:
                    f.write(f"{value}\n\n")
            
            f.write("---\n\n")
    
    def log_context_assembly(self, context_parts: Dict[str, Any]):
        """Log the context assembly process"""
        self.log_step("1. Context Assembly", context_parts)
    
    def log_semantic_search(self, query: str, results: list):
        """Log semantic search query and results"""
        self.log_step("2. Semantic Search (Bi-Encoder)", {
            "Query Text": query[:500] + "..." if len(query) > 500 else query,
            "Query Length (chars)": len(query),
            "Results Count": len(results),
            "Results": results
        })
    
    def log_reranking(self, query: str, candidates: list, reranked: list):
        """Log cross-encoder reranking"""
        self.log_step("3. Cross-Encoder Reranking", {
            "Query": query[:300] + "..." if len(query) > 300 else query,
            "Initial Candidates": len(candidates),
            "Candidates Details": [
                {
                    "scene_id": c.get("scene_id"),
                    "sequence": c.get("sequence"),
                    "bi_encoder_score": c.get("bi_encoder_score", 0)
                } for c in candidates
            ],
            "After Reranking": [
                {
                    "scene_id": r.get("scene_id"),
                    "sequence": r.get("sequence"),
                    "bi_encoder_score": r.get("bi_encoder_score", 0),
                    "rerank_score": r.get("rerank_score", 0),
                    "final_similarity": r.get("similarity_score", 0)
                } for r in reranked
            ]
        })
    
    def log_embedding_generation(self, text: str, embedding_dim: int):
        """Log embedding generation"""
        self.log_step("4. Embedding Generation", {
            "Text Preview": text[:500] + "..." if len(text) > 500 else text,
            "Text Length (chars)": len(text),
            "Embedding Dimension": embedding_dim,
            "Model": "sentence-transformers/all-MiniLM-L6-v2"
        })
    
    def log_llm_prompt(self, prompt_type: str, system_prompt: str, user_prompt: str, params: Dict[str, Any]):
        """Log LLM prompt"""
        self.log_step(f"5. LLM Call - {prompt_type}", {
            "System Prompt": system_prompt,
            "User Prompt": user_prompt,
            "Parameters": params,
            "System Prompt Tokens (approx)": len(system_prompt.split()),
            "User Prompt Tokens (approx)": len(user_prompt.split()),
            "Total Tokens (approx)": len(system_prompt.split()) + len(user_prompt.split())
        })
    
    def log_entity_extraction_prompt(self, scene_content: str, prompt: str):
        """Log entity state extraction prompt"""
        self.log_step("6. Entity State Extraction (LLM Call)", {
            "Scene Content": scene_content[:1000] + "..." if len(scene_content) > 1000 else scene_content,
            "Extraction Prompt": prompt,
            "Purpose": "Extract character states, locations, objects, and relationships"
        })
    
    def log_entity_extraction_result(self, extracted_data: Dict[str, Any]):
        """Log entity extraction results"""
        self.log_step("7. Entity States Extracted", {
            "Characters Updated": extracted_data.get("characters_updated", 0),
            "Locations Updated": extracted_data.get("locations_updated", 0),
            "Objects Updated": extracted_data.get("objects_updated", 0),
            "Raw Extraction": extracted_data.get("raw_extraction", {})
        })
    
    def log_final_context(self, final_context: str, token_count: int):
        """Log the final assembled context sent to LLM"""
        self.log_step("8. Final Context for Scene Generation", {
            "Context": final_context,
            "Token Count": token_count,
            "Context Length (chars)": len(final_context)
        })
    
    def log_scene_generation_result(self, generated_content: str, choices: list):
        """Log the generated scene"""
        self.log_step("9. Generated Scene", {
            "Content": generated_content,
            "Content Length (chars)": len(generated_content),
            "Choices Generated": len(choices),
            "Choices": choices
        })
    
    def finalize_trace(self):
        """Finalize and close the trace file"""
        if not self.current_trace_file:
            return
        
        with open(self.current_trace_file, 'a') as f:
            f.write("\n\n## Summary\n\n")
            f.write(f"**Total Steps:** {len(self.trace_data)}\n")
            f.write(f"**Trace Complete:** {datetime.now().isoformat()}\n")
            f.write(f"\n**Trace saved to:** `{self.current_trace_file}`\n")
        
        logger.info(f"Finalized semantic trace: {self.current_trace_file}")
        return str(self.current_trace_file)


# Global instance
_trace_logger: Optional[SemanticTraceLogger] = None


def get_trace_logger() -> SemanticTraceLogger:
    """Get or create the global trace logger"""
    global _trace_logger
    if _trace_logger is None:
        _trace_logger = SemanticTraceLogger()
    return _trace_logger


def is_tracing_enabled() -> bool:
    """Check if tracing is enabled via environment variable"""
    return os.getenv("ENABLE_SEMANTIC_TRACING", "false").lower() == "true"


