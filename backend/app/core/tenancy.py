"""
Multi-tenancy enforcement.

The ORM layer applies tenant criteria to every mapped entity that exposes a
tenant_id column, including the risk models. PostgreSQL RLS is the independent
database boundary for Core SQL and any query path the ORM guard does not cover.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import event, inspect as sa_inspect, text
from sqlalchemy.orm import Session, with_loader_criteria
from sqlalchemy.sql import Select
from sqlalchemy.sql.elements import TextClause


def _mapper_for(entity):
    try:
        inspected = sa_inspect(entity, raiseerr=False)
        return getattr(inspected, "mapper", inspected)
    except Exception:
        return None


def _has_tenant_column(entity) -> bool:
    mapper = _mapper_for(entity)
    return mapper is not None and hasattr(mapper, "columns") and "tenant_id" in mapper.columns


class TenantScopedSession(Session):
    """A SQLAlchemy Session with tenant-aware ORM and PostgreSQL context."""

    _tenant_id: str | None = None

    def _sync_rls_context(self) -> None:
        # SQLite remains the fast unit-test backend. PostgreSQL receives
        # transaction-local settings, never connection/session-persistent ones.
        if not self.in_transaction():
            return
        connection = self.connection()
        if connection.dialect.name != "postgresql":
            return
        connection.execute(
            text(
                "SELECT "
                "set_config('app.tenant_id', :tenant_id, true), "
                "set_config('app.oidc_subject', :oidc_subject, true), "
                "set_config('app.demo_token', :demo_token, true)"
            ),
            {
                "tenant_id": self.info.get("rls_tenant_id") or "",
                "oidc_subject": self.info.get("rls_oidc_subject") or "",
                "demo_token": self.info.get("rls_demo_token") or "",
            },
        )

    def set_tenant(self, tenant_id: str | None) -> None:
        self._tenant_id = tenant_id
        self.info["rls_tenant_id"] = tenant_id
        self._sync_rls_context()

    def set_oidc_subject(self, subject: str | None) -> None:
        self.info["rls_oidc_subject"] = subject
        self._sync_rls_context()

    def set_demo_token(self, token: str | None) -> None:
        self.info["rls_demo_token"] = token
        self._sync_rls_context()

    @property
    def current_tenant_id(self) -> str | None:
        return self._tenant_id

    def execute(self, statement, *args, **kwargs):
        """Reject textual SQL in tenant scope and filter ORM SELECT entities."""
        if self._tenant_id is not None:
            if isinstance(statement, TextClause):
                raise PermissionError(
                    "Textual SQL is prohibited in tenant-scoped sessions; "
                    "use tenant-scoped ORM queries."
                )

            if isinstance(statement, Select):
                tenant_id = self._tenant_id
                seen = set()
                for description in getattr(statement, "column_descriptions", ()):
                    entity = description.get("entity")
                    if entity is not None and _has_tenant_column(entity):
                        key = id(_mapper_for(entity))
                        if key in seen:
                            continue
                        seen.add(key)
                        statement = statement.options(
                            with_loader_criteria(
                                entity,
                                lambda cls: cls.tenant_id == tenant_id,
                                include_aliases=True,
                            )
                        )

        return super().execute(statement, *args, **kwargs)

    def get(self, entity, ident, **kw):  # type: ignore[override]
        obj = super().get(entity, ident, **kw)
        if (
            obj is not None
            and self._tenant_id is not None
            and _has_tenant_column(type(obj))
            and str(obj.tenant_id) != str(self._tenant_id)
        ):
            return None
        return obj

    def query(self, *entities, **kwargs):  # type: ignore[override]
        query = super().query(*entities, **kwargs)
        if self._tenant_id is not None:
            for entity in entities:
                if _has_tenant_column(entity):
                    query = query.filter(entity.tenant_id == self._tenant_id)
        return query

    def add(self, instance, _warn: bool = True) -> None:  # type: ignore[override]
        if (
            self._tenant_id is not None
            and _has_tenant_column(type(instance))
            and getattr(instance, "tenant_id", None) is None
        ):
            instance.tenant_id = self._tenant_id
        super().add(instance)


@event.listens_for(TenantScopedSession, "after_begin")
def _apply_transaction_local_rls_context(session, transaction, connection) -> None:
    """Reapply context on every transaction, including pooled connection reuse."""
    if connection.dialect.name == "postgresql":
        connection.execute(
            text(
                "SELECT "
                "set_config('app.tenant_id', :tenant_id, true), "
                "set_config('app.oidc_subject', :oidc_subject, true), "
                "set_config('app.demo_token', :demo_token, true)"
            ),
            {
                "tenant_id": session.info.get("rls_tenant_id") or "",
                "oidc_subject": session.info.get("rls_oidc_subject") or "",
                "demo_token": session.info.get("rls_demo_token") or "",
            },
        )


@contextmanager
def tenant_scope(db: TenantScopedSession, tenant_id: str | None) -> Iterator[TenantScopedSession]:
    """Temporarily set a session's tenant, restoring the previous value."""
    previous = db.current_tenant_id
    db.set_tenant(tenant_id)
    try:
        yield db
    finally:
        db.set_tenant(previous)
