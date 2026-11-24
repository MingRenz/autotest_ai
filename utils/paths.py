from pathlib import Path

# 所有路径集中在这里，避免用例层散落相对路径。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_FILE = DATA_DIR / "config" / "config.yaml"
TESTDATA_DIR = DATA_DIR / "testdata"
LOG_DIR = PROJECT_ROOT / "logs"
REPORTS_DIR = PROJECT_ROOT / "reports"
ALLURE_RESULTS_DIR = REPORTS_DIR / "allure-results"
ALLURE_REPORT_DIR = REPORTS_DIR / "allure-report"

for directory in (LOG_DIR, ALLURE_RESULTS_DIR, ALLURE_REPORT_DIR):
    directory.mkdir(parents=True, exist_ok=True)
