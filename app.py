"""
E-Insta Feedback Auto-Bot — FINAL VERSION
Manual captcha solve mode only.

PDF structure (confirmed from Copy_of_Feedback_10.pdf):
  Each form is one page separated by \f (form-feed).
  Fields per page:
    Form No.            | Centre Code        (same line)
    Name                | Feedback ID        (same line)
    Cities              | Age                (same line)
    Actual Date and Timing
    Marital Status      | Education          (same line)
    Hobbies
    Instagram Benefits for Business
    What is your primary Job role ...?
    What type of marketing Task do you perform with instagram?
    How often do you use instagram for marketing purposes?
    How important is instagram for marketing activities?
    How did you hear about Instagram?

  Fields NOT in the PDF: Gender, State, Email, EVC Code, Hashtag
  (these should come from the dashboard config if the form needs them)
"""

import os
import re
import sys
import time
import stat
import shutil
import platform
import subprocess
import threading
import pdfplumber
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options


# ═══════════════════════════════════════════════
#  CROSS-PLATFORM CHROME LAUNCHER
#  Handles: Mac (Intel + ARM), Windows, Linux
#  Error -9 fix: unquarantine on Mac, correct
#  driver/browser version matching via selenium-manager
# ═══════════════════════════════════════════════

IS_MAC     = platform.system() == 'Darwin'
IS_WIN     = platform.system() == 'Windows'
IS_LINUX   = platform.system() == 'Linux'
IS_ARM_MAC = IS_MAC and platform.machine() == 'arm64'


def _fix_mac_quarantine(path):
    """Remove macOS quarantine flag that causes -9 kills."""
    if IS_MAC and path and os.path.exists(path):
        try:
            subprocess.run(
                ['xattr', '-d', 'com.apple.quarantine', path],
                capture_output=True
            )
        except Exception:
            pass


def _make_executable(path):
    if path and os.path.isfile(path):
        try:
            os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        except Exception:
            pass


def _is_real_binary(path):
    """Return True if the file looks like an executable binary (not a text/notice file)."""
    if not path or not os.path.isfile(path):
        return False
    try:
        with open(path, 'rb') as fh:
            magic = fh.read(4)
        # ELF (Linux), Mach-O fat/64/32 (Mac), PE (Windows)
        return magic[:2] in (b'\x7fE', b'MZ') or magic[:4] in (
            b'\xcf\xfa\xed\xfe',  # Mach-O 64-bit LE
            b'\xce\xfa\xed\xfe',  # Mach-O 32-bit LE
            b'\xca\xfe\xba\xbe',  # Mach-O fat binary
            b'\xbe\xba\xfe\xca',
        )
    except Exception:
        return False


def _find_driver_in_dir(directory):
    """Walk a directory and return the first real chromedriver binary found."""
    names = ('chromedriver.exe', 'chromedriver')
    for root, dirs, files in os.walk(directory):
        for name in names:
            if name in files:
                full = os.path.join(root, name)
                if _is_real_binary(full):
                    return full
    return None


