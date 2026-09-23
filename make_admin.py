"""Print a password hash to paste into Supabase users table, or create admin locally.

Usage:
  python make_admin.py "MyStrongPass123"     -> prints hash + SQL
"""
import sys
from werkzeug.security import generate_password_hash

pw = sys.argv[1] if len(sys.argv) > 1 else "RucuAdmin2026"
h = generate_password_hash(pw)
print("HASH:", h)
print()
print("Supabase SQL:")
print(f"insert into users (name,email,password_hash,role,status,created_at) values "
      f"('Super Admin','admin@rucu.ac.tz','{h}','SUPER ADMIN','active',now()::text);")
