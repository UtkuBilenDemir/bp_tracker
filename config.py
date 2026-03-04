import os
from dotenv import load_dotenv

load_dotenv()

# --- Paths ---
WATCH_FOLDER = "watch_folder/"
CSV_PATH = "data/readings.csv"
ERROR_LOG_PATH = "data/errors.log"
HTPASSWD_PATH = "data/.htpasswd"

# --- API ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
VISION_MODEL = "claude-opus-4-6"

# --- Current dose (update when titration changes) ---
CURRENT_DOSE_MG = 5

# --- Baseline (from medical letter) ---
BASELINE_SYSTOLIC = 111
BASELINE_DIASTOLIC = 63
BASELINE_HR = 60

# --- BP threshold zones ---
ELEVATED_SYSTOLIC = 130
ELEVATED_DIASTOLIC = 85
HIGH_SYSTOLIC = 140
HIGH_DIASTOLIC = 90

# --- CSV columns ---
CSV_COLUMNS = [
    "timestamp",
    "systolic",
    "diastolic",
    "heart_rate",
    "dose_taken",
    "dose_mg",
    "dose_time",
    "photo_filename",
    "ai_comment",
]
