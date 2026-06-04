import pytest
from app import create_app
from extensions import db
from models import User
from datetime import datetime, timedelta
import pyotp

@pytest.fixture
def app():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    
    with app.app_context():
        db.create_all()
        # Create a test user
        user = User(username='testuser', email='test@test.com')
        user.set_password('TestPass123!')
        db.session.add(user)
        db.session.commit()
        
        yield app
        
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

def test_lockout_mechanism(client, app):
    # Try 5 failed logins
    for i in range(5):
        client.post('/login', data={'email': 'test@test.com', 'password': 'wrongpassword'})
        
    with app.app_context():
        user = User.query.filter_by(email='test@test.com').first()
        assert user.failed_logins >= 5
        assert user.lockout_until is not None
        assert user.lockout_until > datetime.utcnow()
        
    # Attempting to login with correct password should still fail because of lockout
    resp = client.post('/login', data={'email': 'test@test.com', 'password': 'TestPass123!'})
    assert b'Account locked' in resp.data
    
    # Simulate time passing (reset lockout_until)
    with app.app_context():
        user = User.query.filter_by(email='test@test.com').first()
        user.lockout_until = datetime.utcnow() - timedelta(minutes=1)
        db.session.commit()
        
    # Login should now succeed and reset failed_logins
    resp = client.post('/login', data={'email': 'test@test.com', 'password': 'TestPass123!'})
    with app.app_context():
        user = User.query.filter_by(email='test@test.com').first()
        assert user.failed_logins == 0
        assert user.lockout_until is None

def test_mfa_verification_flow(client, app):
    # Setup MFA for user
    with app.app_context():
        user = User.query.filter_by(email='test@test.com').first()
        user.mfa_enabled = True
        user.mfa_secret = pyotp.random_base32()
        secret = user.mfa_secret
        db.session.commit()
        
    # Login with correct password
    resp = client.post('/login', data={'email': 'test@test.com', 'password': 'TestPass123!'}, follow_redirects=True)
    # It should redirect to MFA page
    assert b'Two-Factor Authentication' in resp.data
    
    # Post wrong code
    resp = client.post('/verify_mfa', data={'token': '000000'})
    assert b'Invalid 6-digit token' in resp.data
    
    # Post correct code
    totp = pyotp.TOTP(secret)
    correct_token = totp.now()
    resp = client.post('/verify_mfa', data={'token': correct_token}, follow_redirects=True)
    assert b'Login successful' in resp.data
