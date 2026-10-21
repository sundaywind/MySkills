import os
import sys
import re
from datetime import datetime

def print_error(msg):
    print(f"\033[31mError: {msg}\033[0m")

def print_success(msg):
    print(f"\033[32mSuccess: {msg}\033[0m")

def print_info(msg):
    print(f"\033[34mInfo: {msg}\033[0m")

def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_skill.py <LRN-ID> [options]")
        print("Options:")
        print("  --global-hot          Promote directly to global HOT memory (memory.md)")
        print("  --domain <name>       Promote to a global WARM domain memory (e.g., domains/java-spring.md)")
        print("  --project <name>      Promote to a global WARM project memory (e.g., projects/my-app.md)")
        print("  --name <skill-name>   Create an independent Antigravity skill folder (default local, use with --global for global)")
        print("  --global              Use with --name to save independent skill to global skills folder")
        print("\nExample: python extract_skill.py LRN-20260630-001 --global-hot")
        sys.exit(1)

    lrn_id = sys.argv[1].upper()
    is_global_hot = "--global-hot" in sys.argv
    is_global_skill = "--global" in sys.argv
    
    # Parse domain
    domain_name = None
    if "--domain" in sys.argv:
        try:
            idx = sys.argv.index("--domain") + 1
            if idx < len(sys.argv):
                domain_name = sys.argv[idx].strip().lower().replace(" ", "-")
        except ValueError:
            pass

    # Parse project
    project_name = None
    if "--project" in sys.argv:
        try:
            idx = sys.argv.index("--project") + 1
            if idx < len(sys.argv):
                project_name = sys.argv[idx].strip().lower().replace(" ", "-")
        except ValueError:
            pass

    # Parse explicit skill name
    skill_name = None
    if "--name" in sys.argv:
        try:
            idx = sys.argv.index("--name") + 1
            if idx < len(sys.argv):
                skill_name = idx < len(sys.argv) and sys.argv[idx].strip().lower().replace(" ", "-")
        except ValueError:
            pass

    # Locate LEARNINGS.md
    learnings_path = os.path.join(".learnings", "LEARNINGS.md")
    if not os.path.exists(learnings_path):
        # Try finding in parent directory
        learnings_path = os.path.join("..", ".learnings", "LEARNINGS.md")
        if not os.path.exists(learnings_path):
            print_error("Could not locate `.learnings/LEARNINGS.md` in the current directory or parent directory.")
            sys.exit(1)

    print_info(f"Reading learnings from: {os.path.abspath(learnings_path)}")
    
    with open(learnings_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Split entries by "---" separator
    entries = content.split("---")
    target_entry = None
    target_index = -1
    
    for idx, entry in enumerate(entries):
        if lrn_id in entry:
            target_entry = entry.strip()
            target_index = idx
            break

    if not target_entry:
        print_error(f"Could not find entry matching ID: {lrn_id}")
        sys.exit(1)

    print_success(f"Found learning entry: {lrn_id}")

    # Parse category
    header_match = re.search(r"##\s*\[" + re.escape(lrn_id) + r"\]\s*(.*)", target_entry)
    category = header_match.group(1).strip() if header_match else "unknown"

    # Parse Summary
    summary_match = re.search(r"###\s*Summary\s*\n+(.*?)(?=\n+###|$)", target_entry, re.DOTALL)
    summary = summary_match.group(1).strip() if summary_match else "No summary provided"

    # Parse Details
    details_match = re.search(r"###\s*Details\s*\n+(.*?)(?=\n+###|$)", target_entry, re.DOTALL)
    details = details_match.group(1).strip() if details_match else ""

    # Parse Suggested Action
    action_match = re.search(r"###\s*Suggested\s*Action\s*\n+(.*?)(?=\n+###|$)", target_entry, re.DOTALL)
    suggested_action = action_match.group(1).strip() if action_match else ""

    global_config_dir = os.path.expanduser(r"~\.gemini\config")
    central_memory_dir = os.path.join(global_config_dir, "self-improving")
    os.makedirs(central_memory_dir, exist_ok=True)

    promotion_target_path = None
    notes = ""

    # 1. Option: Global HOT memory.md
    if is_global_hot:
        hot_memory_path = os.path.join(central_memory_dir, "memory.md")
        if not os.path.exists(hot_memory_path):
            with open(hot_memory_path, "w", encoding="utf-8") as hf:
                hf.write("# Self-Improving HOT Memory (HOT Tier)\n\nAlways loaded. Size limit: <= 100 lines.\n\n## Rules & Invariants\n")
        
        # Read and check if rules list is there
        with open(hot_memory_path, "r", encoding="utf-8") as hf:
            hot_content = hf.read()

        if lrn_id in hot_content:
            print_error(f"Entry {lrn_id} already promoted in global HOT memory.")
            sys.exit(0)

        # Append new rule
        new_rule = f"\n- **{summary}** (from {lrn_id}): {suggested_action}"
        
        # Let's find Rules & Invariants header
        header_pos = hot_content.find("## Rules & Invariants")
        if header_pos != -1:
            # Insert right after header or at the end
            updated_hot = hot_content[:header_pos + len("## Rules & Invariants")] + new_rule + hot_content[header_pos + len("## Rules & Invariants"):]
        else:
            updated_hot = hot_content + "\n## Rules & Invariants" + new_rule

        with open(hot_memory_path, "w", encoding="utf-8") as hf:
            hf.write(updated_hot)

        promotion_target_path = hot_memory_path
        notes = "Promoted to global HOT memory.md"
        print_success(f"Successfully promoted to global HOT memory: {hot_memory_path}")

    # 2. Option: Global WARM domain file
    elif domain_name:
        domain_dir = os.path.join(central_memory_dir, "domains")
        os.makedirs(domain_dir, exist_ok=True)
        domain_file_path = os.path.join(domain_dir, f"{domain_name}.md")
        
        if not os.path.exists(domain_file_path):
            with open(domain_file_path, "w", encoding="utf-8") as df:
                df.write(f"# Scoped WARM Memory: Domain {domain_name.title()}\n\n## Learnings List\n")
        
        with open(domain_file_path, "r", encoding="utf-8") as df:
            domain_content = df.read()

        if lrn_id in domain_content:
            print_error(f"Entry {lrn_id} already promoted in domain {domain_name}.")
            sys.exit(0)

        new_entry = f"\n- **[{lrn_id}] {summary}**: {suggested_action}\n  - *Context*: {details}\n"
        updated_domain = domain_content + new_entry

        with open(domain_file_path, "w", encoding="utf-8") as df:
            df.write(updated_domain)

        promotion_target_path = domain_file_path
        notes = f"Promoted to global WARM domain memory {domain_name}"
        print_success(f"Successfully promoted to domain WARM memory: {domain_file_path}")

    # 3. Option: Global WARM project file
    elif project_name:
        project_dir = os.path.join(central_memory_dir, "projects")
        os.makedirs(project_dir, exist_ok=True)
        project_file_path = os.path.join(project_dir, f"{project_name}.md")
        
        if not os.path.exists(project_file_path):
            with open(project_file_path, "w", encoding="utf-8") as pf:
                pf.write(f"# Scoped WARM Memory: Project {project_name.title()}\n\n## Learnings List\n")
        
        with open(project_file_path, "r", encoding="utf-8") as pf:
            project_content = pf.read()

        if lrn_id in project_content:
            print_error(f"Entry {lrn_id} already promoted in project {project_name}.")
            sys.exit(0)

        new_entry = f"\n- **[{lrn_id}] {summary}**: {suggested_action}\n  - *Context*: {details}\n"
        updated_project = project_content + new_entry

        with open(project_file_path, "w", encoding="utf-8") as pf:
            pf.write(updated_project)

        promotion_target_path = project_file_path
        notes = f"Promoted to global WARM project memory {project_name}"
        print_success(f"Successfully promoted to project WARM memory: {project_file_path}")

    # 4. Default: Create independent Antigravity skill folder
    else:
        # Prompt user or generate name from summary if not explicitly provided
        if not skill_name:
            words = re.findall(r'\b\w+\b', summary.lower())
            stop_words = {'a', 'an', 'the', 'and', 'but', 'or', 'as', 'if', 'of', 'at', 'by', 'for', 'with', 'about', 'to', 'in', 'on', 'this', 'that', 'is', 'was', 'how'}
            keywords = [w for w in words if w not in stop_words and w.isalnum()]
            skill_name = "-".join(keywords[:4]) if keywords else f"skill-{lrn_id.lower()}"

        if is_global_skill:
            base_dir = os.path.join(global_config_dir, "skills")
        else:
            base_dir = os.path.join(".agents", "skills")
            if not os.path.exists(".agents"):
                if os.path.exists(os.path.join("..", ".agents")):
                    base_dir = os.path.join("..", ".agents", "skills")

        skill_dir = os.path.join(base_dir, skill_name)
        skill_file_path = os.path.join(skill_dir, "SKILL.md")

        if os.path.exists(skill_file_path):
            print_error(f"Skill file already exists at: {skill_file_path}")
            sys.exit(1)

        skill_content = f"""---
name: {skill_name}
description: {summary}
---

# {skill_name.replace('-', ' ').title()}

## Summary
{summary}

## Context & Details
{details}

## Reusable Procedure / Rules
{suggested_action}
"""

        os.makedirs(skill_dir, exist_ok=True)
        with open(skill_file_path, "w", encoding="utf-8") as sf:
            sf.write(skill_content)

        promotion_target_path = skill_file_path
        notes = f"Promoted to custom skill {skill_name} at {skill_file_path}"
        print_success(f"Successfully created skill at: {os.path.abspath(skill_file_path)}")

    # Update status and links in local LEARNINGS.md
    print_info("Updating entry status in LEARNINGS.md...")
    
    modified_entry = target_entry
    modified_entry = re.sub(r"\*\*Status\*\*:\s*pending", "**Status**: promoted", modified_entry)
    
    # Format relative link for Markdown update
    if promotion_target_path:
        formatted_link = f"[{os.path.basename(promotion_target_path)}](file:///{os.path.abspath(promotion_target_path).replace(os.sep, '/')})"
        metadata_match = re.search(r"###\s*Metadata\s*\n+(.*?)(?=\n+###|\Z)", modified_entry, re.DOTALL)
        if metadata_match:
            old_metadata = metadata_match.group(0)
            new_metadata = old_metadata.rstrip() + f"\n- Skill-Path: {formatted_link}\n"
            modified_entry = modified_entry.replace(old_metadata, new_metadata)

    # Append Resolution block
    resolution_date = datetime.now().strftime("%Y-%m-%d")
    resolution_block = f"""
### Resolution
- **Resolved**: {resolution_date}
- **Notes**: {notes}
"""
    modified_entry = modified_entry.strip() + "\n" + resolution_block

    entries[target_index] = "\n" + modified_entry.strip() + "\n"
    new_content = "---".join(entries)

    with open(learnings_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    print_success("LEARNINGS.md updated successfully.")

if __name__ == "__main__":
    main()
