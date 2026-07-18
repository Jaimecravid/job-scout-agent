import sys
import logging
import time
import sqlite3
import hashlib
from pathlib import Path

# Establish project root and append to sys.path for robust absolute imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

from src.fetcher import EmailFetcher
from src.brain import GeminiBrain
from src.logger import JobLogger

# Import our outreach module from the project root
from outreach import generate_outreach_draft

# Configure top-level logging exclusively for internal orchestration tracking
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("Router")

# Database configuration (Absolute path resolution to tracker.db)
DB_PATH = PROJECT_ROOT / "data" / "tracker.db"

def make_job_id(company: str, role: str, source_email_id: str) -> str:
    """Generates a unique, deterministic sha256 hash for a specific job matching."""
    raw = f"{company.strip()}|{role.strip()}|{source_email_id.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def is_duplicate(job_id: str) -> bool:
    """Queries tracker.db to see if this specific job_id was already logged."""
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            cur = conn.execute("SELECT 1 FROM applications WHERE job_id = ?", (job_id,))
            return cur.fetchone() is not None
    except Exception as e:
        logger.error(f"Database error checking duplicate: {e}")
        return False # Fallback to False to prevent losing leads

def main() -> None:
    """
    Orchestrates the complete Job Scout Agent pipeline:
    1. Initializes strictly scoped modules.
    2. Connects to IMAP to fetch cached/unread email payloads.
    3. Routes plain-text payloads to the Gemini Brain for schema extraction.
    4. Logs results to the persistent data directory.
    5. Deduplicates matches against tracker.db to prevent redundant actions.
    6. Triggers the Outreach Module if a new MATCH/Angola Eligible lead is found.
    """
    print("\n" + "="*40)
    print("🚀 JOB SCOUT AGENT PIPELINE INITIATED")
    print("="*40)
    
    logger.info("Bootstrapping modules...")

    try:
        fetcher = EmailFetcher()
        brain = GeminiBrain()
        job_logger = JobLogger()
    except Exception as e:
        logger.error(f"Fatal Initialization Error: {e}")
        print(f"\n❌ ERROR: System bootstrapping failed. Check .env and configs.\n   Details: {e}")
        return

    try:
        print("\n[1/4] Establishing secure IMAP connection...")
        fetcher.connect()
        
        print("[2/4] Scanning INBOX for relevant target payloads...")
        emails = fetcher.fetch_job_emails()
        
        if not emails:
            print("\n✅ STANDBY: No new targeted emails found in IMAP cache.")
            return

        print(f"\n[3/4] AI Screening Pipeline engaged. {len(emails)} candidate emails queued.")

        for idx, email_data in enumerate(emails, start=1):
            # Safe parsing for individual incoming email data blocks
            if isinstance(email_data, dict):
                msg_id = email_data.get('message_id', 'UNKNOWN_UID')
                text_content = email_data.get('clean_text', '')
            else:
                msg_id = 'SIMULATED_UID'
                text_content = str(email_data)

            print(f"\n--- Processing Candidate {idx}/{len(emails)} [UID: {msg_id}] ---")

            if not text_content:
                logger.warning(f"Payload missing for UID {msg_id}. Skipping to next.")
                print("   ⚠️  Status: SKIPPED (Empty Payload)")
                continue
            
            # Smart Pacer: Wait 12 seconds between requests to avoid Gemini 5 RPM Free Tier Lockout
            # (Skips the wait on the very first email to save time)
            if idx > 1:
                print("   ⏳ Pacing API request (12s pause) to prevent rate limit lockout...")
                time.sleep(12)
            
            # Send to LLM
            print("   🧠 Analyzing constraints via Gemini 2.5 Flash...")
            result = brain.screen_email(text_content)
            
            # Safety Guard: Ensure result is an evaluatable dictionary object
            if isinstance(result, str):
                logger.error(f"Brain returned raw string: {result[:100]}")
                print("   ❌ Status: SKIPPED (Invalid Brain Response Type)")
                continue
            
            # Console UI Feedback
            status_val = result.get('status', 'ERROR')
            emoji = "✅" if status_val == "MATCH" else "❌" if status_val == "JUNK" else "⚠️"
            
            print(f"   {emoji} Target Alignment: {status_val}")
            print(f"   🇦🇴 Angola Eligible:  {result.get('angola_eligible')}")
            print(f"   📊 Match Confidence: {result.get('match_percentage')}%")
            
            role_title = result.get('role_title', 'Target Role')
            company_name = result.get('platform', 'Target Company')
            print(f"   🏢 Role Identified:  {role_title} @ {company_name}")
            
            # Storage layer commit
            job_logger.log_result(result)
            logger.info(f"UID {msg_id} metrics written to disk.")

            # --- DEDUPLICATION CHECK ---
            job_id = make_job_id(company_name, role_title, msg_id)
            if is_duplicate(job_id):
                print(f"   ⏭️  Status: SKIPPED (Duplicate - Job already exists in database)")
                continue

            # --- TRIGGER OUTREACH GENERATION ---
            if status_val in ["MATCH", "Angola Eligible"]:
                print("   📝 Action Required: Generating tailored outreach draft...")
                draft_path = generate_outreach_draft(
                    job_title=role_title,
                    company_name=company_name,
                    job_description=text_content,
                    source_email_id=msg_id,
                    job_id=job_id
                )
                if draft_path:
                    print(f"   ✉️  Draft ready for review: {draft_path}")

        print("\n[4/4] Pipeline execution cycle complete.")

    except Exception as e:
        logger.error(f"Pipeline crashed during execution routing: {e}")
        print(f"\n❌ PIPELINE ERROR: {e}")
        
    finally:
        print("\n[SYS] Terminating active connections safely...")
        try:
            fetcher.disconnect()
        except Exception:
            pass
        print("="*40)
        print("🛑 AGENT OFFLINE")
        print("="*40 + "\n")

if __name__ == "__main__":
    main()