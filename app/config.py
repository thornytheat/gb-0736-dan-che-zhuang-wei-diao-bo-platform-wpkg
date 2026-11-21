from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / 'sample_data'
RULE_VERSION = '1.0.0'
ZONE = 'Asia/Shanghai'
MAX_INPUT_BYTES = 256 * 1024
MAX_RECORDS = 2000
MAX_LEGS = 20
LATE_SECONDS = 300
SLOT_MINUTES = 15
