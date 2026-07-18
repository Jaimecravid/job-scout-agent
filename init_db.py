import sqlite3
import os

def init_database():
    # Automatically resolve the exact, absolute path on your Windows machine
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = os.path.join(BASE_DIR, "data")
    
    # Ensure the data directory exists
    os.makedirs(DATA_DIR, exist_ok=True)
    db_path = os.path.join(DATA_DIR, "tracker.db")
    
    print(f"Initializing/Migrating database schema at: {db_path}...")
    
    with sqlite3.connect(db_path) as conn:
        # 1. Create table with the new application_status column if it's a brand new set-up
        conn.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT UNIQUE NOT NULL,
                company TEXT NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('sent', 'archived', 'ignored')) DEFAULT 'sent',
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                source_email_id TEXT,
                application_status TEXT NOT NULL DEFAULT 'drafted'
            );
        """)
        
        # Create the index
        conn.execute("CREATE INDEX IF NOT EXISTS idx_job_id ON applications(job_id);")
        
        # 2. Migration Check: Read columns to see if 'application_status' is present in an existing DB
        cursor = conn.execute("PRAGMA table_info(applications);")
        existing_columns = [row[1] for row in cursor.fetchall()]
        
        if "application_status" not in existing_columns:
            print("   🛠️  Migration: 'application_status' column missing. Running alter table...")
            try:
                conn.execute(
                    "ALTER TABLE applications ADD COLUMN application_status TEXT NOT NULL DEFAULT 'drafted';"
                )
                print("   ✅ Migration: Column successfully appended to schema.")
            except Exception as e:
                print(f"   ❌ Migration Error: Could not execute alter table. ({e})")
        else:
            print("   ✅ Schema: Database columns are completely up to date.")
            
        conn.commit()
        
    print("✅ Database successfully prepared.")

if __name__ == "__main__":
    init_database()