import os
import re
import json
import imaplib
import email
import email.policy
import logging
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

class EmailFetcher:
    """
    Manages secure IMAP connections using UID-based searching, handles modern
    email parsing via email.policy.default, filters payloads by target
    keywords/senders, and isolates unprocessed payloads via local JSON caching
    and rule-based pre-filtering (Phase A).
    """

    # Phase A: Geographic disqualifiers -- hard reject before Gemini
    GEO_REJECT = [
        "must reside in", "must be located in", "authorized to work in",
        "onsite", "on-site", "on site", "in-person", "in person",
        "relocation required", "relocation assistance",
        "uk only", "us only", "eu only", "canada only",
    ]

    # Phase A: Content disqualifiers -- hard reject before Gemini
    CONTENT_REJECT = [
        "newsletter", "free course", "tutorial", "webinar",
        "discount", "sale", "your account", "billing",
    ]

    def __init__(self):
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=str(PROJECT_ROOT / ".env"))

        self.username = os.getenv("EMAIL_USER")
        self.password = os.getenv("EMAIL_APP_PASSWORD")
        self.imap_server = os.getenv("IMAP_SERVER") or "imap.gmail.com"
        self.imap_port = 993

        # Target sender domains -- kept narrow to reduce false positives.
        # 'no-reply' deliberately excluded: it matches every automated email
        # on the internet and relies entirely on the pre-filter as a guard,
        # which is too fragile. Rely on target_keywords for non-platform mail.
        self.target_senders = [
            "linkedin", "upwork", "indeed", "glassdoor",
            "remotive", "flexjobs", "turing", "welo",
        ]

        # Keywords that signal a job alert (checked against subject + body)
        self.target_keywords = [
            "annotation", "evaluation", "evaluator", "labeling",
            "prompt", "llm", "ai data", "model", "outlier",
        ]

        self.cache_dir = PROJECT_ROOT / "data"
        self.cache_file = self.cache_dir / "processed_ids.json"
        self.cache_dir.mkdir(exist_ok=True)

        # Set (not list) for O(1) lookup and no duplicate accumulation
        self.processed_ids = self._load_cache()
        self.mail = None

    # ── Cache Management ───────────────────────────────────────────────────

    def _load_cache(self) -> set:
        """
        Loads the set of processed UIDs from disk. Returns an empty set if
        the file is missing or corrupted -- guarantees a safe start state.
        """
        if not self.cache_file.exists():
            return set()
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(data) if isinstance(data, list) else set()
        except Exception as e:
            logging.error(f"Error loading cache file: {e}")
            return set()

    def _save_cache(self) -> None:
        """
        Persists the in-memory processed_ids set to disk as a JSON list.
        """
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(list(self.processed_ids), f, indent=4)
        except Exception as e:
            logging.error(f"Error saving cache file: {e}")

    # ── IMAP Connection ────────────────────────────────────────────────────

    def connect(self) -> None:
        """
        Opens an SSL IMAP connection to Gmail and authenticates.

        Raises:
            RuntimeError: If EMAIL_USER or EMAIL_APP_PASSWORD is missing.
            ConnectionError: If the IMAP handshake or login fails.
        """
        if not self.username or not self.password:
            raise RuntimeError(
                "Critical Configuration Error: EMAIL_USER or "
                "EMAIL_APP_PASSWORD is missing from your .env file."
            )
        try:
            logging.info(f"Connecting to {self.imap_server}:{self.imap_port} over SSL...")
            self.mail = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            self.mail.login(self.username, self.password)
            logging.info("Successfully authenticated and connected to IMAP server.")
        except imaplib.IMAP4.error as e:
            raise ConnectionError(f"IMAP authentication failed: {e}")

    def disconnect(self) -> None:
        """
        Cleanly closes the IMAP session. Safe to call even if connect()
        was never called or the connection was already dropped.
        """
        if self.mail:
            try:
                self.mail.logout()
            except Exception:
                pass
            self.mail = None

    # ── Phase A Pre-Filter ─────────────────────────────────────────────────

    def _is_locally_rejectable(self, text: str) -> bool:
        """
        Hard-reject filter run before sending any email to brain.py.

        Uses word-boundary matching for single-word patterns to avoid
        substring false positives (e.g. 'sale' inside 'wholesale' or
        'in-person' not matching 'inspiration'). Multi-word phrases use
        direct substring matching since they won't appear as parts of
        unrelated words by nature.

        Args:
            text: Lowercased combined subject + body string.

        Returns:
            True if the email should be skipped (geographic disqualifier
            or non-job content), False if it should proceed to Gemini.
        """
        text_lower = text.lower()
        for phrase in (self.GEO_REJECT + self.CONTENT_REJECT):
            if " " in phrase:
                if phrase in text_lower:
                    return True
            else:
                if re.search(r"\b" + re.escape(phrase) + r"\b", text_lower):
                    return True
        return False

    # ── Email Fetching ─────────────────────────────────────────────────────

    def fetch_job_emails(self) -> list:
        """
        Fetches and screens candidate job-alert emails from the last 7 days.

        Pipeline per email:
          1. UID deduplication check (skip if cached)
          2. Fetch raw RFC822 message
          3. Extract and clean body text
          4. Sender/keyword gate (cache and skip if neither match)
          5. Phase A pre-filter (cache and skip if geo/content disqualified)
          6. Append to results for Gemini screening

        UIDs are only cached after a usable body is extracted, so emails
        that fail extraction are left uncached and retried on the next run.

        Returns:
            List of dicts: [{"message_id": uid, "subject": str, "clean_text": str}]
        """
        if not self.mail:
            raise RuntimeError("IMAP connection is not active. Call connect() first.")

        logging.info("Selecting INBOX...")
        self.mail.select("INBOX")

        target_date = (datetime.now() - timedelta(days=7)).strftime("%d-%b-%Y")
        criterion = f'(SINCE "{target_date}")'
        logging.info(f"Searching mailbox using criteria: {criterion}")

        status, data = self.mail.uid("search", None, criterion)
        if status != "OK" or not data[0]:
            logging.info("Found 0 candidate emails from the last 7 days.")
            return []

        uids = data[0].split()
        logging.info(f"Found {len(uids)} total email payloads within the time window.")

        extracted_emails = []

        for uid_bytes in uids:
            uid_str = uid_bytes.decode("utf-8")

            if uid_str in self.processed_ids:
                continue

            status, msg_data = self.mail.uid("fetch", uid_bytes, "(RFC822)")
            if status != "OK" or not msg_data:
                continue

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email, policy=email.policy.default)

            subject = str(msg.get("Subject", "No Subject"))
            sender = str(msg.get("From", "")).lower()

            body_content = self._extract_body(msg)

            if not body_content or not body_content.strip():
                logging.warning(
                    f"Empty body extraction for UID {uid_str}. "
                    "Skipping cache commit to allow retry."
                )
                continue

            content_to_check = f"{subject} {body_content}".lower()
            is_target_sender = any(s in sender for s in self.target_senders)
            has_target_keyword = any(k in content_to_check for k in self.target_keywords)

            if not (is_target_sender or has_target_keyword):
                # Not a job alert -- cache and skip without touching Gemini
                self.processed_ids.add(uid_str)
                self._save_cache()
                continue

            # Phase A: hard-reject on geo/content disqualifiers
            if self._is_locally_rejectable(content_to_check):
                logging.info(
                    f"[SKIPPED_PREFILTER] Local reject — "
                    f"disqualified geography or non-job content "
                    f"(UID: {uid_str}) — '{subject}'"
                )
                self.processed_ids.add(uid_str)
                self._save_cache()
                continue

            logging.info(f"Successfully matched target filter: '{subject}' [UID: {uid_str}]")

            extracted_emails.append({
                "message_id": uid_str,
                "subject": subject,
                "clean_text": body_content,
            })

            self.processed_ids.add(uid_str)
            self._save_cache()

        logging.info(
            f"Extraction sequence complete. "
            f"Forwarding {len(extracted_emails)} targeted emails to Gemini Brain."
        )
        return extracted_emails

    # ── Body Extraction ────────────────────────────────────────────────────

    def _extract_body(self, msg) -> str:
        """
        Extracts the best available plain-text representation of the email.

        Tries the modern email.policy.default API first (msg.get_body),
        then falls back to recursive multipart walking, then single-part
        decoding. HTML content is always routed through _clean_html.

        Returns:
            Cleaned plain-text string, or "" if no usable body found.
        """
        try:
            body_part = msg.get_body(preferencelist=("plain", "html"))
            if body_part:
                content = body_part.get_content()
                if body_part.get_content_type() == "text/html":
                    return self._clean_html(content)
                return content.strip()
        except Exception:
            pass

        if msg.is_multipart():
            html_part = None
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    try:
                        return part.get_payload(decode=True).decode(
                            part.get_content_charset() or "utf-8", errors="ignore"
                        ).strip()
                    except Exception:
                        pass
                elif content_type == "text/html":
                    html_part = part
            if html_part:
                try:
                    html_payload = html_part.get_payload(decode=True).decode(
                        html_part.get_content_charset() or "utf-8", errors="ignore"
                    )
                    return self._clean_html(html_payload)
                except Exception:
                    pass
        else:
            content_type = msg.get_content_type()
            try:
                payload = msg.get_payload(decode=True).decode(
                    msg.get_content_charset() or "utf-8", errors="ignore"
                )
                if content_type == "text/html":
                    return self._clean_html(payload)
                return payload.strip()
            except Exception:
                pass

        return ""

    # ── HTML Cleaning ──────────────────────────────────────────────────────

    def _clean_html(self, html_content: str) -> str:
        """
        Strips HTML down to clean, whitespace-normalized plain text.

        Removes structural noise tags, LinkedIn/platform CSS class patterns,
        and known boilerplate phrases. The result is what Gemini actually
        reads -- keeping it signal-dense is what makes 1.7s evaluation
        latency possible.

        Args:
            html_content: Raw HTML string from email body.

        Returns:
            Single-line, whitespace-normalized plain-text string.
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html_content, "html.parser")

        for tag in soup(["script", "style", "meta", "nav", "footer", "svg", "button"]):
            tag.decompose()

        noise_patterns = [
            "msg_footer", "linkedin-footer", "email-footer",
            "premium-upsell", "widget", "social-proof",
            "legal", "unsubscribe", "tracking",
        ]
        for tag in soup.find_all(class_=True):
            class_str = " ".join(tag.get("class", [])).lower()
            if any(p in class_str for p in noise_patterns):
                tag.decompose()

        text = soup.get_text(separator="\n")
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

        boilerplate_signals = [
            "try premium", "install", "widget", "unsubscribe",
            "share their thoughts", "you're receiving",
            "linkedin corporation", "©", "manage preferences",
        ]
        clean_lines = [
            ln for ln in lines
            if not any(sig in ln.lower() for sig in boilerplate_signals)
        ]

        return " ".join(clean_lines)