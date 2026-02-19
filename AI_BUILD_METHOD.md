# Improved Method to Build Applications with AI Assistance

Documents as contracts, short cycles, zero ambiguity, fast manual verification

This document describes a structured workflow to build software with an AI assistant while keeping decisions explicit, tasks verifiable, and scope controlled. It also defines how the AI should handle any inputs that require human action (for example API keys, external accounts, or permissions).

## Table of contents

1. Method principles  
2. Step -1: Constraints and hard decisions (before brainstorming)  
3. Step 0: Scope and boundaries (mini-brief)  
4. Step 1: Idea exploration (controlled creative loop)  
5. Step 2: SPEC v1 (programmable document)  
6. Step 3: Question loop to close ambiguity  
7. Step 4: Final SPEC (decisions + risks closed)  
8. Step 5: TASKS (verifiable implementation plan)  
9. Recommended template for each task  
10. Practical rules to split tasks well  
11. What the AI must return after each task  
12. Recommended prompts (copy/paste)  
13. Maintenance: changelog, versioning, final checklist  

---

## 1. Method principles

- Controlled iteration: short cycles. If something is unclear, decide before coding.
- Documents as contracts: `SPEC.md` defines the product; `TASKS.md` defines the work; code implements what was agreed.
- Verifiability: every task must be checkable with concrete, quick manual steps (5 to 10 minutes).
- Zero ambiguity: every relevant choice (DB, auth, storage, deployment) must be explicit in the final `SPEC.md`.
- Separation: AI used to build the product (this method) is not the same as AI features inside the product.
- Change discipline: if something changes, it is logged. No inventing requirements mid-build.

### Human inputs at the end (no stopping)

- If the AI needs any user-only input (API keys, credentials, external accounts, DNS, permissions), it must not stop the task.
- It must complete everything else and use safe placeholders where needed.
- At the end of the output, it must include a **User Inputs Needed** checklist with:
  - What is needed
  - Exact location to place it (env var / file / UI path)
  - How to obtain it
  - How to verify it works
- Never output real secrets. Use placeholders and environment variables.

### Secrets handling rules (recommended)

- Local development: use a `.env` file (gitignored) plus a `.env.example` template (committed).
- Production (staging/prod): configure environment variables in the hosting platform. For CI/CD, store values in GitHub Secrets.
- Do not print secrets in logs. Do not commit secrets into the repository.

---

## 2. Step -1: Constraints and hard decisions

Before exploring features, define constraints to prevent uncontrolled scope growth.

- MVP deadline: a realistic target date.
- Monthly budget: hosting, database, storage, AI APIs, tooling.
- Team: solo or with help. Hours per week available.
- Quality level: prototype, usable MVP, or production-grade from day one.
- Allowed stack: frontend, backend, DB, hosting, and why.
- Initial user target: 50, 200, 1,000 (this impacts architecture and cost).

**Output:** a short constraints list (6 to 8 lines) to paste at the top of `SPEC.md` as a **Constraints** section.

---

## 3. Step 0: Scope and boundaries (mini-brief)

Before asking for feature ideas, write a five-point mini-brief.

- Goal: what problem it solves and for whom.
- Users and roles: 2 to 5 roles max for the MVP.
- Primary use cases: 3 to 5 end-to-end flows.
- Out of scope: what will NOT be done in this version.
- Platform and environment: web/mobile/API and whether deployment is cloud or on-prem.

**Output:** a short text (about half a page) used as the **Context** section at the beginning of `SPEC.md`.

---

## 4. Step 1: Idea exploration (controlled creative loop)

An iterative loop to expand ideas without losing control.

- Describe your initial idea in 10 to 20 lines.
- Ask for: features, edge cases, typical metrics, and common risks in this domain.
- Classify ideas into: MVP (must-have), V1 (next), V2 (later).
- Repeat only while meaningful novelty appears. Stop when results start repeating.

**Output:** a prioritized list of features and flows. This becomes input for `SPEC.md`.

---

## 5. Step 2: SPEC v1 (programmable document)

`SPEC.md` must be concrete enough to minimize guessing.

- Vision and goals.
- Users, roles, and permissions.
- Primary user journeys (end-to-end).
- Functional requirements (FR-001, FR-002, ...).
- Non-functional requirements: performance, security, availability, privacy, cost.
- Data model: entities, relationships, rules, indexes.
- Interfaces/contracts: API endpoints, example payloads, error cases, states.
- Integrations: video/audio/storage, payments, email, notifications, etc. (if applicable).
- AI inside the product: use cases, required data, outputs, tolerance, fallback.
- Observability and audit: logs, traces, audit trail.
- Testing and verification: unit, integration, smoke, manual checks.
- Deployment: dev/staging/prod, env vars, migrations, backups.

**Output:** `SPEC.md` v1 (first complete version).

---

## 6. Step 3: Question loop to close ambiguity

Interrogate `SPEC.md` to close decisions. You answer, then `SPEC.md` is updated.

- Ask questions grouped by: product, UX, permissions, data model, integrations, performance, security, deployment, cost.
- Force explicit decisions: Postgres vs SQLite; JWT vs sessions; S3/R2 vs local; specific hosting target.
- The AI must return: the question list, the updated `SPEC.md`, and a Decision Log.
- Repeat until no remaining ambiguities can block implementation.

**Output:** refined `SPEC.md` (v2, v3, ...) plus Decision Log.

Extra rule: if a new decision appears during coding, pause, decide, and log it in `SPEC.md`.

---

## 7. Step 4: Final SPEC (decisions + risks closed)

