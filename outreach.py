import os
import datetime
import re
import urllib.request
import urllib.parse
from google import genai

# Initialize the Gemini Client
client = genai.Client()

# Automatically resolve the base directory of this script (the project root)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def load_master_context():
    """Reads the Master_Context.txt file from the local directory robustly."""
    context_path = os.path.join(BASE_DIR, "Master_Context.txt")
    try:
        with open(context_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        print(f"Error: Master_Context.txt not found at {context_path}")
        return ""

def sanitize_filename(name):
    """Removes invalid characters from job titles/companies for safe file saving."""
    return re.sub(r'(?u)[^-\w.]', '', str(name).strip().replace(' ', '_'))

def send_draft_to_telegram(token, chat_id, job_title, company_name, draft_text):
    """Sends the generated outreach draft safely to your Telegram bot."""
    message_header = (
        f"✉️ OUTREACH DRAFT GENERATED ✉\n"
        f"Role: {job_title}\n"
        f"Company: {company_name}\n"
        f"-----------------------------------------\n\n"
    )
    full_message = message_header + draft_text
    
    if len(full_message) > 4000:
        full_message = full_message[:4000] + "\n\n...[Truncated due to Telegram limit]..."
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": full_message
    }).encode("utf-8")
    
    try:
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req) as response:
            print("   📤 Telegram Delivery: Draft successfully sent to your phone!")
            return True
    except Exception as e:
        print(f"   ⚠️ Telegram Delivery: Failed to send draft to phone ({e})")
        return False

def generate_outreach_draft(job_title, company_name, job_description, source_email_id="UNKNOWN_UID", job_id="UNKNOWN_JOB_ID"):
    """
    Takes matched job details, merges them with Master_Context.txt, 
    generates a pitch, saves it locally with database metadata, and handles alerts.
    """
    context = load_master_context()
    if not context:
        return None

    prompt = f"""
    You are an expert technical operator writing a direct, professional message on behalf of the applicant defined in the context below.
    
    APPLICANT CONTEXT:
    {context}
    
    JOB DETAILS:
    Role: {job_title}
    Company: {company_name}
    Job Description: {job_description}
    
    TASK:
    Write a raw, punchy, no-nonsense outreach message (under 200 words) for this specific role. 
    1. Write like an engineer sending a direct message to another engineering lead or hiring manager. 
    2. Do NOT use generic corporate greetings (no "To Whom It May Concern", "Dear Sir/Madam", or "Dear Hiring Team"). Open directly or with a simple, clean greeting like "Hi team," or "Hi [Hiring Manager],".
    3. Hook the reader immediately with a relevant technical win (e.g., your Netlify MCP server debugging or building your own automated Python agent) to prove your technical capabilities.
    4. Briefly state how your native European Portuguese (PT-PT) and C2 English translation/multi-turn conversational evaluation skills apply directly to the job needs.
    5. Keep it highly concise, execution-focused, and free of typical AI corporate fluff. Absolutely avoid phrases like "My immediate value proposition lies in...", "Your requirement aligns directly...", "I am pleased to apply", "meticulously", or "proven track record".
    6. Sign off simply as Jaime Cravid.
    """

    try:
        print(f"Generating outreach draft for: {job_title} at {company_name}...")
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        draft_text = response.text
        
        # Save output in the project root's outreach_drafts folder
        output_dir = os.path.join(BASE_DIR, "outreach_drafts")
        os.makedirs(output_dir, exist_ok=True)
        
        # Create a clean filename
        date_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_company = sanitize_filename(company_name)
        filename = os.path.join(output_dir, f"{safe_company}_{date_str}.txt")
        
        # Save the draft locally with structured metadata comments at the top
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"ROLE: {job_title}\n")
            f.write(f"COMPANY: {company_name}\n")
            f.write(f"EMAIL_ID: {source_email_id}\n")
            f.write(f"JOB_ID: {job_id}\n")
            f.write("="*40 + "\n\n")
            f.write(draft_text)
            
        print(f"Draft successfully saved to: {filename}")
        
        # --- TRIGGER TELEGRAM DELIVERY ---
        telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        
        if telegram_token and telegram_chat_id:
            send_draft_to_telegram(
                token=telegram_token, 
                chat_id=telegram_chat_id, 
                job_title=job_title, 
                company_name=company_name, 
                draft_text=draft_text
            )
            
        return filename
        
    except Exception as e:
        print(f"Error generating outreach draft: {e}")
        return None

# --- FOR LOCAL TESTING ONLY ---
if __name__ == "__main__":
    test_title = "AI Model Evaluator (Portuguese & Technical)"
    test_company = "Outlier AI"
    test_description = "We need bilingual evaluators to assess coding models and multi-turn conversational AI. Must understand prompt logic and complex system reasoning."
    
    generate_outreach_draft(test_title, test_company, test_description)