#!/usr/bin/env python3
"""Fix line endings in install.sh"""
import sys

file_path = 'backend/scripts/install.sh'

with open(file_path, 'rb') as f:
    content = f.read()

# Replace CRLF with LF
fixed_content = content.replace(b'\r\n', b'\n')

# Also remove any standalone CR characters
fixed_content = fixed_content.replace(b'\r', b'\n')

with open(file_path, 'wb') as f:
    f.write(fixed_content)

print(f"Fixed line endings in {file_path}")
