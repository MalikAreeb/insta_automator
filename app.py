"""
E-Insta Feedback Auto-Bot — OPTIMIZED VERSION
Manual captcha solve mode only.
"""

import os
import re
import time
import platform
import subprocess
import threading
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import pdfplumber  # Better PDF handling, no external deps

# ==================== CONFIGURATION ====================
IS_MAC = platform.system() == 'Darwin'
IS_WIN = platform.system() == 'Windows'

app = Flask(__name__)
CORS(app)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024
os.makedirs('uploads', exist_ok=True)
os.makedirs('templates', exist_ok=True)

# Bot state
bot_state = {
    'running': False,
    'records': [],
    'current_index': 0,
    'success_count': 0,
    'fail_count': 0,
    'logs': [],
    'stop_requested': False,
    'waiting_for_captcha': False,
    'captcha_confirmed': False,
    'config': {
        'email': '', 'password': '', 'delay': 3,
        'max_submissions': 3000, 'evc_code': '',
        'hashtag': '#EInstagram #Marketing #Digital',
        'state': '', 'captcha_wait_seconds': 120
    }
}

# ==================== LOGGING ====================
def add_log(message, log_type='info'):
    timestamp = time.strftime('%H:%M:%S')
    bot_state['logs'].append({'time': timestamp, 'message': message, 'type': log_type})
    if len(bot_state['logs']) > 500:
        bot_state['logs'] = bot_state['logs'][-500:]
    print(f"[{timestamp}] {message}")

# ==================== PDF EXTRACTION (pdfplumber - no external deps) ====================
def extract_records_from_pdf(pdf_path):
    """Extract records from PDF using pdfplumber (works everywhere)."""
    add_log("📖 Reading PDF...", 'info')
    records = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            add_log(f"📄 {len(pdf.pages)} pages found", 'info')
            
            for page in pdf.pages:
                text = page.extract_text()
                if not text or 'Form No.' not in text:
                    continue
                
                record = {
                    'form_no': _extract(text, r'Form No\.\s*:\s*(\d+)'),
                    'center_code': _extract(text, r'Centre Code\s*:\s*(\S+)'),
                    'name': _extract(text, r'Name\s*:\s*(.*?)(?=\s{2,}Feedback ID|\n)', True),
                    'feedback_id': _extract(text, r'Feedback ID\s*:\s*(\S+)'),
                    'city': _extract(text, r'Cities\s*:\s*(.*?)(?=\s{2,}Age\s*:|\n)', True),
                    'age': _extract(text, r'(?<!\w)Age\s*:\s*(\d+)'),
                    'marital_status': _extract(text, r'Marital Status\s*:\s*(\w+)'),
                    'education': _extract(text, r'Education\s*:\s*(.*?)(?=\s{2,}|\n)', True),
                    'hobbies': _extract_multiline(text, 'Hobbies'),
                    'instagram_benefit': _extract_multiline(text, 'Instagram Benefits for Business'),
                    'job_role': _extract_multiline(text, r'What is your primary Job role[^:\n?]*'),
                    'marketing_task': _extract_multiline(text, r'What type of marketing Task[^:\n?]*'),
                    'usage_frequency': _extract_multiline(text, r'How often do you use instagram[^:\n?]*'),
                    'importance': _extract_multiline(text, r'How important is instagram[^:\n?]*'),
                    'hear_about': _extract_multiline(text, r'How did you hear about Instagram\?'),
                    'gender': '', 'state': '', 'email': '', 'evc_code': '', 'hashtag': ''
                }
                
                if record.get('name'):
                    records.append(record)
        
        add_log(f"✅ Extracted {len(records)} records", 'success')
        return records
    except Exception as e:
        add_log(f"❌ PDF error: {e}", 'error')
        return []

def _extract(text, pattern, multiline=False):
    """Extract single field from text."""
    m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if m:
        val = m.group(1).strip()
        return re.sub(r'\s*\n\s*', ' ', val) if multiline else val
    return ''

