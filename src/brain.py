import os
import json
import logging
import re
import datetime
from pathlib import Path
import google.genai as genai
from google.genai import types, errors

PROJECT_ROOT = Path(__file__).resolve().parent.parent
logger = logging.getLogger(__name__)

class GeminiBrain:
    """
    AI-powered evaluation engine that screens raw email text against a
    deterministic candidate persona and eligibility criteria via Gemini 2.5 Flash.
    Uses the google-genai SDK (v2+).
    
    v1.1 Features: Added single-call Gap Analysis & Interview Prep Markdown Generation.
    """
    def __init__(self):
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=PROJECT_ROOT / ".env")
        
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Critical Configuration Error: Neither GEMINI_API_KEY nor "
                "GOOGLE_API_KEY is defined in the environment."
            )
        
        self.prompt_path = PROJECT_ROOT / "config" / "system_prompt.txt"
        if not self.prompt_path.exists():
            raise RuntimeError(f"Critical System Error: System prompt missing at {self.prompt_path}")
        
        self.system_instruction = self._load_system_prompt()
        self._client = genai.Client(api_key=api_key)
        
        # THE FIX: Explicit API-level schema enforcement
        # v1.1 UPDATE: Added Gap Analysis and Interview Prep arrays to single-call schema
        self.response_schema = types.Schema(
            type=types.Type.OBJECT,
            properties={
                "platform": types.Schema(type=types.Type.STRING),
                "role_title": types.Schema(type=types.Type.STRING),
                "status": types.Schema(type=types.Type.STRING),
                "angola_eligible": types.Schema(type=types.Type.BOOLEAN),
                "reason": types.Schema(type=types.Type.STRING),
                "match_percentage": types.Schema(type=types.Type.INTEGER),
                
                # New fields for v1.1 Blueprint
                "requirements_list": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING)
                ),
                "gap_analysis": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING)
                ),
                "interview_questions": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "question": types.Schema(type=types.Type.STRING),
                            "suggested_answer": types.Schema(type=types.Type.STRING)
                        },
                        required=["question", "suggested_answer"]
                    )
                )
            },
            required=[
                "platform", "role_title", "status", "angola_eligible", "reason", "match_percentage",
                "requirements_list", "gap_analysis", "interview_questions"
            ]
        )

        self._config = types.GenerateContentConfig(
            system_instruction=self.system_instruction,
            temperature=0.1,
            response_mime_type="application/json",
            response_schema=self.response_schema,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
        logger.info("GeminiBrain evaluation subsystem successfully initialized.")

    def _load_system_prompt(self) -> str:
        try:
            with open(self.prompt_path, "r", encoding="utf-8") as f:
                base_prompt = f.read().strip()
                
            # Dynamically inject the v1.1 requirement instructions to guarantee they are followed
            # without requiring the user to manually edit their existing text file.
            v1_1_instructions = """
            
            ADDITIONAL OUTPUT REQUIREMENTS (v1.1 Update):
            In addition to your standard screening, you MUST output three new fields:
            1. "requirements_list": Extract a list of the core requirements directly from the job description.
            2. "gap_analysis": A list of genuine gaps between the job's stated requirements and the candidate's profile. If no meaningful gaps exist, return an empty list. Do NOT fabricate weaknesses.
            3. "interview_questions": Exactly 3 objects, each containing a specific "question" for this role/company, and a "suggested_answer" that explicitly references the candidate's actual profile content to answer it.
            """
            return base_prompt + v1_1_instructions
            
        except Exception as e:
            raise IOError(f"Failed to read system prompt: {e}")

    def _write_interview_prep(self, result: dict):
        """
        Safely writes the derived interview prep and gap analysis to a markdown file.
        Fails silently on errors so as not to interrupt the core pipeline execution.
        """
        # Blueprint constraints: Only write files for confirmed matches
        status = result.get("status", "")
        if status not in ["MATCH", "Angola Eligible"]:
            return
            
        reqs = result.get("requirements_list", [])
        gaps = result.get("gap_analysis", [])
        questions = result.get("interview_questions", [])
        
        # If API omitted the new arrays for some reason, abort file creation cleanly
        if not isinstance(questions, list) or len(questions) == 0:
            logger.warning("Gemini matched job but omitted valid interview prep arrays. Skipping markdown generation.")
            return

        company = result.get("platform", "Unknown Company")
        role = result.get("role_title", "Target Role")
        
        # Sanitize strings to create safe Windows filenames
        safe_company = re.sub(r'(?u)[^-\w.]', '', company.strip().replace(' ', '_'))
        safe_role = re.sub(r'(?u)[^-\w.]', '', role.strip().replace(' ', '_'))
        date_str = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        
        out_dir = PROJECT_ROOT / "interview_prep"
        out_dir.mkdir(exist_ok=True)
        
        filepath = out_dir / f"{safe_company}_{safe_role}_{date_str}.md"
        
        # Build the markdown content
        md_lines = [
            f"# Interview Prep: {role} @ {company}",
            f"**Generated:** {datetime.datetime.now().strftime('%b %d, %Y - %H:%M')}\n",
            "## 📋 Core Job Requirements"
        ]
        
        if reqs:
            for req in reqs:
                md_lines.append(f"- {req}")
        else:
            md_lines.append("- *No explicit requirements extracted.*")
            
        md_lines.extend(["\n## 🔍 Strategic Gap Analysis"])
        if gaps:
            for gap in gaps:
                md_lines.append(f"- ⚠️ {gap}")
        else:
            md_lines.append("- ✅ *No significant gaps identified between your profile and the requirements.*")
            
        md_lines.extend(["\n## 🎙️ Tailored Interview Questions"])
        for idx, q in enumerate(questions, 1):
            q_text = q.get("question", "Question missing")
            a_text = q.get("suggested_answer", "Suggested answer missing")
            md_lines.append(f"### Q{idx}: {q_text}")
            md_lines.append(f"**Suggested Strategy:**\n{a_text}\n")
            
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("\n".join(md_lines))
            print(f"   📘 Interview Prep: Generated tailored study guide -> {filepath.name}")
        except Exception as e:
            logger.error(f"Failed to write interview prep file: {e}")

    def screen_email(self, email_body: str) -> dict:
        if not email_body or not email_body.strip():
            logger.warning("Empty email body passed to GeminiBrain. Skipping.")
            return self._error_fallback("Empty or invalid payload.")
        
        try:
            response = self._client.models.generate_content(
                model="gemini-2.5-flash",
                contents=email_body,
                config=self._config,
            )
            
            result_dict = None
            
            # SDK auto-parsing check
            if response.parsed is not None:
                if isinstance(response.parsed, dict):
                    result_dict = response.parsed
                # Handles Pydantic fallback if SDK maps to objects
                elif hasattr(response.parsed, "model_dump"):
                    result_dict = response.parsed.model_dump()
            elif response.text:
                result_dict = json.loads(response.text)
                
            if result_dict:
                # Trigger the async-style markdown writer before returning
                self._write_interview_prep(result_dict)
                return result_dict
            
            logger.error("Gemini returned empty response.")
            return self._error_fallback("API returned an empty response.")
            
        except errors.ClientError as api_err:
            logger.error(f"Gemini client error (4xx): {api_err}")
            return self._error_fallback(f"Gemini ClientError: {api_err}")
        except errors.ServerError as api_err:
            logger.error(f"Gemini server error (5xx): {api_err}")
            return self._error_fallback(f"Gemini ServerError: {api_err}")
        except json.JSONDecodeError as json_err:
            logger.error(f"JSON decode failed on response.text fallback: {json_err}")
            return self._error_fallback("Model output failed JSON parsing.")
        except Exception as gen_err:
            logger.error(f"Unexpected screening exception: {gen_err}")
            return self._error_fallback(f"Internal exception: {gen_err}")

    def _error_fallback(self, message: str) -> dict:
        return {
            "platform": "UNKNOWN",
            "role_title": "UNKNOWN",
            "status": "ERROR",
            "angola_eligible": False,
            "reason": f"Fallback triggered: {message}",
            "match_percentage": 0,
            "requirements_list": [],
            "gap_analysis": [],
            "interview_questions": []
        }