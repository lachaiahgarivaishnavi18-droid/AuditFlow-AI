"""Initialize and verify only the project's explicitly pulled Vercel database."""
import os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from dotenv import dotenv_values
settings=dotenv_values(ROOT/'.env.production.local')
if not settings.get('DATABASE_URL'):raise RuntimeError('Pull production environment for this project first')
for key in ['DATABASE_URL','SECRET_KEY']:
    if settings.get(key) and settings[key]!='[SENSITIVE]':os.environ[key]=settings[key]
os.environ['DEMO_MODE']='true';os.environ['STORE_ORIGINALS_IN_DB']='true'
from app import create_app
from app.models import db,Audit,Document,DocumentBlob
from app.migrate import upgrade
from app.seed import seed
app=create_app()
with app.app_context():
    upgrade();seed()
    print({'database':'PostgreSQL','synthetic_audits':Audit.query.count(),'documents':Document.query.count(),'stored_originals':DocumentBlob.query.count()})
