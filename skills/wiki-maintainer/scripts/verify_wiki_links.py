import os
import re

wiki_dir = "wiki"
# Regex to find markdown links: [label](path)
link_pattern = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')

def verify():
    # Get all valid page names (filenames without .md)
    valid_pages = set()
    for root, dirs, files in os.walk(wiki_dir):
        for file in files:
            if file.endswith(".md"):
                valid_pages.add(file[:-3])

    broken_links = []

    for root, dirs, files in os.walk(wiki_dir):
        for file in files:
            if file.endswith(".md"):
                filepath = os.path.join(root, file)
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                
                links = link_pattern.findall(content)
                for label, path in links:
                    # Skip external, anchor, or special files
                    if (path.startswith("http") or 
                        path.startswith("#") or 
                        path in ["Dockerfile", "Dockerfile.mcp", "docker-compose.yml"] or 
                        path.startswith("file://") or 
                        path.startswith("k8s/")):
                        continue
                    
                    # Check if the page exists in our flat namespace
                    if path not in valid_pages:
                        broken_links.append((filepath, path, label))

    if broken_links:
        print(f"Found {len(broken_links)} broken links:")
        for filepath, path, label in broken_links:
            print(f"{filepath}: Broken link [{label}]({path})")
    else:
        print("No broken internal links found.")

if __name__ == "__main__":
    verify()
