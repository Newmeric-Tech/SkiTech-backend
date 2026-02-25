import sys
from db_connection import engine, SessionLocal
from sqlalchemy import text

def test_connection():
    try:
        # Try to connect and execute a simple query
        with engine.connect() as connection:
            result = connection.execute(text("SELECT version();"))
            row = result.fetchone()
            print(f"✅ Success! Database version: {row[0]}")
            return True
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print("\nPossible issues:")
        print("1. Is PostgreSQL running?")
        print("2. Are the details in your .env file correct?")
        print("3. Is the 'psycopg2-binary' package installed?")
        return False

if __name__ == "__main__":
    test_connection()
