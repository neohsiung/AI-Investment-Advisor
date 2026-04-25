# Agent Governance Layer (.agent)

This directory serves as the **Operational Brain** of the AI Agent. It defines how the agent behaves, what specialized capabilities it possesses, and how it handles complex multi-step processes.

## 🏛️ Structure

### 1. Rules (`/rules`)
The **Guardrails** of the system.
- `engineering-standards.md`: Core coding and architectural requirements.
- `documentation-standards.md`: How we maintain the Wiki and project logs.
- `git-commit-format.md`: Strict rules for atomic commits.
- `reflection-standards.md`: Guidelines for self-healing and error classification.

### 2. Skills (`/skills`)
The **Specialized Capability Packages**. Each folder contains a `SKILL.md` (instructions) and optional scripts/resources.
- `feature-implementation-preflight`: Pre-coding checklist (Architecture/UI/UX).
- `wiki-maintainer`: Automated link verification and structure audits.
- `trunk-based-commit`: High-frequency, atomic version control logic.
- `postgres-raw-sql`: Standards for database interactions.
- `audit-plugin`: Security auditing for 3rd-party tools and plugins.

### 3. Workflows (`/workflows`)
The **Operational Playbooks**. Standardized processes for common large-scale tasks.
- `plan-governance.md`: Rules for maintaining plan integrity within a session.
- `b2c-tech-stack-transition.md`: Guide for migrating components to the v9.0 SaaS stack.

## 📝 Maintenance
- All `SKILL.md` files must follow the YAML frontmatter standard (`name`, `description`).
- References to Wiki components must follow the **8-Pillar Taxonomy**.
- Hardcoded sensitive values (keys, model strings) are strictly prohibited in instructions.
