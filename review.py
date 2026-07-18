import os
import sys
import time
import shutil
import sqlite3
import subprocess
import datetime

# Attempt to load pyperclip, providing a clear error if missing
try:
    import pyperclip
except ImportError:
    print("\n❌ Error: The 'pyperclip' library is missing.")
    print("Please install it by running: pip install pyperclip\n")
    sys.exit(1)

# Import the dashboard rendering engine
try:
    from dashboard import generate_dashboard
except ImportError:
    print("\n❌ Error: Could not import 'generate_dashboard' from 'dashboard.py'.")
    print("Please ensure 'dashboard.py' is in the same directory.")
    sys.exit(1)

# Define core directory paths relative to the script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DRAFT_DIR = os.path.join(BASE_DIR, "outreach_drafts")
SENT_DIR = os.path.join(DRAFT_DIR, "sent")
DB_PATH = os.path.join(BASE_DIR, "data", "tracker.db")

VALID_STATUSES = ['drafted', 'applied', 'interviewing', 'rejected', 'accepted']

def check_cold_start():
    """Validates the environment for non-technical users to prevent tracebacks."""
    missing = []
    if not os.path.exists(os.path.join(BASE_DIR, ".env")):
        missing.append(".env (Missing credentials - please duplicate .env.example)")
    if not os.path.exists(DB_PATH):
        missing.append("tracker.db (Database missing - please run init_db.py)")
    if not os.path.exists(os.path.join(BASE_DIR, ".venv")):
        missing.append(".venv (Python virtual environment missing - run install.bat)")
    
    if missing:
        print("\n⚠️  COLD START SETUP REQUIRED:")
        for m in missing:
            print(f"  - {m}")
        print("\nPlease complete the setup checklist before running the CRM.")
        sys.exit(1)

