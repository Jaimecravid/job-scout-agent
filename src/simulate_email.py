import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from dotenv import load_dotenv

# Establish project root for secure, absolute path resolution on Windows
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Configure isolated logging for this module
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(ch)

def inject_test_payload() -> None:
    """
    Constructs and dispatches a mocked 'Job Alert' email to the user's own 
    inbox via Gmail SMTP. This simulates an incoming external job payload 
    to trigger the End-to-End pipeline validation.
    """
    load_dotenv(dotenv_path=PROJECT_ROOT / ".env")
    
    email_user = os.getenv("EMAIL_USER")
    email_password = os.getenv("EMAIL_APP_PASSWORD")
    
    if not email_user or not email_password:
        raise RuntimeError(
            "Critical: EMAIL_USER or EMAIL_APP_PASSWORD is missing from .env file."
        )
        
    msg = MIMEMultipart()
    msg['From'] = email_user
    msg['To'] = email_user
    msg['Subject'] = "Job Alert: AI Data Annotation Specialist (PT-PT)"
    
    # Payload includes HTML structure, CSS, tracking tags, and specific 
    # keywords designed to trigger positive Angola eligibility and Match status.
    html_payload = """
    <html>
        <body>
            <style> body { font-family: sans-serif; } </style>
            <h2>Job Alert: AI Data Annotation Specialist (Native Portuguese)</h2>
            <p><strong>Company:</strong> Global LLM Trainers</p>
            <p><strong>Location:</strong> Remote (Worldwide / International contractors eligible)</p>
            <p><strong>Role Description:</strong></p>
            <p>Seeking native European Portuguese (PT-PT) speakers for AI model behavior tuning 
            and translation QA. This is a remote contractor position open anywhere globally. 
            No physical US/EU residence is required. Ideal for prompt engineering professionals.</p>
            <br>
            <footer>
                <p><em>Click <a href="#">here</a> to apply or unsubscribe.</em></p>
                <img src="http://tracker.pixel/pixel.gif" style="display:none;" />
                <script>console.log("Tracking active");</script>
            </footer>
        </body>
    </html>
    """
    msg.attach(MIMEText(html_payload, 'html'))
    
    logger.info(f"Connecting to smtp.gmail.com to dispatch test payload to {email_user}...")
    
    try:
        # Utilizing standard SMTP TLS on port 587
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(email_user, email_password)
            server.send_message(msg)
        logger.info("Simulation payload injected successfully into the INBOX.")
        logger.info("Proceed to run `python src/main.py` to test end-to-end extraction and evaluation.")
    except Exception as e:
        logger.error(f"Failed to inject simulation payload: {e}")

if __name__ == "__main__":
    inject_test_payload()