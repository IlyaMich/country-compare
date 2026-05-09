"""Pydantic schemas for the Country Compare API boundary.

Keep this package initializer intentionally light. Importing submodules from here
can create circular imports during FastAPI app startup because modules such as
``api.errors`` import ``api.schemas.common`` before route schemas are needed.
"""

__all__: list[str] = []
