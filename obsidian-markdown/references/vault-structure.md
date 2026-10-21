# Vault Structure Conventions

User's Obsidian vault: `D:\Wind\大脑\`

## Directory Layout

```
D:\Wind\大脑\
├── Daily/           — Daily logs (YYYY-MM-DD.md)
├── Study/           — Learning notes
│   ├── AI/          — AI / Machine Learning
│   ├── Code/        — Programming / Frameworks
│   ├── Infrastructure/ — DevOps / Infrastructure
│   └── Business/    — Business / Product
├── Projects/        — Project documentation
├── Books/           — Book notes
├── Templates/       — Note templates
└── Index.md         — Navigation hub (MUST update after new notes)
```

## Naming Conventions

- **Files**: lowercase-with-hyphens.md (e.g., `rPPG-analysis.md`)
- **Tags**: nested format `#category/subcategory` (e.g., `#ai/computer-vision`)
- **Aliases**: English name for Chinese notes, or abbreviations

## Frontmatter Template

```yaml
---
title: "{{title}}"
date: {{YYYY-MM-DD}}
tags:
  - category
  - subcategory
aliases:
  - Alternative Name
source: "[[source-file]]"
---
```

## Index.md Update Rule

After creating ANY new note, immediately append its wikilink to Index.md under the appropriate section.

## Asset Storage

- PDFs, images → `assets/` subdirectory within the topic folder
- Example: `Study/AI/assets/filename.pdf`
- Reference in note: `![[assets/filename.pdf]]`