Before creating `TASKS.md`, lock the MVP boundary. Clarity over perfection.

- Short architecture overview: components (frontend, backend, DB, storage, queues) and how they communicate.
- Risks and mitigations: scalability, latency, security, cost, data quality, operational complexity.
- Assumptions: anything you are assuming so the AI does not invent later.
- MVP lock: clear In scope vs Out of scope list.
- Change policy: no new features without updating `SPEC.md` and `TASKS.md`.

**Output:** Final `SPEC.md` used as the reference contract for implementation.

---

## 8. Step 5: TASKS (verifiable implementation plan)

Using the final `SPEC.md`, produce a `TASKS.md` that splits work into small, verifiable tasks.

- Phase 0: project foundation (repo, structure, config, CI, env setup).
- Phase 1: auth, roles, permissions.
- Phase 2: core data model + migrations.
- Phase 3: core CRUD.
- Phase 4: core workflows end-to-end.
- Phase 5: integrations (storage, payments, email, notifications, etc.).
- Phase 6: AI features inside the product.
- Phase 7: hardening (observability, security, performance, backups).

**Output:** `TASKS.md` versioned and aligned with the final `SPEC.md`.

Recommendation: add a simple dependency graph so task order cannot break.

---

## 9. Recommended template for each task

Reusable task template designed as a contract an AI can implement with minimal ambiguity.

### TASK N: Short delivery-oriented title

#### Context
- 2 to 4 lines: why this task exists and where it fits.

#### Objective
- What must be working at the end.

#### Scope
- Includes: X, Y  
- Excludes: Z  

#### Requirements
- Concrete list (ideally referencing FR-00X) plus key business rules.

#### Interfaces / Contracts
- Endpoints, events, schemas (request/response), error cases.
- DB changes: tables/fields/migrations.

#### Acceptance Criteria
- Yes/No checklist (include at least one negative case).

#### Definition of Done
- Tests pass, lint/format ok, minimal logs, minimal docs updated.

#### Risks and Notes
- Edge cases, security/performance considerations, cost notes.

#### Manual Verification Plan
- Exact human steps: commands, curls, UI checks.

#### AI Output Requirements
- Files touched, summary, exact commands, assumptions, suggested next task.

#### User Inputs Needed (Checklist)
- [ ] Item
  - What:
  - Where:
  - How to get it:
  - Verify:

---

## 10. Practical rules to split tasks well

- A task should be doable in one sitting and verifiable in 5 to 10 minutes.
- A task should not touch many unrelated files. If needed, split it or create a controlled refactor task.
- If a task mixes UI + API + DB and becomes large, split by layer or use a small vertical slice with strict boundaries.
- Prefer vertical slices only when the slice is small and fully verifiable end-to-end.
- Every task must include at least: 1 success case and 1 error case.

---

## 11. What the AI must return after each task

- Brief summary of what was implemented.
- List of files created/modified and why.
- Exact commands to run tests and apply migrations.
- Manual verification steps ready to copy/paste.
- Assumptions made (explicit) and possible follow-ups.
- Suggestion for the next task (if logical).
- If scope changed, a short changelog entry in `SPEC.md`.
- User Inputs Needed checklist (if any), with What/Where/How to get/Verify, and placeholders used in code.

---

## 12. Recommended prompts (copy/paste)

### Prompt A: Expand ideas
I have a concept for an app: [describe in 10 to 20 lines]. Give me additional feature ideas, typical edge cases, relevant metrics, and common risks. Then categorize the ideas into MVP / V1 / V2.

### Prompt B: Create SPEC v1
Using the following context and prioritized features, write a complete SPEC.md document for building this product. Include: roles/permissions, user journeys, functional requirements (FR-001...), non-functional requirements, data model, API contracts with example payloads and error cases, integrations, AI-in-product use cases, observability, testing, and deployment.

### Prompt C: Ask refinement questions and update SPEC
Here is the current SPEC.md. Ask me every question you need to remove ambiguity and lock decisions. Group questions by topic. After I answer, return an updated SPEC.md and a Decision Log.

### Prompt D: Create TASKS.md from final SPEC
Here is the FINAL SPEC.md. Create a TASKS.md document that splits implementation into small, verifiable programming tasks. Each task must follow this template: Context, Objective, Scope (includes/excludes), Requirements, Interfaces/Contracts, Acceptance Criteria, Definition of Done, Risks/Notes, Manual Verification Plan, AI Output Requirements, User Inputs Needed checklist.

### Prompt Add-on (append to any prompt)
If you need any user-only input (API keys, credentials, permissions, external configuration), do not stop. Use placeholders and finish the task. At the end, output a User Inputs Needed checklist with What / Where / How to get / Verify. Never output real secrets; use placeholders and environment variables.

---

## 13. Maintenance: changelog, versioning, final checklist

- Versioning `SPEC.md`: either `spec_v1.md`, `spec_v2.md`, or a single `SPEC.md` with a Changelog section.
- Version `TASKS.md` aligned with the `SPEC.md` version used to generate it.
- If code diverges from `SPEC.md`: either update `SPEC.md` or record an intentional deviation in the changelog.

### Pre-build checklist
- MVP boundary is clear (in scope vs out of scope).
- Roles and permissions are explicit.
- Core entities and rules are defined (no guessing).
- API contracts include examples and error cases.
- Deployment target is decided (where it runs).
- TASKS are small and each has a manual verification plan.

Optional suggestion: add `DECISIONS.md` and `RISKS.md` to keep the repo clean as it grows.