def _extract_multiline(text, label):
    """Extract multi-line field that spans until next label."""
    markers = [
        r'Form No\.', r'Centre Code', r'Name', r'Feedback ID', r'Cities', r'Age',
        r'Actual Date and Timing', r'Marital Status', r'Education', r'Hobbies',
        r'Instagram Benefits for Business', r'What is your primary Job role[^:\n?]*',
        r'What type of marketing Task[^:\n?]*', r'How often do you use instagram[^:\n?]*',
        r'How important is instagram[^:\n?]*', r'How did you hear about Instagram\?'
    ]
    pattern = rf'(?:{label})\s*\??\s*:\s*(.*?)(?=\n\s*(?:{"|".join(markers)})\s*:|\Z)'
    m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if m:
        return re.sub(r'\s*\n\s*', ' ', m.group(1).strip())
    return ''

# ==================== CHROME DRIVER ====================
def create_driver():
    """Create Chrome driver with optimal settings."""
    opts = Options()
    
    # Essential flags for stability
    flags = [
        '--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu',
        '--disable-software-rasterizer', '--disable-extensions',
        '--disable-background-networking', '--disable-default-apps',
        '--disable-sync', '--disable-translate', '--metrics-recording-only',
        '--mute-audio', '--no-first-run', '--safebrowsing-disable-auto-update',
        '--disable-features=VizDisplayCompositor', '--window-size=390,844',
        '--user-agent=Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) '
        'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1'
    ]
    for flag in flags:
        opts.add_argument(flag)
    
    # Platform-specific binary paths
    if IS_MAC:
        for path in ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                     '/Applications/Chromium.app/Contents/MacOS/Chromium']:
            if os.path.exists(path):
                opts.binary_location = path
                break
    elif IS_WIN:
        for path in [r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                     r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
                     os.path.expanduser(r'~\AppData\Local\Google\Chrome\Application\chrome.exe')]:
            if os.path.exists(path):
                opts.binary_location = path
                break
    
    try:
        driver = webdriver.Chrome(options=opts)
        add_log("✅ Chrome launched", 'success')
        driver.implicitly_wait(5)
        return driver
    except Exception as e:
        add_log(f"❌ Chrome error: {e}", 'error')
        raise

# ==================== SELENIUM HELPERS ====================
def safe_fill(driver, css, value, wait=6):
    if not value:
        return False
    for sel in css.split(','):
        try:
            el = WebDriverWait(driver, wait).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, sel.strip()))
            )
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            time.sleep(0.2)
            el.clear()
            el.send_keys(str(value))
            return True
        except Exception:
            continue
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
        Select(el).select_by_visible_text(value)
        return True
    except Exception:
        return False

def click_button(driver, xpath, wait=8):
    try:
        btn = WebDriverWait(driver, wait).until(EC.element_to_be_clickable((By.XPATH, xpath)))
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
        time.sleep(0.4)
        btn.click()
        return True
    except Exception:
        return False

def click_next(driver):
    return click_button(driver, "//button[normalize-space()='Next' or contains(text(),'Next')]")

# ==================== CAPTCHA HANDLER ====================
def wait_for_manual_captcha(driver, timeout):
    add_log(f"🔴 CAPTCHA - Solve in browser, then click 'I Solved the Captcha' ({timeout}s)", 'warning')
    bot_state['waiting_for_captcha'] = True
    bot_state['captcha_confirmed'] = False
    deadline = time.time() + timeout
    
    while time.time() < deadline:
        if bot_state['captcha_confirmed']:
            bot_state['waiting_for_captcha'] = False
            add_log("✅ Captcha confirmed", 'success')
            return True
        time.sleep(2)
    
    bot_state['waiting_for_captcha'] = False
    add_log("❌ Captcha timeout", 'error')
    return False

# ==================== FORM FILLING ====================
def fill_step1(driver, record, cfg, index):
    safe_fill(driver, 'input[placeholder*="name" i], input[name*="name" i]', record.get('name', ''))
    safe_fill(driver, 'input[placeholder*="center code" i], input[name*="centerCode" i]', record.get('center_code', ''))
    safe_select(driver, 'select', record.get('gender') or 'Male')
    safe_fill(driver, 'input[placeholder*="e-instagram benif" i], textarea[placeholder*="e-instagram benif" i]', record.get('instagram_benefit', ''))
    safe_fill(driver, 'input[placeholder*="feedback id" i], input[name*="feedbackId" i]', record.get('feedback_id') or str(1000 + index))
    time.sleep(0.5)
    click_next(driver)
    time.sleep(2)