def get_time_ago(timestamp):
    """Calculates a human-readable string representing how long ago a timestamp occurred."""
    seconds_ago = time.time() - timestamp
    if seconds_ago < 60:
        return "just now"
    elif seconds_ago < 3600:
        minutes = int(seconds_ago // 60)
        return f"{minutes} min ago"
    elif seconds_ago < 86400:
        hours = int(seconds_ago // 3600)
        return f"{hours} hr ago"
    else:
        days = int(seconds_ago // 86400)
        return f"{days} day ago"

def parse_draft_metadata(content):
    """Parses the structured metadata headers from the top of the draft file."""
    metadata = {"role": "Unknown", "company": "Unknown", "email_id": "UNKNOWN", "job_id": "UNKNOWN"}
    for line in content.splitlines():
        if line.startswith("ROLE:"): metadata["role"] = line.replace("ROLE:", "").strip()
        elif line.startswith("COMPANY:"): metadata["company"] = line.replace("COMPANY:", "").strip()
        elif line.startswith("EMAIL_ID:"): metadata["email_id"] = line.replace("EMAIL_ID:", "").strip()
        elif line.startswith("JOB_ID:"): metadata["job_id"] = line.replace("JOB_ID:", "").strip()
        elif line.startswith("=" * 40): break
    return metadata

def log_application_to_db(job_id, company, role, email_id):
    """Logs entry with WAL hardening and retry logic."""
    for attempt in range(3):
        try:
            with sqlite3.connect(DB_PATH, timeout=5.0) as conn:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA busy_timeout=5000;")
                conn.execute("""
                    INSERT OR IGNORE INTO applications (job_id, company, role, status, source_email_id, application_status)
                    VALUES (?, ?, ?, 'sent', ?, 'drafted')
                """, (job_id, company, role, email_id))
                conn.commit()
            print(f"   💾 Database Log: Saved entry for '{role}' to tracker.db.")
            return True
        except sqlite3.OperationalError as e:
            if attempt == 2:
                print(f"   ⚠️  Database Error: Could not write tracking record. ({e})")
                return False
            time.sleep(0.5)

def update_application_status(app_id, new_status):
    """Updates only the application_status column with retry logic."""
    if new_status not in VALID_STATUSES: return False
    for attempt in range(3):
        try:
            with sqlite3.connect(DB_PATH, timeout=5.0) as conn:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA busy_timeout=5000;")
                conn.execute("UPDATE applications SET application_status = ? WHERE id = ?", (new_status, app_id))
                conn.commit()
            print(f"   💾 Database Log: Updated application #{app_id} status to '{new_status}'.")
            return True
        except sqlite3.OperationalError as e:
            if attempt == 2:
                print(f"   ⚠️  Database Error: Could not update status. ({e})")
                return False
            time.sleep(0.5)

def sync_dashboard_to_netlify():
    """Silently fails on git/network errors to preserve UX."""
    generate_dashboard()
    print("\n🌐 Git Sync: Pushing updated dashboard...")
    try:
        # SECURITY FIX: ONLY push the dashboard.html, NEVER the database
        subprocess.run(["git", "add", "portfolio/dashboard.html"], check=True, cwd=BASE_DIR, capture_output=True, text=True)
        msg = f"build: auto-update tracker {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        subprocess.run(["git", "commit", "-m", msg], check=True, cwd=BASE_DIR, capture_output=True, text=True)
        subprocess.run(["git", "push", "origin", "main"], check=True, cwd=BASE_DIR, capture_output=True, text=True)
        print("   ✅ Sync Complete: Portfolio updating on Netlify.")
        return True
    except subprocess.CalledProcessError:
        print("   ⚠️ Dashboard sync will retry next run (Network/Git error).")
        return False
    except Exception:
        print("   ⚠️ Dashboard sync will retry next run (System error).")
        return False

def review_drafts_flow():
    print("\n" + "-"*45 + "\n📂 REVIEWING PENDING LOCAL DRAFTS\n" + "-"*45)
    if not os.path.exists(DRAFT_DIR): return
    drafts = []
    for item in os.listdir(DRAFT_DIR):
        p = os.path.join(DRAFT_DIR, item)
        if os.path.isfile(p) and item.lower().endswith(".txt"):
            drafts.append({"filename": item, "path": p, "mtime": os.path.getmtime(p)})
    if not drafts:
        print("✅ All caught up! No pending '.txt' drafts found.")
        return
    drafts.sort(key=lambda x: x["mtime"], reverse=True)
    for idx, draft in enumerate(drafts, start=1):
        print(f"  [{idx}] {draft['filename']} ({get_time_ago(draft['mtime'])})")
    
    while True:
        choice = input("\nEnter draft number to copy (or 'b' to go back): ").strip().lower()
        if choice == 'b': return
        if choice.isdigit() and 1 <= int(choice) <= len(drafts): break
        print("⚠️ Invalid input.")
    
    sel = drafts[int(choice) - 1]
    with open(sel["path"], "r", encoding="utf-8") as f: content = f.read()
    metadata = parse_draft_metadata(content)
    pyperclip.copy(content)
    print(f"\n📋 SUCCESS: '{sel['filename']}' copied to clipboard!")
    
    while True:
        ans = input("Mark as sent? Logs to tracker.db (y/n): ").strip().lower()
        if ans == 'n': break
        elif ans == 'y':
            os.makedirs(SENT_DIR, exist_ok=True)
            dp = os.path.join(SENT_DIR, sel["filename"])
            if os.path.exists(dp): os.remove(dp)
            shutil.move(sel["path"], dp)
            if log_application_to_db(metadata["job_id"], metadata["company"], metadata["role"], metadata["email_id"]):
                sync_dashboard_to_netlify()
            break

def update_status_flow():
    print("\n" + "-"*45 + "\n💼 CRM: UPDATE SENT APPLICATION STATUS\n" + "-"*45)
    if not os.path.exists(DB_PATH): return
    
    # Use WAL mode for reading applications list safely
    with sqlite3.connect(DB_PATH, timeout=5.0) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        apps = conn.execute("SELECT id, role, company, application_status, sent_at FROM applications ORDER BY sent_at DESC LIMIT 15").fetchall()
        
    if not apps: return
    for idx, (a_id, r, c, s, t) in enumerate(apps, start=1):
        print(f"  [{idx}] {r} @ {c} (Status: {s})")
        
    while True:
        choice = input("\nEnter app number (or 'b'): ").strip().lower()
        if choice == 'b': return
        if choice.isdigit() and 1 <= int(choice) <= len(apps): break
        
    sel_id, sel_role, sel_comp, cur_status, _ = apps[int(choice) - 1]
    print(f"\nUpdating: '{sel_role}' @ '{sel_comp}'\nAvailable States:")
    for idx, state in enumerate(VALID_STATUSES, start=1): print(f"  [{idx}] {state}")
    
    while True:
        state_choice = input("\nEnter new status number: ").strip()
        if state_choice.isdigit() and 1 <= int(state_choice) <= len(VALID_STATUSES): break
        
    if update_application_status(sel_id, VALID_STATUSES[int(state_choice) - 1]):
        sync_dashboard_to_netlify()

def main():
    check_cold_start()
    while True:
        print("\n" + "="*45 + "\n🚀 JOB SCOUT AGENT: DRAFT & STATUS MANAGER\n" + "="*45)
        print("  [1] Review Pending Drafts\n  [2] Update Sent Application Status\n  [q] Quit")
        c = input("Select an option: ").strip().lower()
        if c == 'q': sys.exit(0)
        elif c == '1': review_drafts_flow()
        elif c == '2': update_status_flow()

if __name__ == "__main__":
    main()