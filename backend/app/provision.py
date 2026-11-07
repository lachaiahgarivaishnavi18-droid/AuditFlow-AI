"""Explicit operator CLI provisioning; not reachable through public registration."""
import getpass
from werkzeug.security import generate_password_hash
from .models import db,User,AuditLog
def create_user(email,username,role):
    if role not in ('administrator','auditor','reviewer'): raise ValueError('Invalid role')
    if '@' not in email: raise ValueError('Valid email required')
    if User.query.filter_by(email=email.lower()).first(): raise ValueError('User already exists')
    password=getpass.getpass('Password (minimum 12 characters): ')
    if len(password)<12 or len(password)>128: raise ValueError('Password must contain 12-128 characters')
    user=User(email=email.lower(),username=username,role=role,password_hash=generate_password_hash(password));db.session.add(user);db.session.flush()
    db.session.add(AuditLog(user_id=user.id,action='operator provision user',resource_type='user',resource_id=user.id,details={'role':role}));db.session.commit()
