"""
Multi-tenancy enforcement.

The design goal: a developer writing a new route or service function should
have to go OUT OF THEIR WAY to leak data across tenants, not remember to
prevent it. That rules out "add .filter(tenant_id=...) to every query" as the
primary mechanism -- it's exactly the kind of thing that gets forgotten once,
which is all it takes for an IDOR.

TenantScopedSession subclasses SQLAlchemy's Session and makes get(), query(),
add(), ORM execute(select(...)), and textual execute tenant-aware. Database
RLS remains the required defense in depth for Core SQL, connection-level SQL,
and privileged database roles.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy.orm import Session, with_loader_criteria
from sqlalchemy.sql import Select
from sqlalchemy.sql.elements import TextClause


class TenantScopedSession(Session):
    """A normal SQLAlchemy Session with tenant-aware ORM access."""

    _tenant_id: str | None = None

    def set_tenant(self, tenant_id: str | None) -> None:
        self._tenant_id = tenant_id

    def execute(self, statement, *args, **kwargs):
        """Prevent common Session.execute() paths from bypassing tenant scope.

        TextClause is rejected outright. ORM Select statements receive a
        global loader criterion for every TenantScoped mapped entity,
        including aliased entities and joined loads. System-scoped sessions
        (tenant_id=None) retain their existing behavior.

        This is application-layer defense, not a substitute for PostgreSQL
        RLS: Core table selects and lower-level connection APIs still require
        database-level controls.
        """
        if self._tenant_id is not None:
            if isinstance(statement, TextClause):
                raise PermissionError(
                    "Textual SQL is prohibited in tenant-scoped sessions; "
                    "use tenant-scoped ORM queries."
                )

            if isinstance(statement, Select):
                from app.models.entities import TenantScoped

                tenant_id = self._tenant_id
                statement = statement.options(
                    with_loader_criteria(
                        TenantScoped,
                        lambda cls: cls.tenant_id == tenant_id,
                        include_aliases=True,
                    )
                )

        return super().execute(statement, *args, **kwargs)

    @property
    def current_tenant_id(self) -> str | None:
        return self._tenant_id

    def get(self, entity, ident, **kw):  # type: ignore[override]
        from app.models.entities import TenantScoped

        obj = super().get(entity, ident, **kw)
        if obj is not None and self._tenant_id is not None and isinstance(obj, TenantScoped):
            if obj.tenant_id != self._tenant_id:
                return None
        return obj

    def query(self, *entities, **kwargs):  # type: ignore[override]
        from app.models.entities import TenantScoped

        q = super().query(*entities, **kwargs)
        if self._tenant_id is not None:
            for entity in entities:
                if isinstance(entity, type) and issubclass(entity, TenantScoped):
                    q = q.filter(entity.tenant_id == self._tenant_id)
        return q

    def add(self, instance, _warn: bool = True) -> None:  # type: ignore[override]
        from app.models.entities import TenantScoped

        if (
            isinstance(instance, TenantScoped)
            and getattr(instance, "tenant_id", None) is None
            and self._tenant_id is not None
        ):
            instance.tenant_id = self._tenant_id
        super().add(instance)


@contextmanager
def tenant_scope(db: TenantScopedSession, tenant_id: str | None) -> Iterator[TenantScopedSession]:
    """Temporarily set a session's tenant, restoring the previous value."""
    previous = db.current_tenant_id
    db.set_tenant(tenant_id)
    try:
        yield db
    finally:
        db.set_tenant(previous)
