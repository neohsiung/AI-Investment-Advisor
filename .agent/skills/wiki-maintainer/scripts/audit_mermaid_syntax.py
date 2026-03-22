import os
import re
import argparse

def audit_mermaid_in_file(filepath, fix=False):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find all mermaid blocks
    # Using non-greedy match for content
    mermaid_blocks = re.findall(r'```mermaid\n(.*?)\n```', content, re.DOTALL)
    if not mermaid_blocks:
        return 0, content

    new_content = content
    warnings = 0

    # Heuristic 1: Extra trailing quotes in sequence diagram messages or labels
    # Example: Agents-->>CIO: 返回分項報告 (Markdown)"
    # Pattern: Look for lines ending with a quote in a message
    
    # We'll process each block separately to avoid matching outside
    matches = list(re.finditer(r'(```mermaid\n)(.*?)(\n```)', content, re.DOTALL))
    offset = 0
    
    for match in matches:
        block_start = match.start(2)
        block_end = match.end(2)
        block_content = match.group(2)
        
        modified_block = block_content
        
        # 1. First Pass: Resolve misplaced quotes like ["Label (text")] or ["Label]"]
        def fix_node_quoting(block):
            # Move quotes outside of labels correctly
            # Fix ["Label (text")] -> ["Label (text)"]
            # Matches ID["Label (text")] where ] is misplaced relative to "
            # Uses backrefs to ensure matching bracket pairs
            patterns = [
                (r'(\w+)\["(.*?)(")(\])', r'\1["\2\4"]'),
                (r'(\w+)\("(.*?)(")(\))', r'\1("\2\4")'),
                (r'(\w+)\{"(.*?)(")(\})', r'\1{"\2\4"}'),
            ]
            for pat, repl in patterns:
                block = re.sub(pat, repl, block)
            
            # Clean up accidental double quotes and fix dangling quotes at ends of lines
            lines = block.split('\n')
            fixed_lines = []
            for line in lines:
                if line.count('"') % 2 != 0:
                    # If line has odd quotes and ends with a node closer, it's missing a quote before the closer
                    line = re.sub(r'(\[|\{|\()([^"\]\}\)]+)(\]|\}|\))$', r'\1"\2"\3', line)
                fixed_lines.append(line)
            return '\n'.join(fixed_lines).replace('""', '"')

        # 2. Second Pass: Ensure special chars are quoted
        def ensure_quotes(block):
            def replacer(m):
                node_id, b_open, label, b_close = m.groups()
                # Skip if already quoted correctly
                if label.startswith('"') and label.endswith('"'):
                    return m.group(0)
                # If contains special chars, wrap the WHOLE label in quotes
                if any(c in label for c in '()[]&:|<>'):
                    return f'{node_id}{b_open}"{label}"{b_close}'
                return m.group(0)
            
            # Match ID[Label]
            block = re.sub(r'(\w+)([\[\(\{])([^"\[\(\{\]\}\)\n]+)([\]\)\}])', replacer, block)
            return block

        # Apply fixes
        temp_block = modified_block
        temp_block = fix_node_quoting(temp_block)
        temp_block = ensure_quotes(temp_block)
        
        # 3. Clean up TRULY safe labels
        def clean_safe_labels(block):
            def replacer(m):
                node_id, b_open, label, b_close = m.groups()
                # If ONLY safe chars, remove quotes
                if re.match(r'^[\w\s\u4e00-\u9fa5\-\.,]+$', label):
                    return f"{node_id}{b_open}{label}{b_close}"
                return m.group(0)
            return re.sub(r'(\w+)([\[\(\{])"(.*?)"([\]\)\}])', replacer, block)

        temp_block = clean_safe_labels(temp_block)
        
        if temp_block != block_content:
            modified_block = temp_block
            print(f"[{filepath}] Refined Mermaid syntax.")
            warnings += 1

        # 3. Special case: BF[BrokerFactory] -->"ET[Etoro] & IK[IBKR]"
        # This was a specific error found earlier.
        new_block = re.sub(r'-->"(.+?)"', r'--> \1', modified_block)
        if new_block != modified_block:
            print(f"[{filepath}] Fixed invalid edge-to-group quoting.")
            modified_block = new_block
            warnings += 1

        if fix and modified_block != block_content:
            # Replace the block in new_content
            # Use slice to replace to handle changing lengths
            start_in_new = block_start + offset
            end_in_new = block_end + offset
            new_content = new_content[:start_in_new] + modified_block + new_content[end_in_new:]
            offset += len(modified_block) - len(block_content)

    return warnings, new_content

def main():
    parser = argparse.ArgumentParser(description="Audit and fix Mermaid syntax in Markdown files.")
    parser.add_argument("path", nargs="?", default="wiki", help="Path to the directory to scan.")
    parser.add_argument("--fix", action="store_true", help="Apply fixes automatically.")
    args = parser.parse_args()

    if not os.path.exists(args.path):
        print(f"Error: Path '{args.path}' does not exist.")
        return

    total_warnings = 0
    files_modified = 0

    for root, _, files in os.walk(args.path):
        for file in files:
            if file.endswith(".md"):
                filepath = os.path.join(root, file)
                warnings, fixed_content = audit_mermaid_in_file(filepath, fix=args.fix)
                if warnings > 0:
                    total_warnings += warnings
                    if args.fix:
                        with open(filepath, 'w', encoding='utf-8') as f:
                            f.write(fixed_content)
                        files_modified += 1

    print(f"\nAudit complete.")
    print(f"Total potential issues found: {total_warnings}")
    if args.fix:
        print(f"Files modified: {files_modified}")

if __name__ == "__main__":
    main()
