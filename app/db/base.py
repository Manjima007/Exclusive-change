"""
Database Model Imports.

This module imports all SQLAlchemy models to ensure they are registered
with the Base metadata. This is required for Alembic autogenerate to
detect all models.

IMPORTANT: Import this module before creating tables or running migrations.

Usage:
    from app.db.base import Base
    # All models are now registered with Base.metadata
"""

# Import Base first
from app.models.base import Base

# Import all models to register them with Base.metadata
# The order matters - models with foreign keys should come after their dependencies
from app.models.tenant import Tenant, Environment, APIKey  # noqa: F401
from app.models.flag import Flag, FlagAuditLog  # noqa: F401

# Re-export Base for convenience
__all__ = [
    "Base",
    "Tenant",
    "Environment", 
    "APIKey",
    "Flag",
    "FlagAuditLog",
]
