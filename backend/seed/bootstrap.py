"""Bootstrap deterministic demo data only on an isolated privileged demo DB.

The seed path intentionally rebuilds the whole demo universe. It must never
run under the restricted production runtime role, which is tenant-scoped and
has no BYPASSRLS or TRUNCATE privilege.
"""
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import entities as m
from seed.seed import run_seed


def main() -> None:
    settings = get_settings()
    if not settings.demo_mode:
        print("Demo bootstrap skipped: DEMO_MODE=false")
        return
    if not settings.demo_allow_global_reset:
        raise RuntimeError(
            "Demo bootstrap requires DEMO_ALLOW_GLOBAL_RESET=true on an isolated demo database."
        )

    db = SessionLocal()
    try:
        if db.get_bind().dialect.name == "postgresql":
            role_is_bypass = db.connection().execute(
                text("SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user")
            ).scalar_one()
            if not role_is_bypass:
                raise RuntimeError(
                    "Demo bootstrap requires a privileged isolated database role; "
                    "the restricted runtime role cannot reset all tenants."
                )

        db.set_tenant(None)
        expected_admin_token = "3e7d80fdfed273606f4c76ff8b24f98b098d2f129a31e399"
        admin_exists = db.query(m.User).filter(m.User.api_token == expected_admin_token).first()
        if admin_exists:
            print("Demo bootstrap skipped: deterministic administrator already present")
            return
        result = run_seed(db, seed_value=settings.seed)
        print(f"Demo bootstrap complete: {result}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