def fill_step2(driver, record):
    safe_fill(driver, 'input[placeholder*="important" i], textarea[placeholder*="important" i]', record.get('importance', ''))
    safe_fill(driver, 'input[placeholder*="city" i]', record.get('city', ''))
    safe_fill(driver, 'input[placeholder*="age" i]', record.get('age', ''))
    safe_fill(driver, 'input[placeholder*="hobbi" i], textarea[placeholder*="hobbi" i]', record.get('hobbies', ''))
    safe_fill(driver, 'input[placeholder*="job role" i], textarea[placeholder*="job role" i]', record.get('job_role', ''))
    time.sleep(0.5)
    click_next(driver)
    time.sleep(2)

def fill_step3(driver, record, index):
    marital_map = {'unmarried': 'Single', 'single': 'Single', 'married': 'Married', 'divorced': 'Divorced', 'widowed': 'Widowed'}
    marital_val = marital_map.get((record.get('marital_status') or 'Single').lower(), 'Single')
    safe_select(driver, 'select[name*="marital" i], select', marital_val)
    
    email_val = record.get('email') or f'user{1000 + index}@gmail.com'
    safe_fill(driver, 'input[placeholder*="email" i], input[name*="email" i]', email_val)
    safe_fill(driver, 'input[placeholder*="marketing task" i], textarea[placeholder*="marketing task" i]', record.get('marketing_task', ''))
    safe_fill(driver, 'input[placeholder*="education" i]', record.get('education', ''))
    
    state_val = record.get('state') or bot_state['config'].get('state', '')
    if state_val:
        safe_fill(driver, 'input[placeholder*="state" i]', state_val)
    
    time.sleep(0.5)
    click_next(driver)
    time.sleep(2)

def fill_step4(driver, record, cfg):
    safe_fill(driver, 'input[placeholder*="how often" i], textarea[placeholder*="how often" i]', record.get('usage_frequency', ''))
    safe_fill(driver, 'input[placeholder*="hashtag" i], textarea[placeholder*="hashtag" i]', record.get('hashtag') or cfg.get('hashtag', '#EInstagram #Marketing #Digital'))
    safe_fill(driver, 'input[placeholder*="how did you hear" i], textarea[placeholder*="how did you hear" i]', record.get('hear_about', ''))
    
    evc = record.get('evc_code') or cfg.get('evc_code', '')
    if evc:
        safe_fill(driver, 'input[placeholder*="evc code" i], input[name*="evcCode" i]', evc)
    
    time.sleep(1)
    if not wait_for_manual_captcha(driver, cfg.get('captcha_wait_seconds', 120)):
        return False
    
    if click_button(driver, "//button[contains(text(),'Submit Form')] | //button[contains(text(),'Submit')]"):
        add_log("✅ Form submitted!", 'success')
        time.sleep(3)
        return True
    else:
        add_log("❌ Submit button not found", 'error')
        return False

