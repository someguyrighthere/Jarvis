#!/usr/bin/env python
"""Test script to simulate voice input and check if Sara responds"""
import time
import os

test_commands = [
    ("hello sara", 5),
    ("sara what is python", 8),
    ("open chrome", 4),
]

for command, wait_time in test_commands:
    print(f"\n{'='*60}")
    print(f"Testing command: '{command}'")
    print(f"{'='*60}")
    
    # Write command to input.txt
    with open("input.txt", "w", encoding="utf-8") as f:
        f.write(command)
    print(f"✓ Written to input.txt")
    
    # Wait for processing
    print(f"⏱ Waiting {wait_time} seconds...")
    time.sleep(wait_time)
    
    # Check if log was updated
    if os.path.exists("log.txt"):
        with open("log.txt", "r", encoding="utf-8") as f:
            content = f.read()
            if content.strip():
                print(f"\n✓ Log file updated:")
                print(content[-500:])  # Last 500 chars
            else:
                print("⚠ Log file is empty")
    else:
        print("⚠ Log file doesn't exist")

print(f"\n{'='*60}")
print("Test complete!")
print(f"{'='*60}")