def get_chrome_driver():
    """
    Return a ready-to-use (path-fixed, unquarantined) chromedriver path.
    Strategy order:
      1. selenium-manager (bundled with selenium ≥ 4.6) — handles version matching automatically
      2. System PATH chromedriver
      3. webdriver-manager cache walk
      4. webdriver-manager fresh download
    Raises RuntimeError with install instructions if nothing works.
    """

    # ── 1. selenium-manager (best: auto-matches Chrome version) ──────────
    try:
        from selenium.webdriver.chrome.service import Service as ChromeService
        # Let selenium pick driver automatically (selenium ≥ 4.6.0)
        # We do a dry-run probe here; actual launch happens in create_driver()
        sm_result = subprocess.run(
            [sys.executable, '-c',
             'from selenium.webdriver.chrome.service import Service; '
             'from selenium import webdriver; '
             'import selenium.webdriver.common.selenium_manager as sm; '
             'b = sm.SeleniumManager(); '
             'print(b.driver_location(webdriver.ChromeOptions()))'],
            capture_output=True, text=True, timeout=30
        )
        path = sm_result.stdout.strip().splitlines()[-1] if sm_result.returncode == 0 else ''
        if path and _is_real_binary(path):
            _fix_mac_quarantine(path)
            _make_executable(path)
            add_log(f"[Driver] selenium-manager: {path}", 'info')
            return path
    except Exception:
        pass

    # ── 2. System PATH ────────────────────────────────────────────────────
    system_driver = shutil.which('chromedriver')
    if system_driver and _is_real_binary(system_driver):
        _fix_mac_quarantine(system_driver)
        add_log(f"[Driver] System PATH: {system_driver}", 'info')
        return system_driver

    # ── 3. Walk existing webdriver-manager cache ──────────────────────────
    for cache_root in [
        os.path.expanduser('~/.wdm/drivers/chromedriver'),
        os.path.expanduser('~/.wdm'),
    ]:
        if os.path.isdir(cache_root):
            found = _find_driver_in_dir(cache_root)
            if found:
                _fix_mac_quarantine(found)
                _make_executable(found)
                add_log(f"[Driver] wdm cache: {found}", 'info')
                return found

    # ── 4. webdriver-manager fresh download ───────────────────────────────
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        raw = ChromeDriverManager().install()
        raw_dir = os.path.dirname(raw)
        # raw might point to a THIRD_PARTY_NOTICES text file; walk siblings
        found = _find_driver_in_dir(raw_dir) or _find_driver_in_dir(os.path.dirname(raw_dir))
        if not found and _is_real_binary(raw):
            found = raw
        if found:
            _fix_mac_quarantine(found)
            _make_executable(found)
            add_log(f"[Driver] wdm download: {found}", 'info')
            return found
    except Exception as e:
        add_log(f"[Driver] webdriver-manager failed: {e}", 'warning')

    # ── Nothing worked ────────────────────────────────────────────────────
    msg = (
        "ChromeDriver not found or kept getting killed.\n"
        "Fix for your platform:\n"
        "  Mac:     brew install chromedriver && xattr -d com.apple.quarantine $(which chromedriver)\n"
        "  Windows: pip install webdriver-manager   (auto-handled)\n"
        "  Linux:   sudo apt install chromium-driver\n"
        "Then restart the bot."
    )
    raise RuntimeError(msg)


def create_driver():
    """
    Create and return a Chrome WebDriver instance.
    Applies all flags needed to prevent -9 kills on Mac ARM,
    and works on Windows/Linux without changes.
    """
    opts = Options()

    # ── Stability flags (fix -9 / crashes on all platforms) ──────────────
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--disable-gpu')                   # safe on all platforms
    opts.add_argument('--disable-software-rasterizer')
    opts.add_argument('--disable-extensions')
    opts.add_argument('--disable-background-networking')
    opts.add_argument('--disable-default-apps')
    opts.add_argument('--disable-sync')
    opts.add_argument('--disable-translate')
    opts.add_argument('--metrics-recording-only')
    opts.add_argument('--mute-audio')
    opts.add_argument('--no-first-run')
    opts.add_argument('--safebrowsing-disable-auto-update')
    opts.add_argument('--disable-features=VizDisplayCompositor')  # Mac ARM -9 fix

    # ── Mobile viewport (site is mobile-first) ───────────────────────────
    opts.add_argument('--window-size=390,844')
    opts.add_argument(
        '--user-agent=Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) '
        'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1'
    )

    # ── Mac ARM: point Chrome to the correct binary if Homebrew ──────────
    if IS_ARM_MAC:
        for chrome_path in [
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            '/Applications/Chromium.app/Contents/MacOS/Chromium',
        ]:
            if os.path.exists(chrome_path):
                opts.binary_location = chrome_path
                break

    # ── Windows: common install paths ────────────────────────────────────
    if IS_WIN:
        for chrome_path in [
            r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
            os.path.expanduser(r'~\AppData\Local\Google\Chrome\Application\chrome.exe'),
        ]:
            if os.path.exists(chrome_path):
                opts.binary_location = chrome_path
                break

    # ── Try selenium auto-driver first (no explicit driver path needed) ───
    try:
        driver = webdriver.Chrome(options=opts)
        add_log("✅ Chrome launched via selenium auto-manager", 'success')
        driver.implicitly_wait(5)
        return driver
    except Exception as e:
        add_log(f"⚠️  Auto-launch failed ({e}), trying explicit driver path...", 'warning')

    # ── Fall back to explicit driver path ─────────────────────────────────
    driver_path = get_chrome_driver()
    add_log(f"🔧 Using driver: {driver_path}", 'info')
    service = Service(executable_path=driver_path)
    driver = webdriver.Chrome(service=service, options=opts)
    add_log("✅ Chrome launched via explicit driver path", 'success')
    driver.implicitly_wait(5)
    return driver


