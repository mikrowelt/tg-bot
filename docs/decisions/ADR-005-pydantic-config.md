# ADR-005: Pydantic for Configuration

## Status
Accepted

## Context

Original configuration used Python dataclasses:

```python
@dataclass
class Config:
    app_id: int
    app_hash: str
    # ...
```

Issues encountered:
- **No validation** — Invalid values only caught at runtime
- **Type coercion** — String "123" not auto-converted to int
- **Error messages** — Generic Python errors, not user-friendly
- **Documentation** — No schema generation

## Decision

Migrate to **Pydantic BaseModel**:

```python
from pydantic import BaseModel, Field, field_validator

class Config(BaseModel):
    app_id: int = Field(gt=0, description="Telegram app ID")
    app_hash: str = Field(min_length=1, description="Telegram app hash")
    phone: str = Field(min_length=1)

    @field_validator('phone', mode='before')
    @classmethod
    def convert_phone_to_string(cls, v):
        return str(v) if v is not None else v

    model_config = {"frozen": False, "arbitrary_types_allowed": True}
```

### Validation Added

| Field | Validation |
|-------|------------|
| `app_id` | Must be > 0 |
| `app_hash` | Must not be empty |
| `port` | Must be 1-65535 |
| Proxy auth | Both username AND password required, or neither |

### Type Coercion

```python
# Profile JSON has phone as number
{"phone": 1234567890}

# Pydantic auto-converts to string
config.phone  # "1234567890"
```

## Consequences

### Benefits
- **Validation at load time** — Catch errors early
- **Better error messages** — Pydantic explains what's wrong
- **Type safety** — Automatic type conversion
- **Documentation** — JSON schema generation possible
- **IDE support** — Better autocomplete

### Drawbacks
- **Dependency** — Adds pydantic to requirements
- **Learning curve** — Different from dataclasses
- **Config naming** — Inner `Config` class deprecated in v2

### Mitigation
- Pydantic is well-maintained, widely used
- `model_config` dict replaces inner `Config` class
- Minimal API surface used (BaseModel, Field, validators)
