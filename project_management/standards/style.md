# Style Guide: Productivity Guard

## Universal Rules

These apply to all projects by default. To disable one, move it to the "Disabled Universal Rules" section at the bottom of this file with a written rationale.

### Code Quality

- **DRY** — If logic appears in more than one place, extract it. If the agent believes duplication is the better path (performance, clarity, decoupling), it must state the tradeoff explicitly and get confirmation before proceeding.
- **No dead code** — Unreachable code, unused imports, and commented-out blocks are removed. Version control is the archive.
- **Fail loudly** — Errors propagate or are handled meaningfully. No empty catch blocks, no silent swallowing, no returning default values that mask failures.
- **Naming carries intent** — Names describe *what* something is or *what* it does, not *how*. No abbreviations that aren't universally understood in the domain.
- **Functions do one thing** — A function that needs "and" in its description is two functions.
- **Minimize scope** — Variables are declared as close to their use as possible, with the narrowest visibility that works.
- **Magic values get named constants** — Literal values that aren't self-evident get a named constant with an explanatory name.

### Process

- **Every commit is buildable** — No partial commits that break the build.
- **Tests pass before commit** — If tests exist, they pass. No "fix the tests later."
- **No dead code in main branch** — Before declaring work complete, confirm nothing unused was left behind.

---

## Language & Tooling

### Backend (Python)
- Language: Python 3.11
- Test command: `cd backend && source .venv/bin/activate && pytest tests/ -v`
- Source directory: `backend/`
- No formal linter/formatter configured — follow PEP 8 conventions

### Extension (JavaScript)
- Language: JavaScript (ES2020, no transpilation)
- Source directory: `extension/`
- Build output: `extension/web-ext-artifacts/` (via `web-ext build`)

## Naming Conventions

### Backend (Python)
- Classes: PascalCase
- Functions and variables: snake_case
- Constants: UPPER_SNAKE_CASE
- Modules: snake_case

### Extension (JavaScript)
- Functions and variables: camelCase
- Constants: UPPER_SNAKE_CASE

## Formatting

### Backend (Python)
- Indentation: 4 spaces
- String quotes: double quotes preferred

### Extension (JavaScript)
- Indentation: 2 spaces
- String quotes: double quotes preferred

## Type Safety

### Backend (Python)
- All function parameters and return types are annotated where practical
- `Optional[T]` used for nullable parameters; `list[T]` for lists
- Pydantic models validate all API boundaries (input and output)
- No mypy enforcement currently

### Extension (JavaScript)
- No TypeScript; vanilla JS only

## Error Handling

### Backend (Python)
- Errors propagate to the top level; no silent swallowing
- Claude API errors default to DENY (fail safe for access decisions)
- HA API errors are logged as warnings; execution continues without room context
- dnsmasq write/signal errors are logged; the API response still reflects the decision
- Validate at system boundaries only — Pydantic models handle incoming API request validation

### Extension (JavaScript)
- Network errors are caught and displayed in the blocked.html UI
- Extension fails closed: if the backend is unreachable, the block stands

## Serialization

- API requests/responses: handled automatically by Pydantic (JSON)
- Claude API responses: expected JSON; parsed in `LLMGatekeeper._parse_response`; parse failure defaults to DENY
- Config: YAML (`config.yaml`), loaded once at startup via `yaml.safe_load`
- Database: raw SQL via aiosqlite; no ORM

## Build & Lint Gate

- After any backend change, run `cd backend && source .venv/bin/activate && pytest tests/ -v`. All tests must pass.
- No formal lint step; follow PEP 8 and existing code conventions.
- When tests flag an issue, fix the underlying problem — do not suppress.