# ═══════════════════════════════════════════════
#  FLASK APP + BOT STATE
# ═══════════════════════════════════════════════

app = Flask(__name__)
CORS(app)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024
os.makedirs('uploads', exist_ok=True)
os.makedirs('templates', exist_ok=True)

bot_state = {
    'running': False,
    'records': [],
    'current_index': 0,
    'success_count': 0,
    'fail_count': 0,
    'logs': [],
    'config': {
        'email': '',
        'password': '',
        'delay': 3,
        'max_submissions': 3000,
        'evc_code': '',
        'captcha_wait_seconds': 120
    },
    'stop_requested': False,
    'waiting_for_captcha': False,
    'captcha_confirmed': False
}


def add_log(message, log_type='info'):
    timestamp = time.strftime('%H:%M:%S')
    bot_state['logs'].append({'time': timestamp, 'message': message, 'type': log_type})
    if len(bot_state['logs']) > 500:
        bot_state['logs'] = bot_state['logs'][-500:]
    print(f"[{timestamp}] {message}")


# ═══════════════════════════════════════════════
#  PDF EXTRACTION  — matches Copy_of_Feedback_10.pdf exactly
# ═══════════════════════════════════════════════

# All field label patterns in the order they appear on each page.
# Used to build a "stop-before-next-label" lookahead for multi-line fields.
_MARKERS = [
    r'Form No\.',
    r'Centre Code',
    r'Name',
    r'Feedback ID',
    r'Cities',
    r'Age',
    r'Actual Date and Timing',
    r'Marital Status',
    r'Education',
    r'Hobbies',
    r'Instagram Benefits for Business',
    r'What is your primary Job role[^:\n?]*',
    r'What type of marketing Task[^:\n?]*',
    r'How often do you use instagram[^:\n?]*',
    r'How important is instagram[^:\n?]*',
    r'How did you hear about Instagram\?',
]

_STOP = r'(?=' + '|'.join(_MARKERS) + r')'


def _get(page, label_re):
    """
    Extract the value that follows `label_re:` on a page,
    stopping before the next known field label.
    Collapses internal newlines to spaces.
    """
    pat = r'(?:' + label_re + r')\s*\??\s*:\s*(.*?)(?=\n\s*(?:' + '|'.join(_MARKERS) + r')\s*:|\Z)'
    m = re.search(pat, page, re.DOTALL | re.IGNORECASE)
    if m:
        val = m.group(1).strip()
        return re.sub(r'\s*\n\s*', ' ', val).strip()
    return ''


