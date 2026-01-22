# CLAUDE.md — tg-bot

> Inherits workflow from [../CLAUDE.md](../CLAUDE.md)

## Development Workflow (MANDATORY)

```
REQUIREMENTS → TESTS → IMPLEMENT → VERIFY → CHANGELOG
```

1. **Requirements First** — Update `docs/requirements/` before any code change
2. **TDD** — Write failing tests in `tests/` BEFORE implementation
3. **Implement** — Write minimal code to make tests pass
4. **Verify** — Run `pytest -x --tb=short`
5. **Changelog** — Update `CHANGELOG.md`

## First Steps

**Before making changes:** Read `docs/` and understand the CLI commands and client mixins.

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
