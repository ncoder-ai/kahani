#!/usr/bin/env python3
import sqlite3
import os

# Get the database path
db_path = os.path.join(os.path.dirname(__file__), "data", "kahani.db")

if not os.path.exists(db_path):
    print(f"Database not found at: {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("=== USER_SETTINGS TABLE SCHEMA ===")
cursor.execute("PRAGMA table_info(user_settings);")
user_settings_columns = cursor.fetchall()
for row in user_settings_columns:
    print(f"Column: {row[1]}, Type: {row[2]}, NotNull: {row[3]}, Default: {row[4]}")

print("\n=== STORIES TABLE SCHEMA ===")
cursor.execute("PRAGMA table_info(stories);")
stories_columns = cursor.fetchall()
for row in stories_columns:
    print(f"Column: {row[1]}, Type: {row[2]}, NotNull: {row[3]}, Default: {row[4]}")

print("\n=== ALL TABLES ===")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
for table in tables:
    print(f"Table: {table[0]}")

conn.close()