def extract_records_from_pdf(pdf_path):
    """Parse PDF using pdfplumber (works on Railway, no external deps)."""
    add_log("📖 Reading PDF with pdfplumber...", 'info')
    records = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            add_log(f"📄 {len(pdf.pages)} pages found", 'info')
            
            for page_num, page in enumerate(pdf.pages):
                text = page.extract_text()
                
                if not text or 'Form No.' not in text:
                    continue
                
                # Extract fields using regex
                record = {
                    'form_no': _extract_field(text, r'Form No\.\s*:\s*(\d+)'),
                    'center_code': _extract_field(text, r'Centre Code\s*:\s*(\S+)'),
                    'name': _extract_field(text, r'Name\s*:\s*(.*?)(?=\s{2,}Feedback ID|\n)', True),
                    'feedback_id': _extract_field(text, r'Feedback ID\s*:\s*(\S+)'),
                    'city': _extract_field(text, r'Cities\s*:\s*(.*?)(?=\s{2,}Age\s*:|\n)', True),
                    'age': _extract_field(text, r'(?<!\w)Age\s*:\s*(\d+)'),
                    'marital_status': _extract_field(text, r'Marital Status\s*:\s*(\w+)'),
                    'education': _extract_field(text, r'Education\s*:\s*(.*?)(?=\s{2,}|\n)', True),
                    'hobbies': _extract_field(text, r'Hobbies\s*:\s*(.*?)(?=\n\s*(?:Form No\.|Centre Code|Name|Feedback ID|Cities|Age|Actual Date|Marital Status|Education|Hobbies|Instagram Benefits|What is your primary|What type of marketing|How often|How important|How did you hear)|\Z)', True),
                    'instagram_benefit': _extract_field(text, r'Instagram Benefits for Business\s*:\s*(.*?)(?=\n\s*(?:Form No\.|Centre Code|Name|Feedback ID|Cities|Age|Actual Date|Marital Status|Education|Hobbies|Instagram Benefits|What is your primary|What type of marketing|How often|How important|How did you hear)|\Z)', True),
                    'job_role': _extract_field(text, r'What is your primary Job role[^:\n?]*\s*:\s*(.*?)(?=\n\s*(?:Form No\.|Centre Code|Name|Feedback ID|Cities|Age|Actual Date|Marital Status|Education|Hobbies|Instagram Benefits|What is your primary|What type of marketing|How often|How important|How did you hear)|\Z)', True),
                    'marketing_task': _extract_field(text, r'What type of marketing Task[^:\n?]*\s*:\s*(.*?)(?=\n\s*(?:Form No\.|Centre Code|Name|Feedback ID|Cities|Age|Actual Date|Marital Status|Education|Hobbies|Instagram Benefits|What is your primary|What type of marketing|How often|How important|How did you hear)|\Z)', True),
                    'usage_frequency': _extract_field(text, r'How often do you use instagram[^:\n?]*\s*:\s*(.*?)(?=\n\s*(?:Form No\.|Centre Code|Name|Feedback ID|Cities|Age|Actual Date|Marital Status|Education|Hobbies|Instagram Benefits|What is your primary|What type of marketing|How often|How important|How did you hear)|\Z)', True),
                    'importance': _extract_field(text, r'How important is instagram[^:\n?]*\s*:\s*(.*?)(?=\n\s*(?:Form No\.|Centre Code|Name|Feedback ID|Cities|Age|Actual Date|Marital Status|Education|Hobbies|Instagram Benefits|What is your primary|What type of marketing|How often|How important|How did you hear)|\Z)', True),
                    'hear_about': _extract_field(text, r'How did you hear about Instagram\?\s*:\s*(.*?)(?=\n\s*(?:Form No\.|Centre Code|Name|Feedback ID|Cities|Age|Actual Date|Marital Status|Education|Hobbies|Instagram Benefits|What is your primary|What type of marketing|How often|How important|How did you hear)|\Z)', True),
                    'gender': '',
                    'state': '',
                    'email': '',
                    'evc_code': '',
                    'hashtag': '',
                }
                
                if record.get('name'):
                    records.append(record)
                    add_log(f"  ✓ Extracted: {record['name']} (Form {record['form_no']})", 'info')
        
        add_log(f"✅ Extracted {len(records)} records successfully", 'success')
        return records
        
    except Exception as e:
        add_log(f"❌ PDF extraction error: {str(e)}", 'error')
        import traceback
        add_log(traceback.format_exc(), 'error')
        return []

def _extract_field(text, pattern, multiline=False):
    """Helper to extract single field from text."""
    m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if m:
        val = m.group(1).strip()
        if multiline:
            val = re.sub(r'\s*\n\s*', ' ', val)
        return val
    return ''


# ═══════════════════════════════════════════════
#  SELENIUM HELPERS
# ═══════════════════════════════════════════════

