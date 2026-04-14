# Project Bootstrap Skill

Use when starting work in any project — whether a new session in an existing repo or first time touching a codebase.

## When This Activates
Beginning of a work session, switching projects, or when context about the project is unclear.

## Bootstrap Sequence

### 1. Read the Project CLAUDE.md
- Every project has context, gotchas, and patterns. Read it before writing code.
- If no CLAUDE.md exists, scan the repo structure and create one.

### 2. Check OpenViking for Context
- Search OV for the project name or related APIs.
- Check `resources/agents/coding-practices` for universal principles.
- Check `resources/life-os/external-apis/` if the project integrates with external services.

### 3. Identify the Right Agent
- Suggest `/backend`, `/frontend`, `/database`, `/platform`, or `/fullstack` based on the task.
- If the task spans layers, default to `/fullstack`.

### 4. Understand Branch State
- Check `git status` and `git branch` — what branch are you on? Is it clean?
- For established projects: work should happen on feature branches, not main.
- Create a feature branch if starting new work: `git checkout -b feature/description`.

### 5. Understand the Dev Environment
- Check for `package.json` scripts, `Makefile`, `docker-compose.yml`.
- Identify how to run, build, and test before making changes.
- Start the dev server if it's a frontend project — verify it works before touching code.

## For New Projects
- Initialize with `git init`, create `.gitignore`, set up basic structure.
- Create a CLAUDE.md with: what this is, tech stack, commands, key patterns.
- Set up the feature branch workflow from day one.

## Principle
Understand before you build. 5 minutes of orientation saves hours of wrong assumptions.
