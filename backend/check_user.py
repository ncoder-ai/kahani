#!/usr/bin/env python3
"""
Script to check and reset user account for testing
"""
import sys
import os

# Add the backend directory to Python path
sys.path.append('/Users/user/apps/kahani/backend')

from app.database import get_db
from app.models import User
from app.utils.security import get_password_hash, verify_password
from sqlalchemy.orm import Session

def check_user():
    """Check and fix user account"""
    db = next(get_db())
    
    # Find the test user
    user = db.query(User).filter(User.email == "test@test.com").first()
    
    if not user:
        print("User test@test.com not found. Creating user...")
        # Create the user
        hashed_password = get_password_hash("test")
        user = User(
            email="test@test.com",
            username="testuser",
            display_name="Test User",
            hashed_password=hashed_password,
            is_active=True
        )
        db.add(user)
        db.commit()
        print("User created successfully!")
    else:
        print(f"User found: {user.email}")
        print(f"Username: {user.username}")
        print(f"Is active: {user.is_active}")
        
        # Test password verification
        if verify_password("test", user.hashed_password):
            print("Password 'test' is correct!")
        else:
            print("Password 'test' is incorrect. Updating password...")
            user.hashed_password = get_password_hash("test")
            user.is_active = True
            db.commit()
            print("Password updated to 'test'")
    
    db.close()

if __name__ == "__main__":
    check_user()