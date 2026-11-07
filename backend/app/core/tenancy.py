"""
Multi-tenancy enforcement.

The design goal: a developer writing a new route or service function should
have to go OUT OF THEIR WAY to leak data across tenants, not remember to
prevent it. That rules out "add .filter(tenant_id=...) to every query" as the
primary mechanism -- it's exactly the kind of thing that gets forgotten once,
which is all it takes for an IDOR.

TenantScopedSession subclasses sqlalchemy.orm.Session directly (rather than
wrapping it, or relying on `with_loader_criteria` global-filter events) and
overrides exactly three methods:

- get()   -- cross-tenant fetch-by-primary-key returns None (treated as
             not-found, not forbidden -- this avoids confirming that a
             resource exists to a caller who isn't allowed to see it).
- query() -- automatically ANDs a tenant_id filter onto any TenantScoped
             entity being queried, before any .filter()/.join()/etc. the
             caller chains on top.
- add()   -- auto-stamps tenant_id on a new object if the caller didn't set
             one already, from the session's own current tenant.

This was verified empirically before being adopted -- see the two throwaway
scripts run during development, which is also why `with_loader_criteria` was
NOT used: it does not reliably cover Session.get() across SQLAlchemy
versions, and a security mechanism that "usually" works is not a security
mechanism.

WHAT THIS DOES NOT COVER (documented honestly, not hidden):
- Raw SQL / session.execute(text(...)) is not filtered. Nothing in this
  codebase currently does that (verified: no `session.execute(text(` or
  raw cursor usage anywhere in app/), but a future contributor adding raw
  SQL would silently bypass tenant scoping. A production hardening pass
  should add a lint rule or code-review checklist item for this.
- SQLAlchemy relationship()-based lazy loading is not intercepted (this
  codebase does not declare any `relationship()` attributes -- everything
  is explicit FK columns and manual queries -- so this gap has zero surface
  area today, but would need the same treatment if relationships were added
  later).
- This is tenant *identification* enforcement, not tenant *authentication*.
  Combined with the RBAC layer (app/core/authz.py), a request's tenant comes
  from a verified user's bearer token, not a client-supplied header --
  see authz.py for exactly where identity is established.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import TextClause


class TenantScopedSession(Session):
    """A normal SQLAlchemy Session for everything except get()/query()/add(),
    which are tenant-aware. isinstance(x, Session) is still True for
    instances of this class, so existing `db: Session` type hints throughout
    the codebase remain accurate -- no call site needed to change its
    signature for this to take effect."""

    _tenant_id: str | None = None

    def set_tenant(self, tenant_id: str | None) -> None:
        self._tenant_id = tenant_id

    def execute(self, statement, *args, **kwargs):
        """Reject textual SQL while a tenant scope is active.

        ORM query() and get() are tenant-filtered below. Session.execute(text(...))
        is not, so allowing it would silently bypass the isolation boundary.
        System-scoped sessions (tenant_id=None) retain their existing behavior.
        For tenant-scoped work, use ORM statements that preserve entity scoping.
        """
        if self._tenant_id is not None and isinstance(statement, TextClause):
            raise PermissionError(
                "Textual SQL is prohibited in tenant-scoped sessions; "
                "use tenant-scoped ORM queries."
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
    """Temporarily set a session's tenant, restoring the previous value on
    exit. Used by the seed script, which legitimately writes rows for
    multiple tenants in one run -- every other caller (routes, services)
    should have exactly one tenant for the lifetime of the session."""
    previous = db.current_tenant_id
    db.set_tenant(tenant_id)
    try:
        yield db
    finally:
        db.set_tenant(previous)
