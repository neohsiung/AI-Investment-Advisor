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
        
        # 1. Fix extra trailing quotes in lines
        # e.g., A-->>B: Text" -> A-->>B: Text
        new_block = re.sub(r'(: .*?)"($|\n)', r'\1\2', modified_block)
        if new_block != modified_block:
            print(f"[{filepath}] Fixed extra trailing quote in message line.")
            modified_block = new_block
            warnings += 1

        # 1. Ensure labels with parentheses ARE quoted
        # This matches nodes like ID[Label (with parens)] and adds quotes.
        # It avoids matching across lines or other nodes.
        def ensure_quotes_for_parens(m):
            node_id = m.group(1)
            bracket_open = m.group(2)
            label = m.group(3)
            bracket_close = m.group(4)
            if '"' in label: # Already has quotes?
                return m.group(0)
            return f'{node_id}{bracket_open}"{label}"{bracket_close}'

        new_block = re.sub(r'(\w+)([\[\(\{])([^"\[\]\n]*?[\(\)][^"\[\]\n]*?)([\]\)\}])', ensure_quotes_for_parens, modified_block)
        
        # 2. Clean up redundant quotes for TRULY safe labels (no parens)
        def fix_node_labels(m):
            node_id = m.group(1)
            bracket_open = m.group(2)
            label = m.group(3)
            bracket_close = m.group(4)
            
            # If label contains parentheses, it MUST be quoted
            if '(' in label or ')' in label:
                return f'{node_id}{bracket_open}"{label}"{bracket_close}'
            
            # If label only contains simple text (no parens, no special punctuation), remove quotes
            if re.match(r'^[\w\s\u4e00-\u9fa5\-\.,]+$', label):
                return f"{node_id}{bracket_open}{label}{bracket_close}"
            
            # Otherwise, keep as is
            return m.group(0)

        new_block = re.sub(r'(\w+)([\[\(\{])"(.*?)"([\]\)\}])', fix_node_labels, new_block)
        if new_block != modified_block:
            print(f"[{filepath}] Optimized node labels and quoting.")
            modified_block = new_block
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
