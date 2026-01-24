# CLAUDE.md — tg-bot

> Inherits workflow from [../CLAUDE.md](../CLAUDE.md)

---

## For Agents: Read This First

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  YOU ARE AN AGENT WORKING ON tg-bot                                         │
│                                                                             │
│  MANDATORY WORKFLOW:                                                        │
│  1. Read this CLAUDE.md completely                                          │
│  2. Read docs/requirements/ for existing specs                              │
│  3. UPDATE docs/requirements/ with YOUR implementation specs                │
│  4. Write tests FIRST in tests/ (TDD)                                       │
│  5. Implement minimal code to pass tests                                    │
│  6. Run: pytest -x --tb=short                                               │
│  7. UPDATE docs/ with classes/functions/commands you created                │
│  8. UPDATE CHANGELOG.md                                                     │
│                                                                             │
│  LOCAL DOCS LOCATIONS:                                                      │
│  - Requirements: docs/requirements/*.md                                     │
│  - Architecture: docs/architecture/*.md                                     │
│  - Decisions: docs/decisions/*.md                                           │
│  - Changelog: CHANGELOG.md                                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Development Workflow (MANDATORY)

```
REQUIREMENTS → TESTS → IMPLEMENT → VERIFY → E2E → CHANGELOG → DOCS
```

1. **Requirements First** — Update `docs/requirements/` before any code change
2. **TDD** — Write failing tests in `tests/` BEFORE implementation
3. **Implement** — Write minimal code to make tests pass
4. **Verify** — Run `pytest -x --tb=short`
5. **E2E on Dev** — Deploy to dev, verify feature works. **Task NOT done until E2E passes**
6. **Changelog** — Update `CHANGELOG.md`
7. **Update Docs** — Add class/function/property names to docs for ast-grep

## First Steps: Read Docs → ast-grep → Code

1. **Read `docs/`** — Understand CLI commands, client mixins, find class/function names
2. **Use ast-grep** — Search for those names in code (see patterns below)
3. **Analyze code** — Read with context from documentation

**Never search code blindly — read docs first to know what to search for.**

## ast-grep Patterns

```python
# CLI commands
"@cli.command($$$)"
"@click.command($$$)"

# Client methods
"async def join_channel($$$)"

# Verification handlers
"class MathSolver"
"async def solve($$$)"

# Telethon events
"@client.on($$$)"
```

## Testing

```bash
pytest -x --tb=short             # Smoke test
pytest -v                        # Verbose
pytest --cov=tgbot               # With coverage
```

| What | How | Location |
|------|-----|----------|
| CLI commands | Click CliRunner | `tests/` |
| Client methods | Mock Telethon client | `tests/` |
| Verification handlers | Unit tests with sample data | `tests/` |
| Utils | Pure unit tests | `tests/` |

Mock Telethon API calls — never hit real Telegram in tests.

## Changelog

**REQUIRED:** Update `CHANGELOG.md` with every change — features, fixes, refactors.

## Notes

- CLI entry: `tgbot/cli.py`
- Client mixins: `client_*.py`
- Verification: `tgbot/verification/`
- Sessions stored in `profiles/`
