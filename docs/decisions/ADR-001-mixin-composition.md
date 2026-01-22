# ADR-001: Mixin Composition for Client

## Status
Accepted

## Context

The original `client.py` file was over 1,300 lines containing all Telegram operations: profile management, channel operations, message sending, and information retrieval. This made the file:

- Difficult to navigate and understand
- Hard to test individual concerns
- Prone to merge conflicts in collaborative development
- Slow to load when only needing a subset of functionality

## Decision

Split the TgBot client into focused **mixins**, each handling a single concern:

```python
class TgBot(ProfileMixin, ChannelsMixin, MessagesMixin, InfoMixin):
    """Main client class inheriting from all operation mixins."""
    pass
```

**Mixin breakdown:**
- `ProfileMixin` (client_profile.py) — Profile CRUD operations
- `ChannelsMixin` (client_channels.py) — Join/leave channels
- `MessagesMixin` (client_messages.py) — Send messages/comments
- `InfoMixin` (client_info.py) — Retrieve information

Each mixin assumes access to `self.client` (TelegramClient) and `self.config`.

## Consequences

### Benefits
- **Single responsibility** — Each file handles one concern
- **Easier testing** — Can mock individual mixins
- **Better navigation** — Find relevant code faster
- **Reduced conflicts** — Changes to profile don't touch message code
- **Smaller files** — 280-650 lines instead of 1,300

### Drawbacks
- **Implicit dependencies** — Mixins assume certain attributes exist
- **Method discovery** — Must check multiple files for available methods
- **Circular imports** — Need careful import ordering

### Mitigation
- Document which attributes mixins require
- TgBot class docstring lists all inherited methods
- Use TYPE_CHECKING for type hints to avoid circular imports
