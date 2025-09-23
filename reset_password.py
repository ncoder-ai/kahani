#!/usr/bin/env python3
"""
Simple script to reset a user's password in the Kahani database
"""
import sys
import sqlite3
from passlib.context import CryptContext

# Same password context used in the app
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def reset_password(email: str, new_password: str):
    """Reset password for a user"""
    # Hash the new password
    hashed_password = pwd_context.hash(new_password)
    
    # Connect to database
    conn = sqlite3.connect('data/kahani.db')
    cursor = conn.cursor()
    
    # Update the user's password
    cursor.execute(
        "UPDATE users SET hashed_password = ?, updated_at = CURRENT_TIMESTAMP WHERE email = ?",
        (hashed_password, email)
    )
    
    if cursor.rowcount == 0:
        print(f"❌ No user found with email: {email}")
        conn.close()
        return False
    
    conn.commit()
    conn.close()
    
    print(f"✅ Password updated successfully for {email}")
    return True

if __name__ == "__main__":
    email = "user@example.com"
    new_password = "newpassword123"
    
    print(f"Resetting password for: {email}")
    print(f"New password will be: {new_password}")
    
    if reset_password(email, new_password):
        print("\n🎉 You can now login with:")
        print(f"   Email: {email}")
        print(f"   Password: {new_password}")
    else:
        print("\n❌ Password reset failed")