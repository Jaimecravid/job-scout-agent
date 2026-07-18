import csv
import logging
import os
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
from plyer import notification
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

# Establish project root for secure, absolute path resolution on Windows
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Configure isolated logging for this module
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(ch)

TELEGRAM_TIMEOUT_SECONDS = 8


def _is_retryable_telegram_error(exception: BaseException) -> bool:
    """
    Retry predicate for the Telegram POST: retry on connection drops,
    timeouts, and Telegram-side (5xx) errors, but NOT on 4xx client
    errors -- an invalid bot token or chat ID fails identically on every
    attempt, so retrying it only delays the failure log.
    """
    if isinstance(exception, requests.exceptions.HTTPError):
        response = exception.response
        return response is not None and response.status_code >= 500
    return isinstance(exception, (requests.exceptions.ConnectionError, requests.exceptions.Timeout))


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception(_is_retryable_telegram_error),
    reraise=True,
)
def _post_to_telegram(bot_token: str, chat_id: str, text: str) -> None:
    """
    Sends a single message to a Telegram chat via the Bot API's
    sendMessage endpoint. Wrapped with tenacity retries (see
    _is_retryable_telegram_error) so a transient network blip or a
    momentary Telegram outage doesn't cost a MATCH alert.
    """
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }
    response = requests.post(url, json=payload, timeout=TELEGRAM_TIMEOUT_SECONDS)
    response.raise_for_status()


