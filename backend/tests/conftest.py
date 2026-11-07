import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import create_app
from app.models import db,User
from werkzeug.security import generate_password_hash

@pytest.fixture
def app(tmp_path):
    app=create_app({'TESTING':True,'SECRET_KEY':'test-secret-with-more-than-thirty-two-characters','SQLALCHEMY_DATABASE_URI':'sqlite://','UPLOAD_DIR':str(tmp_path/'uploads')})
    with app.app_context():
        db.create_all()
        for email,role in [('auditor@test.com','auditor'),('other@test.com','auditor'),('reviewer@test.com','reviewer'),('admin@test.com','administrator')]: db.session.add(User(username=role,email=email,role=role,password_hash=generate_password_hash('TestPassword!2026')))
        db.session.commit()
    yield app
    with app.app_context(): db.session.remove();db.drop_all()
@pytest.fixture
def client(app): return app.test_client()
@pytest.fixture
def headers(client):
    response=client.post('/api/auth/login',json={'email':'auditor@test.com','password':'TestPassword!2026'})
    return {'Authorization':'Bearer '+response.json['token']}
@pytest.fixture
def audit(client,headers):
    response=client.post('/api/audits',headers=headers,json={'project_name':'Synthetic audit','organization_name':'SYNTHETIC Company','financial_year':'2025-26','audit_period_start':'2025-04-01','audit_period_end':'2026-03-31','reviewer_id':3})
    assert response.status_code==201,response.json
    return response.json['id']