def safe_fill(driver, css, value, wait=6):
    if not value:
        return False
    for sel in [s.strip() for s in css.split(',')]:
        try:
            el = WebDriverWait(driver, wait).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, sel))
            )
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            time.sleep(0.2)
            el.clear()
            el.send_keys(str(value))
            return True
        except Exception:
            continue
    add_log(f"⚠️  Could not fill: {css[:60]}", 'warning')
    return False


def safe_select(driver, css, value, wait=6):
    if not value:
        return False
    try:
        el = WebDriverWait(driver, wait).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, css))
        )
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        time.sleep(0.2)
        sel = Select(el)
        try:
            sel.select_by_visible_text(value)
            return True
        except Exception:
            pass
        for opt in sel.options:
            if value.lower() in opt.text.lower():
                sel.select_by_visible_text(opt.text)
                return True
        for opt in sel.options:
            if opt.get_attribute('value') not in ('', None):
                sel.select_by_value(opt.get_attribute('value'))
                return True
    except Exception as e:
        add_log(f"⚠️  Select failed [{css[:40]}]: {e}", 'warning')
    return False


def click_button(driver, xpath, wait=8, label='button'):
    try:
        btn = WebDriverWait(driver, wait).until(
            EC.element_to_be_clickable((By.XPATH, xpath))
        )
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
        time.sleep(0.4)
        btn.click()
        return True
    except Exception as e:
        add_log(f"⚠️  {label} not found: {e}", 'warning')
        return False


def click_next(driver):
    return click_button(
        driver,
        "//button[normalize-space()='Next' or contains(text(),'Next')]",
        label='Next button'
    )


# ═══════════════════════════════════════════════
#  CAPTCHA HANDLER  (manual only)
# ═══════════════════════════════════════════════

def wait_for_manual_captcha(driver, timeout):
    add_log(
        f"🔴 CAPTCHA — Solve 'I am human' in the browser, then click "
        f"'✅ I Solved the Captcha' in the dashboard. ({timeout}s timeout)",
        'warning'
    )
    bot_state['waiting_for_captcha'] = True
    bot_state['captcha_confirmed'] = False
    deadline = time.time() + timeout

    while time.time() < deadline:
        if bot_state['captcha_confirmed']:
            bot_state['waiting_for_captcha'] = False
            add_log("✅ Captcha confirmed — continuing submission", 'success')
            return True
        try:
            solved = driver.execute_script("""
                var r = document.querySelector('[name="h-captcha-response"]');
                return r && r.value && r.value.length > 20;
            """)
            if solved:
                bot_state['waiting_for_captcha'] = False
                add_log("✅ Captcha auto-detected as solved!", 'success')
                return True
        except Exception:
            pass
        time.sleep(2)

    bot_state['waiting_for_captcha'] = False
    add_log("❌ Captcha timeout — skipping this form", 'error')
    return False


# ═══════════════════════════════════════════════
#  FORM STEPS
# ═══════════════════════════════════════════════

def fill_step1(driver, record, cfg):
    """Step 1: Name | Center Code | Gender | E-Instagram Benefits | Feedback Id"""
    add_log("📝 Step 1 — Name, Center Code, Gender, Benefits, Feedback Id", 'info')

    safe_fill(driver,
        'input[placeholder*="name" i], input[name*="name" i]',
        record.get('name', ''))

    safe_fill(driver,
        'input[placeholder*="center code" i], input[name*="centerCode" i], '
        'input[name*="center_code" i]',
        record.get('center_code', ''))

    # Gender not in PDF — default to Male
    gender_val = record.get('gender') or 'Male'
    safe_select(driver, 'select', gender_val)

    safe_fill(driver,
        'input[placeholder*="e-instagram benif" i], '
        'textarea[placeholder*="e-instagram benif" i], '
        'input[name*="instagramBenefit" i], textarea[name*="instagramBenefit" i]',
        record.get('instagram_benefit', ''))

    feedback_id = record.get('feedback_id') or str(1000 + bot_state['current_index'])
    safe_fill(driver,
        'input[placeholder*="feedback id" i], input[name*="feedbackId" i], '
        'input[name*="feedback_id" i]',
        feedback_id)

    time.sleep(0.5)
    click_next(driver)
    time.sleep(2)


