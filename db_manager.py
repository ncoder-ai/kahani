#!/usr/bin/env python3
"""
Database user management script
"""
import sqlite3
import os

# Database path
db_path = "/Users/nishant/apps/kahani/backend/data/kahani.db"

def list_users():
    """List all users in the database"""
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT id, email, username, display_name, is_active FROM users")
        users = cursor.fetchall()
        
        if not users:
            print("No users found in database")
        else:
            print("Users in database:")
            print("ID | Email | Username | Display Name | Active")
            print("-" * 60)
            for user in users:
                print(f"{user[0]} | {user[1]} | {user[2]} | {user[3]} | {user[4]}")
    except Exception as e:
        print(f"Error querying users: {e}")
    finally:
        conn.close()

def delete_user(email):
    """Delete a user by email"""
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # First check if user exists
        cursor.execute("SELECT id, email FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()
        
        if not user:
            print(f"User with email '{email}' not found")
            return
        
        print(f"Found user: ID={user[0]}, Email={user[1]}")
        
        # Delete user
        cursor.execute("DELETE FROM users WHERE email = ?", (email,))
        conn.commit()
        
        if cursor.rowcount > 0:
            print(f"Successfully deleted user '{email}'")
        else:
            print(f"No user deleted (maybe already gone?)")
            
    except Exception as e:
        print(f"Error deleting user: {e}")
    finally:
        conn.close()

def main():
    print("=== Kahani Database User Management ===")
    print()
    
    # List current users
    print("Current users:")
    list_users()
    print()
    
    # Ask what to do
    action = input("Enter 'delete' to delete test@test.com, or 'list' to just list users: ").strip().lower()
    
    if action == 'delete':
        delete_user('test@test.com')
        print()
        print("Users after deletion:")
        list_users()
    elif action == 'list':
        print("No changes made")
    else:
        print("Invalid action")

if __name__ == "__main__":
    main()