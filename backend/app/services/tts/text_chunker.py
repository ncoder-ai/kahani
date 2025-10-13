"""
Text Chunking Service for TTS

Intelligently splits text into chunks suitable for TTS synthesis.
Respects sentence and paragraph boundaries for natural audio flow.
"""

import re
from typing import List, Optional
from dataclasses import dataclass


@dataclass
class TextChunk:
    """Represents a chunk of text for TTS processing"""
    text: str
    index: int
    start_pos: int
    end_pos: int
    is_sentence_boundary: bool = True
    is_paragraph_boundary: bool = False


class TextChunker:
    """
    Intelligently chunks text for TTS synthesis.
    
    Features:
    - Respects sentence boundaries
    - Respects paragraph boundaries
    - Configurable max chunk size
    - Preserves punctuation and whitespace
    - Handles edge cases (very long sentences, etc.)
    """
    
    def __init__(
        self,
        max_chunk_size: int = 280,
        min_chunk_size: int = 50,
        respect_sentences: bool = True,
        respect_paragraphs: bool = True
    ):
        """
        Initialize text chunker.
        
        Args:
            max_chunk_size: Maximum characters per chunk
            min_chunk_size: Minimum characters per chunk (avoid tiny chunks)
            respect_sentences: Try to avoid breaking sentences
            respect_paragraphs: Try to keep paragraphs together
        """
        self.max_chunk_size = max_chunk_size
        self.min_chunk_size = min_chunk_size
        self.respect_sentences = respect_sentences
        self.respect_paragraphs = respect_paragraphs
        
        # Sentence boundary patterns
        self.sentence_end_pattern = re.compile(r'[.!?]+[\s\n]+|[.!?]+$')
        
        # Paragraph boundary pattern
        self.paragraph_pattern = re.compile(r'\n\s*\n')
    
    def chunk_text(self, text: str) -> List[TextChunk]:
        """
        Split text into chunks suitable for TTS.
        
        Args:
            text: The text to chunk
            
        Returns:
            List of TextChunk objects
        """
        if not text or not text.strip():
            return []
        
        # If text is short enough, return as single chunk
        if len(text) <= self.max_chunk_size:
            return [TextChunk(
                text=text,
                index=0,
                start_pos=0,
                end_pos=len(text),
                is_sentence_boundary=True,
                is_paragraph_boundary=True
            )]
        
        # Split by paragraphs first if enabled
        if self.respect_paragraphs:
            paragraphs = self._split_paragraphs(text)
            chunks = []
            current_pos = 0
            
            for para in paragraphs:
                para_chunks = self._chunk_paragraph(para, current_pos, len(chunks))
                chunks.extend(para_chunks)
                current_pos += len(para)
            
            return chunks
        else:
            return self._chunk_paragraph(text, 0, 0)
    
    def _split_paragraphs(self, text: str) -> List[str]:
        """Split text into paragraphs."""
        paragraphs = self.paragraph_pattern.split(text)
        # Filter out empty paragraphs
        return [p for p in paragraphs if p.strip()]
    
    def _chunk_paragraph(
        self,
        paragraph: str,
        start_offset: int,
        chunk_index_offset: int
    ) -> List[TextChunk]:
        """
        Chunk a single paragraph.
        
        Args:
            paragraph: The paragraph text
            start_offset: Position offset for this paragraph in original text
            chunk_index_offset: Starting index for chunks
            
        Returns:
            List of TextChunk objects
        """
        if len(paragraph) <= self.max_chunk_size:
            return [TextChunk(
                text=paragraph,
                index=chunk_index_offset,
                start_pos=start_offset,
                end_pos=start_offset + len(paragraph),
                is_sentence_boundary=True,
                is_paragraph_boundary=True
            )]
        
        chunks = []
        
        if self.respect_sentences:
            # Split by sentences
            sentences = self._split_sentences(paragraph)
            current_chunk = ""
            chunk_start = start_offset
            
            for sentence in sentences:
                # If adding this sentence exceeds max size
                if len(current_chunk) + len(sentence) > self.max_chunk_size:
                    # If current chunk has content, save it
                    if current_chunk and len(current_chunk.strip()) >= self.min_chunk_size:
                        chunks.append(TextChunk(
                            text=current_chunk,
                            index=chunk_index_offset + len(chunks),
                            start_pos=chunk_start,
                            end_pos=chunk_start + len(current_chunk),
                            is_sentence_boundary=True,
                            is_paragraph_boundary=False
                        ))
                        chunk_start += len(current_chunk)
                        current_chunk = ""
                    
                    # If sentence itself is too long, split it
                    if len(sentence) > self.max_chunk_size:
                        sentence_chunks = self._split_long_sentence(
                            sentence,
                            chunk_start,
                            chunk_index_offset + len(chunks)
                        )
                        chunks.extend(sentence_chunks)
                        chunk_start += len(sentence)
                    else:
                        current_chunk = sentence
                else:
                    current_chunk += sentence
            
            # Add remaining chunk
            if current_chunk.strip():
                chunks.append(TextChunk(
                    text=current_chunk,
                    index=chunk_index_offset + len(chunks),
                    start_pos=chunk_start,
                    end_pos=chunk_start + len(current_chunk),
                    is_sentence_boundary=True,
                    is_paragraph_boundary=True
                ))
        else:
            # Simple character-based chunking
            chunks = self._simple_chunk(paragraph, start_offset, chunk_index_offset)
        
        return chunks
    
    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences."""
        sentences = []
        last_end = 0
        
        for match in self.sentence_end_pattern.finditer(text):
            sentence = text[last_end:match.end()]
            if sentence.strip():
                sentences.append(sentence)
            last_end = match.end()
        
        # Add remaining text
        if last_end < len(text):
            remaining = text[last_end:]
            if remaining.strip():
                sentences.append(remaining)
        
        return sentences if sentences else [text]
    
    def _split_long_sentence(
        self,
        sentence: str,
        start_offset: int,
        chunk_index_offset: int
    ) -> List[TextChunk]:
        """Split a very long sentence at natural break points."""
        chunks = []
        
        # Try to split at commas, semicolons, or conjunctions
        break_points = [
            (m.end(), False) for m in re.finditer(r'[,;]\s+', sentence)
        ]
        
        if not break_points:
            # No natural breaks, split by words
            return self._simple_chunk(sentence, start_offset, chunk_index_offset)
        
        current_chunk = ""
        chunk_start = start_offset
        last_pos = 0
        
        for break_pos, _ in break_points:
            segment = sentence[last_pos:break_pos]
            
            if len(current_chunk) + len(segment) > self.max_chunk_size:
                if current_chunk:
                    chunks.append(TextChunk(
                        text=current_chunk,
                        index=chunk_index_offset + len(chunks),
                        start_pos=chunk_start,
                        end_pos=chunk_start + len(current_chunk),
                        is_sentence_boundary=False
                    ))
                    chunk_start += len(current_chunk)
                current_chunk = segment
            else:
                current_chunk += segment
            
            last_pos = break_pos
        
        # Add remaining
        remaining = sentence[last_pos:]
        if remaining:
            current_chunk += remaining
        
        if current_chunk:
            chunks.append(TextChunk(
                text=current_chunk,
                index=chunk_index_offset + len(chunks),
                start_pos=chunk_start,
                end_pos=chunk_start + len(current_chunk),
                is_sentence_boundary=True
            ))
        
        return chunks
    
    def _simple_chunk(
        self,
        text: str,
        start_offset: int,
        chunk_index_offset: int
    ) -> List[TextChunk]:
        """Simple word-boundary-aware chunking."""
        chunks = []
        words = text.split()
        current_chunk = ""
        chunk_start = start_offset
        
        for word in words:
            # Check if adding this word would exceed max size
            test_chunk = current_chunk + (" " if current_chunk else "") + word
            
            if len(test_chunk) > self.max_chunk_size:
                if current_chunk:
                    chunks.append(TextChunk(
                        text=current_chunk,
                        index=chunk_index_offset + len(chunks),
                        start_pos=chunk_start,
                        end_pos=chunk_start + len(current_chunk),
                        is_sentence_boundary=False
                    ))
                    chunk_start += len(current_chunk) + 1  # +1 for space
                    current_chunk = word
                else:
                    # Single word is too long, split it
                    chunks.append(TextChunk(
                        text=word[:self.max_chunk_size],
                        index=chunk_index_offset + len(chunks),
                        start_pos=chunk_start,
                        end_pos=chunk_start + self.max_chunk_size,
                        is_sentence_boundary=False
                    ))
                    chunk_start += self.max_chunk_size
                    current_chunk = word[self.max_chunk_size:]
            else:
                current_chunk = test_chunk
        
        # Add remaining chunk
        if current_chunk:
            chunks.append(TextChunk(
                text=current_chunk,
                index=chunk_index_offset + len(chunks),
                start_pos=chunk_start,
                end_pos=chunk_start + len(current_chunk),
                is_sentence_boundary=False
            ))
        
        return chunks
    
    def get_chunk_summary(self, chunks: List[TextChunk]) -> dict:
        """Get summary statistics for chunks."""
        if not chunks:
            return {
                "total_chunks": 0,
                "total_characters": 0,
                "avg_chunk_size": 0,
                "min_chunk_size": 0,
                "max_chunk_size": 0,
                "sentence_boundaries": 0,
                "paragraph_boundaries": 0
            }
        
        sizes = [len(chunk.text) for chunk in chunks]
        
        return {
            "total_chunks": len(chunks),
            "total_characters": sum(sizes),
            "avg_chunk_size": sum(sizes) / len(sizes),
            "min_chunk_size": min(sizes),
            "max_chunk_size": max(sizes),
            "sentence_boundaries": sum(1 for c in chunks if c.is_sentence_boundary),
            "paragraph_boundaries": sum(1 for c in chunks if c.is_paragraph_boundary)
        }