# ==================== MAIN AUTOMATION ====================
def run_automation():
    if bot_state['running']:
        return
    
    bot_state.update({'running': True, 'stop_requested': False, 'success_count': 0, 'fail_count': 0, 'current_index': 0})
    cfg = bot_state['config']
    driver = None
    
    try:
        add_log("🌐 Launching Chrome...", 'info')
        driver = create_driver()
        
        # Login
        driver.get('https://www.thefuturesparks.com/login')
        time.sleep(3)
        try:
            driver.find_element(By.CSS_SELECTOR, 'input[type="email"], input[name="email"]').send_keys(cfg['email'])
            driver.find_element(By.CSS_SELECTOR, 'input[type="password"]').send_keys(cfg['password'])
            driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()
            time.sleep(4)
            add_log("✅ Logged in", 'success')
        except Exception:
            add_log("⚠️ Auto-login failed - please login manually (30s)", 'warning')
            time.sleep(30)
        
        driver.get('https://www.thefuturesparks.com/tasks')
        time.sleep(3)
        
        total = min(len(bot_state['records']), cfg['max_submissions'])
        add_log(f"🎯 Will submit {total} forms", 'info')
        
        for i in range(total):
            if bot_state['stop_requested']:
                add_log("⏹️ Stopped by user", 'warning')
                break
            
            bot_state['current_index'] = i
            record = bot_state['records'][i].copy()
            record['evc_code'] = cfg.get('evc_code', '')
            
            add_log(f"📋 [{i+1}/{total}] {record.get('name', 'Unknown')}", 'info')
            
            try:
                driver.get('https://www.thefuturesparks.com/tasks')
                time.sleep(3)
                
                # Click Start button
                start_clicked = False
                for xpath in ["//button[normalize-space()='Start']", "//a[normalize-space()='Start']", "//button[contains(text(),'Start')]"]:
                    try:
                        btn = WebDriverWait(driver, 4).until(EC.element_to_be_clickable((By.XPATH, xpath)))
                        driver.execute_script("arguments[0].click();", btn)
                        start_clicked = True
                        add_log("✅ Clicked Start", 'success')
                        time.sleep(2)
                        break
                    except Exception:
                        continue
                
                if not start_clicked:
                    add_log("⚠️ Start button not found", 'warning')
                    bot_state['fail_count'] += 1
                    continue
                
                # Fill form
                fill_step1(driver, record, cfg, i)
                fill_step2(driver, record)
                fill_step3(driver, record, i)
                success = fill_step4(driver, record, cfg)
                
                if success:
                    bot_state['success_count'] += 1
                else:
                    bot_state['fail_count'] += 1
                    
            except Exception as e:
                bot_state['fail_count'] += 1
                add_log(f"❌ Error: {str(e)[:100]}", 'error')
            
            pct = round(((i + 1) / total) * 100)
            add_log(f"📊 {pct}% | ✅ {bot_state['success_count']} | ❌ {bot_state['fail_count']}", 'info')
            
            if i < total - 1 and not bot_state['stop_requested']:
                time.sleep(cfg['delay'])
        
        add_log(f"🎉 Done! ✅ {bot_state['success_count']} | ❌ {bot_state['fail_count']}", 'success')
        
    except Exception as e:
        add_log(f"❌ Fatal: {e}", 'error')
    finally:
        if driver:
            try: driver.quit()
            except: pass
        bot_state['running'] = False

# ==================== FLASK ROUTES ====================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/upload', methods=['POST'])
def upload_pdf():
    if 'pdf' not in request.files:
        return jsonify({'error': 'No file'}), 400
    file = request.files['pdf']
    if not file.filename:
        return jsonify({'error': 'Empty filename'}), 400
    
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(file.filename))
    file.save(filepath)
    records = extract_records_from_pdf(filepath)
    bot_state['records'] = records
    return jsonify({'success': True, 'total_records': len(records)})

@app.route('/api/start', methods=['POST'])
def start_bot():
    if bot_state['running']:
        return jsonify({'error': 'Bot is running'}), 400
    
    data = request.json or {}
    cfg = bot_state['config']
    cfg.update({
        'email': data.get('email', ''),
        'password': data.get('password', ''),
        'delay': float(data.get('delay', 3)),
        'max_submissions': int(data.get('max_submissions', 3000)),
        'evc_code': data.get('evc_code', ''),
        'hashtag': data.get('hashtag', '#EInstagram #Marketing #Digital'),
        'state': data.get('state', ''),
        'captcha_wait_seconds': int(data.get('captcha_wait_seconds', 120))
    })
    
    if not bot_state['records']:
        return jsonify({'error': 'Upload PDF first'}), 400
    if not cfg['email'] or not cfg['password']:
        return jsonify({'error': 'Email and password required'}), 400
    
    threading.Thread(target=run_automation, daemon=True).start()
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
    pct = round((bot_state['current_index'] / total) * 100) if total > 0 and bot_state['current_index'] > 0 else 0
    return jsonify({
        'running': bot_state['running'],
        'records_total': len(bot_state['records']),
        'current_index': bot_state['current_index'],
        'success_count': bot_state['success_count'],
        'fail_count': bot_state['fail_count'],
        'progress_percent': pct,
        'logs': bot_state['logs'][-50:],
        'waiting_for_captcha': bot_state.get('waiting_for_captcha', False)
    })

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("  🤖  E-INSTA FEEDBACK AUTO-BOT (OPTIMIZED)")
    print("=" * 60)
    print("  🌐  http://localhost:5001")
    print("  📄  Upload PDF → Set credentials → START")
    print("  🔴  Captcha? Solve in browser → click dashboard button")
    print("=" * 60 + "\n")
    app.run(debug=False, host='0.0.0.0', port=5001)