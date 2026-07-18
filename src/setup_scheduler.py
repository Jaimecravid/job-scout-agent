import logging
import subprocess
from pathlib import Path

# Establish project root for secure, absolute path resolution on Windows
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Configure isolated logging for this module
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(ch)


def _find_pythonw() -> str:
    """
    Locates the pythonw.exe executable that ships alongside every standard
    CPython installation on Windows. Using pythonw.exe (rather than
    python.exe) is what suppresses the console window when the task fires
    silently in the background via Task Scheduler -- no .vbs wrapper needed.

    Resolution order:
      1. A pythonw.exe sitting next to the currently-running python.exe
         (the case for both standalone installs and .venv environments).
      2. The string "pythonw" as a bare fallback, which works when Python's
         Scripts directory is on PATH (rare but possible on some systems).

    Returns:
        str: Absolute path to pythonw.exe, or "pythonw" as a PATH fallback.
    """
    import sys
    python_exe = Path(sys.executable)
    # In a venv: <venv>/Scripts/python.exe  -> <venv>/Scripts/pythonw.exe
    # In base:   C:/Python313/python.exe    -> C:/Python313/pythonw.exe
    candidate = python_exe.parent / "pythonw.exe"
    if candidate.exists():
        logger.info(f"Found pythonw.exe at: {candidate}")
        return str(candidate)

    logger.warning(
        "pythonw.exe not found next to current interpreter; "
        "falling back to 'pythonw' on PATH."
    )
    return "pythonw"


def register_scheduled_task() -> None:
    """
    Registers (or overwrites) a Windows Task Scheduler entry that runs the
    Job Scout Agent silently, once per hour, using pythonw.exe so no
    console window ever appears on the user's screen.

    The task action is:
        pythonw.exe  <project_root>/src/main.py
    with the working directory set to <project_root>, matching the
    PROJECT_ROOT resolution used across all modules.

    Raises:
        subprocess.CalledProcessError: re-raised if schtasks.exe itself
        fails (e.g. insufficient privileges to write to Task Scheduler).
    """
    task_name = "JobScoutAgent_Hourly"
    pythonw = _find_pythonw()
    main_script = str(PROJECT_ROOT / "src" / "main.py")

    # /TR   - Task Run: the full command Task Scheduler will execute
    # /SC   - Schedule type (HOURLY)
    # /MO   - Modifier: every 1 hour
    # /SD   - Start Date: today (avoids schtasks defaulting to a past date)
    # /ST   - Start Time: on the next whole hour from now
    # /F    - Force overwrite if the task already exists
    # /RL HIGHEST - Run with highest available privileges on the account
    import datetime
    now = datetime.datetime.now()
    start_time = (now + datetime.timedelta(hours=1)).strftime("%H:00")

    command = [
        "schtasks", "/Create",
        "/TN", task_name,
        "/TR", f'"{pythonw}" "{main_script}"',
        "/SC", "HOURLY",
        "/MO", "1",
        "/SD", now.strftime("%m/%d/%Y"),
        "/ST", start_time,
        "/F",
    ]

    logger.info(f"Registering Task Scheduler entry '{task_name}'...")
    logger.info(f"  Runner  : {pythonw}")
    logger.info(f"  Script  : {main_script}")
    logger.info(f"  Work dir: {PROJECT_ROOT}")

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            # Set the working directory so relative .env / data/ paths
            # resolve correctly at task execution time
            cwd=str(PROJECT_ROOT),
        )
        logger.info(f"Task registered. Windows response: {result.stdout.strip()}")
    except subprocess.CalledProcessError as e:
        logger.error(f"schtasks registration failed: {e.stderr.strip()}")
        raise


if __name__ == "__main__":
    """
    Standalone entry point. Run once from the project root:
        python src/setup_scheduler.py
    """
    try:
        logger.info("Configuring background automation...")
        register_scheduled_task()
        logger.info("Done. The agent will run silently every hour.")
    except Exception as ex:
        logger.error(f"Setup failed: {ex}")