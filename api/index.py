"""Vercel Flask entry point. Database and originals are durable PostgreSQL data."""
import os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app import create_app
from app.migrate import upgrade
from app.seed import seed
from app.models import db
from sqlalchemy import text

if not os.getenv('DATABASE_URL'):raise RuntimeError('Vercel deployment requires DATABASE_URL')
if not os.getenv('SECRET_KEY'):raise RuntimeError('Vercel deployment requires a persistent SECRET_KEY')
app=create_app()
with app.app_context():
    # Serialize schema/seed setup across cold-starting serverless instances.
    with db.engine.connect() as connection:
        connection.execute(text('SELECT pg_advisory_lock(49261735)'))
        try:
            upgrade()
            if app.config['DEMO_MODE']:seed()
        finally:
            connection.execute(text('SELECT pg_advisory_unlock(49261735)'))
