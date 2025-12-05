#!/usr/bin/env python3
"""
Test script to compare JSON messages across multiple log files.
Ensures all messages are identical except for the last message in each file.
"""

import json
import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple


def load_json_file(filepath: Path) -> List[Dict[str, Any]]:
    """Load and parse JSON from a file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: File not found: {filepath}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in {filepath}: {e}", file=sys.stderr)
        sys.exit(1)


def compare_messages(
    messages_list: List[List[Dict[str, Any]]],
    filenames: List[str]
) -> Tuple[bool, List[str]]:
    """
    Compare messages across all files.
    Returns (all_match, error_messages)
    """
    errors = []
    
    # Check that all files have the same number of messages
    lengths = [len(msgs) for msgs in messages_list]
    if len(set(lengths)) > 1:
        error_msg = f"Files have different message counts: {dict(zip(filenames, lengths))}"
        errors.append(error_msg)
        return False, errors
    
    num_messages = lengths[0]
    
    if num_messages == 0:
        errors.append("All files are empty")
        return False, errors
    
    # Compare all messages except the last one
    all_match = True
    for msg_idx in range(num_messages - 1):
        # Get the first file's message as reference
        reference_msg = messages_list[0][msg_idx]
        
        # Compare with all other files
        for file_idx in range(1, len(messages_list)):
            current_msg = messages_list[file_idx][msg_idx]
            
            if reference_msg != current_msg:
                all_match = False
                error_msg = (
                    f"Message {msg_idx} differs between files:\n"
                    f"  Reference ({filenames[0]}): {json.dumps(reference_msg, indent=2)}\n"
                    f"  Different ({filenames[file_idx]}): {json.dumps(current_msg, indent=2)}"
                )
                errors.append(error_msg)
    
    # Check that last messages are different (expected)
    last_messages = [msgs[-1] for msgs in messages_list]
    all_last_same = all(msg == last_messages[0] for msg in last_messages[1:])
    
    if all_last_same:
        errors.append("WARNING: Last messages are identical across all files (expected to differ)")
    
    return all_match, errors


def print_summary(
    messages_list: List[List[Dict[str, Any]]],
    filenames: List[str],
    all_match: bool,
    errors: List[str]
):
    """Print test summary and results."""
    print("=" * 80)
    print("MESSAGE COMPARISON TEST")
    print("=" * 80)
    print()
    
    # Print file info
    print("Files being compared:")
    for i, filename in enumerate(filenames):
        num_msgs = len(messages_list[i])
        print(f"  {i+1}. {filename} ({num_msgs} messages)")
    print()
    
    # Print message count info
    lengths = [len(msgs) for msgs in messages_list]
    if len(set(lengths)) == 1:
        print(f"All files have {lengths[0]} messages")
        print(f"Comparing first {lengths[0] - 1} messages (last message expected to differ)")
    print()
    
    # Print results
    if all_match and not errors:
        print("✓ SUCCESS: All messages (except last) are identical across all files")
        print()
        
        # Show last messages are different
        print("Last messages (expected to differ):")
        for filename, msgs in zip(filenames, messages_list):
            last_msg = msgs[-1]
            print(f"\n{filename}:")
            print(f"  Role: {last_msg.get('role', 'N/A')}")
            content_preview = last_msg.get('content', '')[:100]
            print(f"  Content preview: {content_preview}...")
    else:
        print("✗ FAILURE: Differences found in non-final messages")
        print()
        for error in errors:
            print(error)
            print()
    
    print("=" * 80)


def main():
    """Main test execution."""
    # Define file paths
    log_dir = Path(__file__).parent / "logs"
    
    files = [
        log_dir / "prompt_sent new scene.txt",
        log_dir / "prompt_sent variant.txt",
        log_dir / "prompt_sent guided variant.txt",
        log_dir / "prompt_sent continue.txt",
        log_dir / "prompt_choice_sent json.txt",
    ]
    
    filenames = [f.name for f in files]
    
    # Load all files
    print("Loading JSON files...")
    messages_list = [load_json_file(f) for f in files]
    print(f"Loaded {len(messages_list)} files\n")
    
    # Compare messages
    all_match, errors = compare_messages(messages_list, filenames)
    
    # Print summary
    print_summary(messages_list, filenames, all_match, errors)
    
    # Exit with appropriate code
    if all_match:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
