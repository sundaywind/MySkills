---
name: self-improvement
description: "Fused self-improvement and central tiered memory skill. Activates when: (1) Mistakes occur, user corrects behavior, or a command fails; (2) User asks for memory statistics, patterns, or files; (3) You complete significant work and perform self-reflection. Manages local project logs and a global tiered memory cache (HOT/WARM/COLD) for cross-session reuse."
---

# Unified Self-Improvement & Central Tiered Memory Skill

This skill combines project-local logging with a global, cross-project centralized memory cache to enable persistent agent self-evolution.

---

## 1. Directory Structure

### Project-Local Storage (Capture Inbox)
Created in the root of any active project:
```text
.learnings/
├── LEARNINGS.md          # Insights, corrections, and knowledge gaps
├── ERRORS.md             # Detailed log of command and API failures
└── FEATURE_REQUESTS.md   # Missing capabilities requested by user
```

### Global Centralized Storage (Durable Memory Tiers)
Stored in the global configuration path: `C:\Users\Wind\.gemini\config\self-improving/`
```text
C:\Users\Wind\.gemini\config\self-improving/
├── memory.md             # HOT memory: always loaded, <=100 lines (confirmed rules)
├── corrections.md        # HOT log: last 50 user corrections
├── projects/             # WARM memory: project-specific files (e.g., projects/my-app.md)
├── domains/              # WARM memory: domain-specific files (e.g., domains/java-spring.md)
└── archive/              # COLD memory: decayed/inactive patterns
```

---

## 2. Dynamic Memory Loading Policy

When this skill is active, you **MUST** read and respect the memory files dynamically:
1. **Always Read HOT Memory**: Load `C:\Users\Wind\.gemini\config\self-improving\memory.md` and `corrections.md` at the start of any session.
2. **Read Scoped WARM Memory**:
   - If in a project (e.g., `government-canteen`), search for `projects/government-canteen.md` and load it.
   - If using a domain technology (e.g., Vue, Spring Boot, Linux Nginx), search for matching files in `domains/` and load them.
3. **Graceful Context Management**: If context window limit is approached, unload COLD/WARM files first. Never fail silently.

---

## 3. Ingestion & Promotion Workflow

```text
Local Capture (.learnings/) -> 3x Repeated / Explicit Fix -> Global Central Memory (self-improving/)
```

### Ingestion Signals:
- **Corrections**: Log to local `LEARNINGS.md` (category: `correction`) and global `corrections.md` when the user says: *"No, that's wrong..."*, *"Actually, it should be..."*, *"I prefer X, not Y"*.
- **Errors**: Log to local `ERRORS.md` when commands return non-zero exit codes, tool calls fail, or exceptions trigger.
- **Self-Reflections**: After significant tasks, evaluate and log insights (format: `CONTEXT: ... | REFLECTION: ... | LESSON: ...`).

### Promotion/Demotion Rules:
- **Promote to WARM/HOT**:
  - Run the python helper script to promote a local log:
    `python C:\Users\Wind\.gemini\config\skills\self-improvement\scripts\extract_skill.py <LRN-ID> [--global-hot] [--domain <name>] [--project <name>]`
  - A pattern seen 3 times in 7 days should be promoted to HOT (`memory.md`).
- **Demote to WARM**: Unused in HOT for 30 days $\rightarrow$ move to `domains/` or `projects/`.
- **Archive to COLD**: Unused in WARM for 90 days $\rightarrow$ move to `archive/`.

---

## 4. Central Memory Quick Queries

When the user queries memory, respond in the following format:

- **"Show my patterns" / "What are my rules?"**
  - Read and display `C:\Users\Wind\.gemini\config\self-improving\memory.md`.
- **"Memory stats"**
  - Report the number of entries in HOT, WARM, and COLD tiers, plus a summary of the last 5 logs from `corrections.md`.
- **"Forget X"**
  - Search all tiers for X and delete it after user confirmation.

---

## 5. Security & Boundary Rules
- **NEVER** store plain-text credentials, API keys, private tokens, or personal identifying information in memory.
- Prefer general method guidelines or redacted logs.
- Never write or modify files in `C:\Users\Wind\.gemini\config\self-improving\` without explicit user intent.
