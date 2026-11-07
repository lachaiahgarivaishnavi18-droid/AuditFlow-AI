"""Versioned initial schema; future migrations must be explicit functions."""
from sqlalchemy import text
from .models import db,DocumentBlob
def upgrade():
    with db.engine.begin() as conn:
        conn.execute(text('CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY)'))
        applied={r[0] for r in conn.execute(text('SELECT version FROM schema_migrations'))}
    if 1 not in applied:
        db.create_all()
        with db.engine.begin() as conn: conn.execute(text('INSERT INTO schema_migrations (version) VALUES (1)'))
    if 2 not in applied:
        DocumentBlob.__table__.create(db.engine,checkfirst=True)
        with db.engine.begin() as conn:conn.execute(text('INSERT INTO schema_migrations (version) VALUES (2)'))