def fill_step2(driver, record):
    """Step 2: How important | City | Age | Hobbies | Primary job role"""
    add_log("📝 Step 2 — Importance, City, Age, Hobbies, Job Role", 'info')

    safe_fill(driver,
        'input[placeholder*="important" i], textarea[placeholder*="important" i]',
        record.get('importance', ''))

    safe_fill(driver,
        'input[placeholder*="city" i], input[name*="city" i]',
        record.get('city', ''))

    safe_fill(driver,
        'input[placeholder*="age" i], input[name*="age" i]',
        record.get('age', ''))

    safe_fill(driver,
        'input[placeholder*="hobbi" i], textarea[placeholder*="hobbi" i], '
        'input[name*="hobbie" i]',
        record.get('hobbies', ''))

    safe_fill(driver,
        'input[placeholder*="job role" i], textarea[placeholder*="job role" i], '
        'input[name*="jobRole" i]',
        record.get('job_role', ''))

    time.sleep(0.5)
    click_next(driver)
    time.sleep(2)


def fill_step3(driver, record):
    """Step 3: Marital Status | Email | Marketing tasks | Education | State"""
    add_log("📝 Step 3 — Marital, Email, Marketing, Education, State", 'info')

    marital_map = {
        'unmarried': 'Single', 'single': 'Single',
        'married':   'Married', 'divorced': 'Divorced', 'widowed': 'Widowed'
    }
    raw_marital = (record.get('marital_status') or 'Single').strip()
    marital_val = marital_map.get(raw_marital.lower(), raw_marital)
    safe_select(driver, 'select[name*="marital" i], select', marital_val)

    email_val = record.get('email') or f'user{1000 + bot_state["current_index"]}@gmail.com'
    safe_fill(driver,
        'input[placeholder*="email" i], input[name*="email" i], input[type="email"]',
        email_val)

    safe_fill(driver,
        'input[placeholder*="marketing task" i], '
        'textarea[placeholder*="marketing task" i], '
        'input[name*="marketingTask" i], textarea[name*="marketingTask" i]',
        record.get('marketing_task', ''))

    safe_fill(driver,
        'input[placeholder*="education" i], input[name*="education" i]',
        record.get('education', ''))

    # State not in PDF — use config value or leave blank
    state_val = record.get('state') or bot_state['config'].get('state', '')
    if state_val:
        safe_fill(driver,
            'input[placeholder*="state" i], input[name*="state" i]',
            state_val)

    time.sleep(0.5)
    click_next(driver)
    time.sleep(2)


def fill_step4(driver, record, cfg):
    """Step 4: How often | Hashtag | How did you hear | Evc Code → hCaptcha → Submit"""
    add_log("📝 Step 4 — Frequency, Hashtag, Heard, Evc Code, Captcha", 'info')

    safe_fill(driver,
        'input[placeholder*="how often" i], textarea[placeholder*="how often" i], '
        'input[name*="usageFrequency" i]',
        record.get('usage_frequency', ''))

    # Hashtag not in PDF — use config value or default
    hashtag_val = record.get('hashtag') or cfg.get('hashtag', '#EInstagram #Marketing #Digital')
    safe_fill(driver,
        'input[placeholder*="hashtag" i], textarea[placeholder*="hashtag" i], '
        'input[name*="hashtag" i]',
        hashtag_val)

    safe_fill(driver,
        'input[placeholder*="how did you hear" i], '
        'textarea[placeholder*="how did you hear" i], input[name*="hearAbout" i]',
        record.get('hear_about', ''))

    evc = record.get('evc_code') or cfg.get('evc_code', '')
    if evc:
        safe_fill(driver,
            'input[placeholder*="evc code" i], input[name*="evcCode" i], '
            'input[name*="evc" i]',
            evc)

    time.sleep(1)

    captcha_ok = wait_for_manual_captcha(driver, cfg.get('captcha_wait_seconds', 120))
    if not captcha_ok:
        return False

    submitted = click_button(
        driver,
        "//button[contains(text(),'Submit Form')] | //button[contains(text(),'Submit')]",
        label='Submit Form button'
    )
    if submitted:
        add_log("✅ Form submitted!", 'success')
        time.sleep(3)
        return True
    else:
        add_log("❌ Submit button not found", 'error')
        return False