class JobLogger:
    """
    Handles appending structured job screening results to a persistent CSV
    log and updating a Markdown dashboard within the data/ directory, plus
    firing MATCH notifications (desktop toast + optional Telegram mobile
    push). Contains no AI, routing, or email logic.
    """

    def __init__(self):
        """
        Initializes the JobLogger, ensures the data directory exists,
        prepares the CSV and Markdown files with standard headers if they
        are missing, and loads Telegram credentials (if configured) for
        mobile push alerts.
        """
        self.data_dir = PROJECT_ROOT / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.csv_path = self.data_dir / "job_logs.csv"
        self.md_path = self.data_dir / "dashboard.md"
        self._initialize_files()

        # Telegram is optional: if these aren't set in .env, mobile alerts
        # are silently skipped and only the desktop toast fires. Unlike
        # fetcher.py, a missing .env here is NOT fatal.
        load_dotenv(dotenv_path=PROJECT_ROOT / ".env")
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")

    def _initialize_files(self) -> None:
        """
        Creates the CSV and Markdown files with structural headers if they
        do not exist.
        """
        if not self.csv_path.exists():
            with open(self.csv_path, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Timestamp", "Platform", "Role Title", "Status",
                    "Angola Eligible", "Match Percentage", "Reason"
                ])
            logger.info(f"Initialized new CSV log at {self.csv_path}")

        if not self.md_path.exists():
            with open(self.md_path, mode="w", encoding="utf-8") as f:
                f.write("# Job Scout Agent Dashboard\n\n")
                f.write("| Date | Platform | Role | Status | Angola Eligible | Match % |\n")
                f.write("|---|---|---|---|---|---|\n")
            logger.info(f"Initialized new Markdown dashboard at {self.md_path}")

    def _send_telegram_alert(self, role_title: str, platform: str, match_percentage, reason: str) -> None:
        """
        Sends a MATCH alert to the user's Telegram chat via the Bot API.

        Fully isolated from the CSV/Markdown write path above: this only
        runs after those writes have already completed, and it has its own
        try/except so a Telegram outage, misconfiguration, or rate limit
        can never affect logging to disk. Currently fires on MATCH only,
        mirroring the existing desktop toast -- if JUNK/ERROR alerts are
        wanted on mobile too, move the call in log_result() outside the
        `if status == "MATCH"` gate.
        """
        if not self.telegram_bot_token or not self.telegram_chat_id:
            logger.debug(
                "Telegram not configured (missing TELEGRAM_BOT_TOKEN or "
                "TELEGRAM_CHAT_ID); skipping mobile alert."
            )
            return

        message = (
            "*Job Scout - MATCH FOUND*\n"
            f"Role: {role_title}\n"
            f"Platform: {platform}\n"
            f"Match: {match_percentage}%\n"
            f"Reason: {reason}"
        )

        try:
            _post_to_telegram(self.telegram_bot_token, self.telegram_chat_id, message)
            logger.info("Telegram alert sent successfully.")
        except requests.exceptions.HTTPError as t_err:
            # Deliberately avoid logging str(t_err) -- the underlying
            # requests exception embeds the full request URL, which
            # contains the bot token. Log only the status code.
            status = t_err.response.status_code if t_err.response is not None else "unknown"
            logger.warning(
                f"Telegram alert failed after retries: HTTP {status} "
                "(check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)"
            )
        except Exception as t_err:
            logger.warning(f"Telegram alert failed after retries: {type(t_err).__name__}")

    def log_result(self, result: dict) -> None:
        """
        Appends a single structured screening result to both the CSV file
        and the Markdown dashboard. Triggers a native desktop toast alert
        and, if configured, a Telegram mobile push on system matches.

        Args:
            result (dict): The parsed JSON dictionary from the GeminiBrain
            module.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        platform = result.get("platform", "UNKNOWN")
        role_title = result.get("role_title", "UNKNOWN")
        status = result.get("status", "ERROR")
        angola_eligible = result.get("angola_eligible", False)
        match_percentage = result.get("match_percentage", 0)
        reason = result.get("reason", "No reason provided")

        # Convert boolean eligibility to clean plain text for Excel-safe CSV encoding
        csv_angola_str = "YES" if angola_eligible else "NO"

        # Append data to CSV (Strictly clean text data, no emoji rendering)
        try:
            with open(self.csv_path, mode="a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    timestamp, platform, role_title, status,
                    csv_angola_str, match_percentage, reason
                ])
        except Exception as e:
            logger.error(f"Failed to write to CSV: {e}")

        # Construct visually expressive formatting for the Markdown Dashboard only
        status_emoji = "✅ MATCH" if status == "MATCH" else "❌ JUNK" if status == "JUNK" else "⚠️ ERROR"
        md_angola_str = "✅ YES" if angola_eligible else "🚫 NO"
        md_line = (
            f"| {timestamp} | {platform} | {role_title} | "
            f"{status_emoji} | {md_angola_str} | {match_percentage}% |\n"
        )

        # Append data to Markdown Dashboard
        try:
            with open(self.md_path, mode="a", encoding="utf-8") as f:
                f.write(md_line)
        except Exception as e:
            logger.error(f"Failed to write to Markdown dashboard: {e}")

        # Real-time notification block for verified opportunities
        if status == "MATCH":
            try:
                notification.notify(
                    title="Job Scout - MATCH FOUND",
                    message=f"{role_title} @ {platform} ({match_percentage}%)",
                    app_name="Job Scout Agent",
                    timeout=10
                )
            except Exception as n_err:
                # Fault isolation: keep pipeline operational if Windows graphics engine is busy
                logger.warning(f"Desktop notification failed to fire: {n_err}")

            # Mobile push via Telegram -- isolated from the desktop toast
            # above; a failure here never blocks, and is never blocked by,
            # the notification call above.
            self._send_telegram_alert(role_title, platform, match_percentage, reason)


if __name__ == "__main__":
    # Standalone testing entry point to verify file creation and data appending logic.
    try:
        logger.info("Testing JobLogger initialization...")
        test_logger = JobLogger()
        test_payload = {
            "platform": "Test Platform",
            "role_title": "AI QA Tester",
            "status": "MATCH",
            "angola_eligible": True,
            "reason": "Test reason verified.",
            "match_percentage": 99
        }
        logger.info("Injecting test payload...")
        test_logger.log_result(test_payload)
        logger.info("Test complete. Check data/ directory for updates.")
    except Exception as ex:
        logger.error(f"Logger test execution failed: {ex}")