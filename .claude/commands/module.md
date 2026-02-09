---
name: module
description: Scaffold a new backend module (router + service + schema + test)
---

# Module Command

Scaffold a new backend module with router, service, schema, and test boilerplate.

## Usage

```
/module <module-name>
```

## Example

```
/module architect
```

## What This Does

1. **Creates files** for a new module in the monolithic backend
2. **Generates boilerplate** (router, service, schemas)
3. **Sets up test** file
4. **Wires router** into main.py

## Generated Structure

```
backend/src/
├── api/
│   └── {module}.py          # FastAPI router
├── services/
│   └── {module}.py          # Business logic
├── schemas/
│   └── {module}.py          # Pydantic request/response models
└── ...

backend/tests/
├── test_{module}.py          # Unit tests
└── test_{module}_integration.py  # Integration tests (if needed)
```

## Generated Files

### api/{module}.py

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.database import get_db
from src.schemas.{module} import {Module}Response

router = APIRouter(prefix="/api/v1/{module}", tags=["{module}"])


@router.get("/{id}", response_model={Module}Response)
async def get_{module}(id: int, db: AsyncSession = Depends(get_db)) -> {Module}Response:
    ...
```

### services/{module}.py

```python
from sqlalchemy.ext.asyncio import AsyncSession


class {Module}Service:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, id: int) -> ...:
        ...
```

### schemas/{module}.py

```python
from pydantic import BaseModel


class {Module}Response(BaseModel):
    id: int
    ...

    model_config = {"from_attributes": True}
```

## Next Steps

After generation:

1. **Implement business logic** in services/{module}.py
2. **Define schemas** in schemas/{module}.py
3. **Wire up router** in main.py (`app.include_router`)
4. **Write tests** in tests/
5. **Run** `/test` to verify

## Reference

See `.claude/rules/architecture.md` for architectural guidelines.