# ═══════════════════════════════════════════════
#  MAIN AUTOMATION THREAD
# ═══════════════════════════════════════════════

def run_automation():
    if bot_state['running']:
        return
    bot_state['running'] = True
    bot_state['stop_requested'] = False
    bot_state['success_count'] = 0
    bot_state['fail_count'] = 0
    bot_state['current_index'] = 0
    cfg = bot_state['config']
    driver = None

    try:
        add_log(f"🌐 Launching Chrome ({platform.system()} / {platform.machine()})...", 'info')
        driver = create_driver()

        # ── Login ──
        add_log("🔐 Navigating to login...", 'info')
        driver.get('https://www.thefuturesparks.com/login')
        time.sleep(3)
        try:
            email_el = driver.find_element(By.CSS_SELECTOR, 'input[type="email"], input[name="email"]')
            pass_el  = driver.find_element(By.CSS_SELECTOR, 'input[type="password"]')
            email_el.clear(); email_el.send_keys(cfg['email'])
            pass_el.clear();  pass_el.send_keys(cfg['password'])
            driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()
            time.sleep(4)
            add_log("✅ Logged in", 'success')
        except Exception as e:
            add_log(f"⚠️  Auto-login failed: {e} — please log in manually (30 s)", 'warning')
            time.sleep(30)

        # ── Tasks page ──
        driver.get('https://www.thefuturesparks.com/tasks')
        time.sleep(3)

        total = min(len(bot_state['records']), cfg['max_submissions'])
        add_log(f"🎯 Will submit {total} forms", 'info')

        for i in range(total):
            if bot_state['stop_requested']:
                add_log("⏹️  Stopped by user", 'warning')
                break

            bot_state['current_index'] = i
            record = bot_state['records'][i]

            # Apply config overrides for fields absent from the PDF
            record['evc_code'] = record.get('evc_code') or cfg.get('evc_code', '')

            add_log(f"📋 [{i+1}/{total}] {record.get('name', 'Unknown')}", 'info')

            try:
                driver.get('https://www.thefuturesparks.com/tasks')
                time.sleep(3)

                # ── Click Start ──
                start_clicked = False
                try:
                    btn = driver.execute_script("""
                        var all = document.querySelectorAll('button,a,div[role="button"]');
                        for (var i=0; i<all.length; i++){
                            var t = (all[i].innerText||all[i].textContent||'').trim();
                            if (t==='Start' || t.startsWith('Start')) return all[i];
                        }
                        return null;
                    """)
                    if btn:
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                        time.sleep(0.4)
                        driver.execute_script("arguments[0].click();", btn)
                        start_clicked = True
                        add_log("✅ Clicked Start (JS)", 'success')
                        time.sleep(2)
                except Exception:
                    pass

                if not start_clicked:
                    for xpath in [
                        "//button[normalize-space()='Start']",
                        "//a[normalize-space()='Start']",
                        "//button[contains(normalize-space(),'Start')]",
                    ]:
                        try:
                            btn = WebDriverWait(driver, 4).until(
                                EC.element_to_be_clickable((By.XPATH, xpath))
                            )
                            driver.execute_script("arguments[0].click();", btn)
                            start_clicked = True
                            add_log(f"✅ Clicked Start (xpath)", 'success')
                            time.sleep(2)
                            break
                        except Exception:
                            continue

                if not start_clicked:
                    add_log("⚠️  Start button not found — skipping", 'warning')
                    bot_state['fail_count'] += 1
                    continue

                # ── Wait for form ──
                form_found = False
                for wait_xpath in [
                    "//*[contains(text(),'E-Insta')]",
                    "//*[contains(text(),'Feedback')]",
                    "//*[contains(text(),'Step 1')]",
                    "//input[@placeholder]",
                    "//form",
                ]:
                    try:
                        WebDriverWait(driver, 8).until(
                            EC.presence_of_element_located((By.XPATH, wait_xpath))
                        )
                        form_found = True
                        break
                    except Exception:
                        continue

                if not form_found:
                    add_log("⚠️  Form did not load — skipping", 'warning')
                    bot_state['fail_count'] += 1
                    continue

                time.sleep(1)

                fill_step1(driver, record, cfg)
                fill_step2(driver, record)
                fill_step3(driver, record)
                success = fill_step4(driver, record, cfg)

                if success:
                    bot_state['success_count'] += 1
                else:
                    bot_state['fail_count'] += 1

            except Exception as e:
                bot_state['fail_count'] += 1
                add_log(f"❌ [{i+1}/{total}] Error: {str(e)[:120]}", 'error')

            pct = round(((i + 1) / total) * 100)
            add_log(
                f"📊 {pct}% | ✅ {bot_state['success_count']} success "
                f"| ❌ {bot_state['fail_count']} failed",
                'info'
            )

            if i < total - 1 and not bot_state['stop_requested']:
                time.sleep(cfg['delay'])

        add_log(
            f"🎉 Done! ✅ {bot_state['success_count']} success | "
            f"❌ {bot_state['fail_count']} failed",
            'success'
        )

    except Exception as e:
        add_log(f"❌ Fatal error: {e}", 'error')
    finally:
        if driver:
            try: driver.quit()
            except Exception: pass
        bot_state['running'] = False


# ═══════════════════════════════════════════════
#  FLASK ROUTES
# ═══════════════════════════════════════════════

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/upload', methods=['POST'])
def upload_pdf():
    if 'pdf' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    file = request.files['pdf']
    if not file.filename:
        return jsonify({'error': 'Empty filename'}), 400
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    records = extract_records_from_pdf(filepath)
    bot_state['records'] = records
    return jsonify({
        'success': True,
        'total_records': len(records),
        'sample': records[:3]
    })


@app.route('/api/start', methods=['POST'])
def start_bot():
    if bot_state['running']:
        return jsonify({'error': 'Bot is already running'}), 400
    data = request.json or {}
    cfg = bot_state['config']
    cfg['email']                = data.get('email', '')
    cfg['password']             = data.get('password', '')
    cfg['delay']                = float(data.get('delay', 3))
    cfg['max_submissions']      = int(data.get('max_submissions', 3000))
    cfg['evc_code']             = data.get('evc_code', '')
    cfg['hashtag']              = data.get('hashtag', '#EInstagram #Marketing #Digital')
    cfg['state']                = data.get('state', '')
    cfg['captcha_wait_seconds'] = int(data.get('captcha_wait_seconds', 120))

    if not bot_state['records']:
        return jsonify({'error': 'No records loaded — upload PDF first'}), 400
    if not cfg['email'] or not cfg['password']:
        return jsonify({'error': 'Email and password are required'}), 400

    t = threading.Thread(target=run_automation)
    t.daemon = True
    t.start()
    return jsonify({'success': True})


@app.route('/api/stop', methods=['POST'])
def stop_bot():
    bot_state['stop_requested'] = True
    return jsonify({'success': True})


@app.route('/api/captcha_done', methods=['POST'])
def captcha_done():
    bot_state['captcha_confirmed'] = True
    return jsonify({'success': True})


@app.route('/api/status', methods=['GET'])
def get_status():
    total = min(len(bot_state['records']), bot_state['config']['max_submissions'])
    pct = 0
    if total > 0 and bot_state['current_index'] > 0:
        pct = round((bot_state['current_index'] / total) * 100)
    return jsonify({
        'running':             bot_state['running'],
        'records_total':       len(bot_state['records']),
        'current_index':       bot_state['current_index'],
        'success_count':       bot_state['success_count'],
        'fail_count':          bot_state['fail_count'],
        'progress_percent':    pct,
        'logs':                bot_state['logs'][-50:],
        'waiting_for_captcha': bot_state.get('waiting_for_captcha', False)
    })


if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("  🤖  E-INSTA FEEDBACK AUTO-BOT")
    print("=" * 60)
    print("  🌐  Open:  http://localhost:5001")
    print("  📄  Upload PDF → Set credentials → Click START")
    print("  🔴  When captcha appears: solve in browser → click dashboard button")
    print("=" * 60 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5001)