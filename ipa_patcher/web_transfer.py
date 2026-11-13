# -*- coding: utf-8 -*-
import os
import sys
import socket
import http.server
import urllib.parse
from socketserver import ThreadingMixIn
import time
import datetime
import secrets
import hashlib
import re
import json
from collections import defaultdict
import threading
import shutil
import argparse

from i18n import init_i18n, set_lang, get_lang, t

try:
    import background
    HAVE_BACKGROUND = True
except ImportError:
    HAVE_BACKGROUND = False

try:
    import console
    HAVE_CONSOLE = True
except ImportError:
    HAVE_CONSOLE = False

CONFIG = {
    'PORT': 8080,
    'MAX_FILE_SIZE': 5 * 1024 * 1024 * 1024,
    'ALLOWED_EXTENSIONS': {'.ipa', '.tipa', '.zip', '.deb', '.dylib'},
    'RATE_LIMIT': 5,
    'BAN_THRESHOLD': 5,
    'BAN_DURATION': 600,
    'SESSION_TIMEOUT': 300,
    'MAX_CONNECTIONS': 10,
}

VERSION = '1.1.9'


def _parse_cli_args():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--lang", choices=["en", "ru"], default=None)
    args, _ = parser.parse_known_args()
    return args


def _get_docs_dir():
    home = os.path.expanduser('~')
    if os.path.basename(home).lower() == 'documents':
        return home
    return os.path.join(home, 'Documents')


DOCS_DIR = _get_docs_dir()
FILES_DIR = os.path.join(DOCS_DIR, 'IPA_Patcher_Files')
LOGS_DIR = os.path.join(DOCS_DIR, 'IPA_Patcher_Logs')
LOG_FILE = os.path.join(LOGS_DIR, 'web_transfer.log')
BLACKLIST_FILE = os.path.join(LOGS_DIR, 'blacklist.json')
AUDIT_LOG = os.path.join(LOGS_DIR, 'audit.log')

STOP_SERVER = False
SERVER_INSTANCE = None


class SecurityManager:
    def __init__(self):
        self.access_token = str(secrets.randbelow(900000) + 100000)
        self.token_hash = hashlib.sha256(self.access_token.encode()).hexdigest()
        self.sessions = {}
        self.rate_limiter = defaultdict(list)
        self.failed_attempts = defaultdict(int)
        self.banned_ips = {}
        self.active_connections = 0
        self.connection_lock = threading.Lock()
        self.rate_lock = threading.Lock()
        self._load_blacklist()

    def _load_blacklist(self):
        try:
            if os.path.exists(BLACKLIST_FILE):
                with open(BLACKLIST_FILE, 'r', encoding='utf-8') as f:
                    self.banned_ips = json.load(f).get('banned', {})
        except Exception:
            pass

    def _save_blacklist(self):
        try:
            os.makedirs(LOGS_DIR, mode=0o755, exist_ok=True)
            with open(BLACKLIST_FILE, 'w', encoding='utf-8') as f:
                json.dump({'banned': self.banned_ips}, f)
        except Exception:
            pass

    def check_rate_limit(self, ip):
        now = time.time()
        with self.rate_lock:
            self.rate_limiter[ip] = [t for t in self.rate_limiter[ip] if now - t < 60]
            if len(self.rate_limiter[ip]) >= CONFIG['RATE_LIMIT']:
                return False
            self.rate_limiter[ip].append(now)
        return True

    def check_ban(self, ip):
        with self.rate_lock:
            if ip in self.banned_ips:
                if time.time() - self.banned_ips[ip] < CONFIG['BAN_DURATION']:
                    return True
                else:
                    del self.banned_ips[ip]
                    self._save_blacklist()
        return False

    def record_failed_attempt(self, ip):
        with self.rate_lock:
            self.failed_attempts[ip] += 1
            if self.failed_attempts[ip] >= CONFIG['BAN_THRESHOLD']:
                self.banned_ips[ip] = time.time()
                self._save_blacklist()
                audit_log(t("wt_banned", ip=ip), 'WARN')

    def validate_token(self, token):
        if not token:
            return False
        return secrets.compare_digest(token, self.access_token)

    def get_session_id(self, ip):
        with self.rate_lock:
            if ip not in self.sessions:
                self.sessions[ip] = {
                    'created': time.time(),
                    'last_activity': time.time()
                }
            return self.sessions[ip]

    def check_connection_limit(self):
        with self.connection_lock:
            if self.active_connections >= CONFIG['MAX_CONNECTIONS']:
                return False
            self.active_connections += 1
            return True

    def release_connection(self):
        with self.connection_lock:
            if self.active_connections > 0:
                self.active_connections -= 1

    def get_token(self):
        return self.access_token

    def rotate_token(self):
        new_token = str(secrets.randbelow(900000) + 100000)
        self.access_token = new_token
        self.token_hash = hashlib.sha256(new_token.encode()).hexdigest()
        audit_log(t("wt_pin_updated"), 'INFO')
        return new_token


security = SecurityManager()


def audit_log(msg, level='INFO'):
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    masked_msg = re.sub(r'\b(\d{1,3}\.\d{1,3})\.\d{1,3}\.\d{1,3}\b', r'\1.xxx.xxx', msg)
    try:
        os.makedirs(LOGS_DIR, mode=0o755, exist_ok=True)
        with open(AUDIT_LOG, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] [{level}] {masked_msg}\n")
    except Exception:
        pass


def log_message(msg, level='INFO'):
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        os.makedirs(LOGS_DIR, mode=0o755, exist_ok=True)
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] [{level}] {msg}\n")
    except Exception:
        pass

    color_print(f"[{timestamp}] {msg}", level_to_color(level))


def level_to_color(level):
    if level == 'INFO':
        return 'cyan'
    elif level == 'SUCCESS':
        return 'green'
    elif level == 'WARN':
        return 'yellow'
    elif level == 'ERROR':
        return 'red'
    else:
        return 'white'


def ensure_directories():
    for d in [FILES_DIR, LOGS_DIR]:
        if not os.path.exists(d):
            os.makedirs(d, mode=0o755, exist_ok=True)


def color_print(text, color='white'):
    if HAVE_CONSOLE:
        try:
            colors = {
                'white': (1.0, 1.0, 1.0),
                'red': (1.0, 0.0, 0.0),
                'green': (0.0, 1.0, 0.0),
                'yellow': (1.0, 1.0, 0.0),
                'blue': (0.0, 0.5, 1.0),
                'cyan': (0.0, 1.0, 1.0),
                'magenta': (1.0, 0.0, 1.0),
                'orange': (1.0, 0.5, 0.0),
            }
            r, g, b = colors.get(color, (1.0, 1.0, 1.0))
            console.set_color(r, g, b)
            print(text)
            console.set_color(1.0, 1.0, 1.0)
            return
        except Exception:
            pass

    ansi_colors = {
        'white': '\033[97m',
        'red': '\033[91m',
        'green': '\033[92m',
        'yellow': '\033[93m',
        'blue': '\033[94m',
        'cyan': '\033[96m',
        'magenta': '\033[95m',
        'orange': '\033[33m',
    }
    reset = '\033[0m'
    code = ansi_colors.get(color, '\033[97m')
    print(f"{code}{text}{reset}")


def clear_screen():
    if HAVE_CONSOLE:
        try:
            console.clear()
            return
        except Exception:
            pass
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


def sanitize_filename(filename):
    filename = os.path.basename(filename)
    filename = re.sub(r'[^a-zA-Z0-9_.-]', '_', filename)
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:250] + ext
    return filename


def is_allowed_extension(filename):
    return os.path.splitext(filename)[1].lower() in CONFIG['ALLOWED_EXTENSIONS']


def is_safe_path(path):
    try:
        real_base = os.path.realpath(FILES_DIR)
        real_path = os.path.realpath(path)
        return real_path == real_base or real_path.startswith(real_base + os.sep)
    except Exception:
        return False


def shorten_path(path):
    if 'Documents' in path:
        return '~/Documents' + path.split('Documents', 1)[1]
    return path


class ThreadedFastHTTPServer(ThreadingMixIn, http.server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class SecureHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, format, *args):
        pass

    def send_security_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('X-XSS-Protection', '1; mode=block')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header(
            'Content-Security-Policy',
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'"
        )

    def send_json_response(self, data, status=200):
        response = json.dumps(data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(response)))
        self.send_header('Connection', 'close')
        self.send_security_headers()
        self.end_headers()
        self.wfile.write(response)
        self.close_connection = True

    def send_html_response(self, html_text, status=200):
        response = html_text.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(response)))
        self.send_header('Connection', 'close')
        self.send_security_headers()
        self.end_headers()
        self.wfile.write(response)
        self.close_connection = True

    def validate_request(self):
        ip = self.client_address[0]

        if security.check_ban(ip):
            self.send_response(403)
            self.send_header('Connection', 'close')
            self.end_headers()
            self.close_connection = True
            return False

        if not security.check_rate_limit(ip):
            self.send_response(429)
            self.send_header('Connection', 'close')
            self.end_headers()
            self.close_connection = True
            return False

        security.get_session_id(ip)['last_activity'] = time.time()
        return True

    def validate_token(self):
        token = self.headers.get('X-Access-Token')
        if token and security.validate_token(token):
            return True

        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if 'token' in params and security.validate_token(params['token'][0]):
            return True

        return False

    def do_GET(self):
        if STOP_SERVER:
            self.close_connection = True
            return

        if not security.check_connection_limit():
            self.send_json_response({'error': 'Server busy'}, 503)
            return

        try:
            ip = self.client_address[0]

            if not self.validate_request():
                return

            parsed = urllib.parse.urlparse(self.path)
            clean_path = parsed.path
            params = urllib.parse.parse_qs(parsed.query)

            if clean_path == '/api/verify':
                token = params.get('token', [''])[0]
                if security.validate_token(token):
                    log_message(t("wt_login_success", ip=ip), 'SUCCESS')
                    audit_log(t("wt_login_success", ip=ip), 'INFO')
                    self.send_json_response({'valid': True})
                else:
                    log_message(t("wt_login_fail", ip=ip), 'WARN')
                    audit_log(t("wt_login_fail", ip=ip), 'WARN')
                    security.record_failed_attempt(ip)
                    self.send_json_response({'valid': False}, 401)
                return

            if clean_path == '/' or clean_path == '/index.html':
                if 'token' in params and security.validate_token(params['token'][0]):
                    self.send_html_response(self.get_secure_html())
                else:
                    self.send_html_response(self.get_login_page(), 401)
                return

            if clean_path.startswith('/api/'):
                if not self.validate_token():
                    security.record_failed_attempt(ip)
                    self.send_json_response({'error': 'Unauthorized'}, 401)
                    return

                if clean_path == '/api/status':
                    self.send_json_response({
                        'status': 'online',
                        'connections': security.active_connections,
                        'max_file_size': CONFIG['MAX_FILE_SIZE']
                    })
                    return

                if clean_path == '/api/files':
                    files = []
                    try:
                        for f in os.listdir(FILES_DIR):
                            fpath = os.path.join(FILES_DIR, f)
                            if os.path.isfile(fpath):
                                files.append({
                                    'name': f,
                                    'size': os.path.getsize(fpath),
                                    'modified': os.path.getmtime(fpath)
                                })
                    except Exception:
                        pass
                    self.send_json_response(files)
                    return

                if clean_path == '/api/stop':
                    stop_server()
                    self.send_json_response({'status': 'stopped'})
                    return

            self.send_response(404)
            self.send_header('Connection', 'close')
            self.end_headers()
            self.close_connection = True
        finally:
            security.release_connection()

    def do_POST(self):
        if STOP_SERVER:
            self.close_connection = True
            return

        if not security.check_connection_limit():
            self.send_json_response({'error': 'Server busy'}, 503)
            return

        try:
            ip = self.client_address[0]

            if not self.validate_request():
                return

            try:
                content_length = int(self.headers.get('Content-Length', 0))
            except ValueError:
                self.send_json_response({'error': 'Invalid Content-Length'}, 400)
                return

            if content_length <= 0:
                self.send_json_response({'error': 'Invalid Content-Length'}, 400)
                return

            if not self.validate_token():
                security.record_failed_attempt(ip)
                self.send_json_response({'error': 'Invalid token'}, 401)
                return

            filename = urllib.parse.unquote(self.headers.get('X-File-Name', 'file.bin'))
            safe_filename = sanitize_filename(filename)

            if not is_allowed_extension(safe_filename):
                self.send_json_response({'error': 'Rejected file type'}, 400)
                return

            if content_length > CONFIG['MAX_FILE_SIZE']:
                self.send_json_response({'error': 'Payload too large'}, 413)
                return

            ensure_directories()
            out_path = os.path.join(FILES_DIR, safe_filename)

            if not is_safe_path(out_path):
                self.send_json_response({'error': 'Forbidden'}, 403)
                return

            if os.path.exists(out_path):
                name, ext = os.path.splitext(safe_filename)
                timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                safe_filename = f"{name}_{timestamp}{ext}"
                out_path = os.path.join(FILES_DIR, safe_filename)

            start_time = time.time()
            written = 0
            temp_path = out_path + '.tmp'

            try:
                with open(temp_path, 'wb') as f:
                    while written < content_length:
                        chunk_size = min(65536, content_length - written)
                        chunk = self.rfile.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        written += len(chunk)

                        if time.time() - start_time > 3600:
                            raise TimeoutError("Upload timeout (1 hour)")

                if written < content_length:
                    raise ConnectionError("Incomplete read")

                os.rename(temp_path, out_path)

                elapsed = time.time() - start_time
                speed = written / elapsed / 1024 / 1024 if elapsed > 0 else 0

                size_mb_str = f"{written / 1024 / 1024:.2f}"
                log_message(t("wt_file_uploaded", name=safe_filename, size=size_mb_str, ip=ip), 'SUCCESS')
                audit_log(t("wt_file_uploaded", name=safe_filename, size=size_mb_str, ip=ip), 'INFO')

                self.send_json_response({
                    'status': 'success',
                    'filename': safe_filename,
                    'size': written,
                    'speed': round(speed, 2),
                    'time': round(elapsed, 2)
                })

                print()
                color_print(f"  [+] Успешно загружен: {safe_filename}", 'green')
                return

            except Exception as e:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
                log_message(t("wt_upload_err", ip=ip, err=e), 'ERROR')
                audit_log(t("wt_upload_err", ip=ip, err=e), 'ERROR')
                self.send_json_response({'error': 'Internal Server Error'}, 500)
        finally:
            security.release_connection()

    def get_login_page(self):
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>{t("wt_html_login_title")}</title>
            <style>
                *{{margin:0;padding:0;box-sizing:border-box}}
                body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#1c1c1e;display:flex;justify-content:center;align-items:center;min-height:100vh}}
                .card{{background:#2c2c2e;padding:30px;border-radius:16px;text-align:center;width:320px;color:white}}
                h2{{margin-bottom:20px;font-size:20px;font-weight:600}}
                input{{width:100%;padding:12px;border:none;border-radius:10px;margin-bottom:16px;font-size:16px;text-align:center;background:#3a3a3c;color:white;font-family:monospace;letter-spacing:2px}}
                input:focus{{outline:2px solid #007aff}}
                .btn{{background:#007aff;color:white;padding:12px;border:none;border-radius:10px;width:100%;font-weight:600;font-size:16px;cursor:pointer;transition:opacity 0.2s}}
                .btn:hover{{opacity:0.8}}
                .hint{{font-size:12px;color:#8e8e93;margin-top:12px}}
                .version{{font-size:11px;color:#5a5a5c;margin-top:8px}}
            </style>
        </head>
        <body>
            <div class="card">
                <h2>Secure Transfer</h2>
                <input type="password" id="pin" placeholder="{t("wt_html_pin_ph")}" maxlength="6" autofocus>
                <button class="btn" id="login">{t("wt_html_login_btn")}</button>
                <div class="hint">{t("wt_html_pin_hint")}</div>
                <div class="version">IPA Patcher Lite Transfer v{VERSION}</div>
            </div>
            <script>
                document.getElementById('login').onclick = function() {{
                    const pin = document.getElementById('pin').value.trim();
                    if (!pin) return;
                    fetch('/api/verify?token=' + encodeURIComponent(pin))
                        .then(r => r.ok ? window.location.href='/?token='+encodeURIComponent(pin) : alert('Invalid PIN'));
                }};
                document.getElementById('pin').onkeydown = function(e) {{
                    if (e.key === 'Enter') document.getElementById('login').click();
                }};
                setTimeout(() => document.getElementById('pin').focus(), 300);
            </script>
        </body>
        </html>
        """

    def get_secure_html(self):
        token = security.get_token()
        ip = get_local_ip()
        port = CONFIG['PORT']
        max_size_mb = CONFIG['MAX_FILE_SIZE'] // (1024 * 1024)
        allowed_json = json.dumps(sorted(CONFIG['ALLOWED_EXTENSIONS']))

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Secure Transfer</title>
            <style>
                *{{margin:0;padding:0;box-sizing:border-box}}
                body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#f2f2f7;display:flex;justify-content:center;align-items:center;min-height:100vh}}
                .card{{background:white;padding:30px;border-radius:24px;box-shadow:0 10px 30px rgba(0,0,0,0.05);text-align:center;width:350px;max-width:90%}}
                .badge{{display:inline-block;padding:4px 12px;border-radius:10px;font-size:12px;font-weight:600;margin-bottom:16px}}
                .badge.ok{{background:#34c759;color:white}}
                .badge.error{{background:#ff3b30;color:white}}
                .badge.waiting{{background:#ff9500;color:white}}
                h2{{font-size:22px;font-weight:700;color:#1c1c1e;margin-bottom:4px}}
                .sub{{font-size:14px;color:#8e8e93;margin-bottom:16px}}
                .ip-box{{background:#f2f2f7;padding:10px;border-radius:10px;font-size:14px;font-weight:600;margin:12px 0}}
                .pin-box{{font-family:monospace;font-size:24px;letter-spacing:4px;font-weight:700;background:#f2f2f7;padding:12px;border-radius:10px;margin:8px 0 16px 0;user-select:all}}
                .btn{{background:#007aff;color:white;padding:14px;border-radius:12px;display:block;font-weight:600;font-size:16px;cursor:pointer;border:none;width:100%;transition:opacity 0.2s}}
                .btn:hover{{opacity:0.8}}
                .btn:disabled{{opacity:0.5;cursor:not-allowed}}
                .btn.error{{background:#ff3b30}}
                .btn.success{{background:#34c759}}
                #prog{{display:none;margin-top:16px;height:6px;background:#e5e5ea;border-radius:3px;overflow:hidden}}
                #fill{{height:100%;width:0%;background:#34c759;transition:width 0.15s}}
                .info{{font-size:13px;color:#8e8e93;margin-top:10px}}
                .exts{{font-size:11px;color:#8e8e93;margin-top:8px}}
                .exts span{{background:#e5e5ea;padding:2px 8px;border-radius:4px;display:inline-block;margin:2px}}
                .version{{font-size:11px;color:#c7c7cc;margin-top:12px}}
                .size-info{{font-size:11px;color:#8e8e93;margin-top:4px}}
            </style>
        </head>
        <body>
            <div class="card">
                <div class="badge ok" id="status">{t("wt_html_badge_ok")}</div>
                <h2>Secure Transfer</h2>
                <p class="sub">{t("wt_html_sub")}</p>
                <div class="ip-box">{ip}:{port}</div>
                <div class="info">{t("wt_pin_ph") if get_lang()=='ru' else "PIN CODE"}</div>
                <div class="pin-box" id="pinDisplay">{token}</div>
                <input type="file" id="fileInput" style="display:none">
                <button class="btn" id="uploadBtn">{t("wt_html_pick_btn")}</button>
                <div id="prog"><div id="fill"></div></div>
                <div id="msg" class="info"></div>
                <button id="stopBtn" style="background:#ff3b30;color:white;padding:14px;border-radius:12px;border:none;width:100%;font-size:16px;font-weight:600;margin-top:12px;cursor:pointer">{t("wt_html_stop_btn")}</button>
                <div class="exts">
                    <span>.ipa</span><span>.tipa</span><span>.zip</span><span>.deb</span><span>.dylib</span>
                </div>
                <div class="size-info">{t("wt_html_max_size", size=max_size_mb)}</div>
                <div class="version">IPA Patcher Lite Transfer v{VERSION}</div>
            </div>
            <script>
                (function() {{
                    const TOKEN = '{token}';
                    const MAX_SIZE = {CONFIG['MAX_FILE_SIZE']};
                    const ALLOWED = {allowed_json};

                    const status = document.getElementById('status');
                    const btn = document.getElementById('uploadBtn');
                    const fileInput = document.getElementById('fileInput');
                    const prog = document.getElementById('prog');
                    const fill = document.getElementById('fill');
                    const msg = document.getElementById('msg');
                    const pinDisplay = document.getElementById('pinDisplay');
                    const stopBtn = document.getElementById('stopBtn');

                    pinDisplay.onclick = function() {{
                        navigator.clipboard.writeText(TOKEN).then(() => {{
                            const orig = this.textContent;
                            this.textContent = '{t("wt_html_copied")}';
                            setTimeout(() => {{ this.textContent = orig; }}, 1500);
                        }});
                    }};

                    function isAllowed(filename) {{
                        const ext = '.' + filename.split('.').pop().toLowerCase();
                        return ALLOWED.includes(ext);
                    }}

                    btn.onclick = function() {{ fileInput.click(); }};

                    fileInput.onchange = function() {{
                        const file = this.files[0];
                        if (!file) return;

                        if (!isAllowed(file.name)) {{
                            alert('Invalid file type.');
                            this.value = '';
                            return;
                        }}

                        if (file.size > MAX_SIZE) {{
                            alert('File too large.');
                            this.value = '';
                            return;
                        }}

                        btn.textContent = '{t("wt_html_uploading")}';
                        btn.disabled = true;
                        status.className = 'badge waiting';
                        status.textContent = '{t("wt_html_status_load")}';
                        prog.style.display = 'block';
                        msg.textContent = file.name + ' (' + (file.size/1024/1024).toFixed(1) + ' MB)';

                        const xhr = new XMLHttpRequest();
                        const start = Date.now();

                        xhr.upload.onprogress = function(e) {{
                            if (e.lengthComputable) {{
                                const pct = (e.loaded / e.total * 100);
                                fill.style.width = pct + '%';
                                const elapsed = (Date.now() - start) / 1000;
                                const speed = elapsed > 0 ? (e.loaded / 1024 / 1024) / elapsed : 0;
                                msg.textContent = pct.toFixed(0) + '%  ' + speed.toFixed(1) + ' MB/s';
                            }}
                        }};

                        xhr.onload = function() {{
                            if (xhr.status === 200) {{
                                try {{
                                    const resp = JSON.parse(xhr.responseText);
                                    status.className = 'badge ok';
                                    status.textContent = '{t("wt_html_status_done")}';
                                    btn.textContent = '{t("wt_html_pick_btn")}';
                                    btn.className = 'btn';
                                    btn.disabled = false;
                                    msg.textContent = '{t("wt_html_saved_lbl", name="")}' + resp.filename;
                                    prog.style.display = 'none';
                                    fill.style.width = '0%';
                                    fileInput.value = '';
                                }} catch(e) {{
                                    xhr.onerror();
                                }}
                            }} else {{
                                xhr.onerror();
                            }}
                        }};

                        xhr.onerror = function() {{
                            status.className = 'badge error';
                            status.textContent = '{t("wt_html_status_err")}';
                            btn.textContent = '{t("wt_html_retry_btn")}';
                            btn.className = 'btn error';
                            btn.disabled = false;
                            msg.textContent = '{t("wt_html_err_msg")}';
                            prog.style.display = 'none';
                            fill.style.width = '0%';
                        }};

                        xhr.open('POST', '/');
                        xhr.setRequestHeader('Content-Type', 'application/octet-stream');
                        xhr.setRequestHeader('X-File-Name', encodeURIComponent(file.name));
                        xhr.setRequestHeader('X-Access-Token', TOKEN);
                        xhr.send(file);
                    }};

                    stopBtn.onclick = function() {{
                        if (confirm('{t("wt_html_stop_q")}')) {{
                            fetch('/api/stop?token=' + TOKEN)
                                .then(r => {{
                                    if (r.ok) {{
                                        status.className = 'badge error';
                                        status.textContent = '{t("wt_html_status_err")}';
                                        btn.disabled = true;
                                        stopBtn.disabled = true;
                                        msg.textContent = '{t("wt_html_stopped_msg")}';
                                        prog.style.display = 'none';
                                        setTimeout(() => {{ window.close(); }}, 1000);
                                    }}
                                }});
                        }}
                    }};
                }})();
            </script>
        </body>
        </html>
        """


def stop_server():
    global STOP_SERVER, SERVER_INSTANCE
    STOP_SERVER = True
    log_message(t("wt_srv_stopped_web"), 'INFO')
    audit_log(t("wt_srv_stopped_web"), 'INFO')

    def shutdown_server():
        time.sleep(0.1)
        if SERVER_INSTANCE:
            try:
                SERVER_INSTANCE.shutdown()
                SERVER_INSTANCE.server_close()
            except Exception:
                pass

    threading.Thread(target=shutdown_server, daemon=True).start()


def print_header():
    clear_screen()
    width = 49
    title = f"IPA PATCHER LITE TRANSFER v{VERSION}"

    color_print("=" * width, 'cyan')
    color_print(title.center(width), 'cyan')
    color_print("=" * width, 'cyan')
    print()


def print_status(ip, port, running=False):
    max_size_mb = CONFIG['MAX_FILE_SIZE'] // (1024 * 1024)
    if running:
        color_print(t("wt_run_running"), 'green')
        color_print(t("wt_run_addr", ip=ip, port=port), 'blue')
        color_print(t("wt_run_dir", path=shorten_path(FILES_DIR)), 'white')
        color_print(t("wt_run_pin", pin=security.get_token()), 'yellow')
        color_print(t("wt_run_size", size=max_size_mb), 'white')
        color_print(t("wt_run_conn", conn=security.active_connections), 'white')
        if HAVE_BACKGROUND:
            color_print(t("wt_run_bg"), 'green')
        color_print(t("wt_run_log", path=shorten_path(LOG_FILE)), 'white')
        color_print(t("wt_run_audit", path=shorten_path(AUDIT_LOG)), 'white')
    else:
        color_print(t("wt_run_stopped"), 'yellow')
    print()
    color_print("-" * 49, 'cyan')
    print()


def show_security_info():
    clear_screen()
    print_header()
    color_print(t("wt_sec_info_title"), 'cyan')
    print()
    color_print(t("wt_sec_prot"), 'yellow')
    color_print(t("wt_sec_dt"), 'green')
    color_print(t("wt_sec_dos"), 'green')
    color_print(t("wt_sec_brute"), 'green')
    color_print(t("wt_sec_overflow"), 'green')
    color_print(t("wt_sec_xss"), 'green')
    color_print(t("wt_sec_timing"), 'green')
    color_print(t("wt_sec_leak"), 'green')
    print()
    color_print(t("wt_pin_lbl"), 'yellow')
    color_print(f"    {security.get_token()}", 'blue')
    color_print(t("wt_pin_hint"), 'white')
    print()
    color_print(t("wt_ext_lbl"), 'yellow')
    color_print("    " + ", ".join(sorted(CONFIG['ALLOWED_EXTENSIONS'])), 'white')
    print()
    color_print(t("wt_limits_lbl"), 'yellow')
    max_size_mb = CONFIG['MAX_FILE_SIZE'] // (1024 * 1024)
    color_print(t("wt_max_size", size=max_size_mb), 'white')
    color_print(t("wt_req_min", rate=CONFIG['RATE_LIMIT']), 'white')
    color_print(t("wt_max_conn", conn=CONFIG['MAX_CONNECTIONS']), 'white')
    color_print(t("wt_ban_after", num=CONFIG['BAN_THRESHOLD']), 'white')
    print()
    color_print("-" * 49, 'cyan')
    input(t("wt_press_enter"))


def view_security_logs():
    clear_screen()
    print_header()
    color_print(t("wt_audit_title"), 'cyan')
    print()
    color_print("-" * 49, 'cyan')
    print()

    if not os.path.exists(AUDIT_LOG):
        color_print(t("wt_audit_missing"), 'yellow')
    else:
        try:
            with open(AUDIT_LOG, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if not lines:
                    color_print(t("wt_audit_empty"), 'yellow')
                else:
                    for line in lines[-50:]:
                        print(line.strip())
        except Exception as e:
            color_print(f"  Error: {e}", 'red')

    print()
    color_print("-" * 49, 'cyan')
    input(t("wt_press_enter"))


def view_upload_log():
    clear_screen()
    print_header()
    color_print(t("wt_upload_log_title"), 'cyan')
    print()
    color_print("-" * 49, 'cyan')
    print()

    if not os.path.exists(LOG_FILE):
        color_print(t("wt_upload_log_missing"), 'yellow')
    else:
        try:
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if not lines:
                    color_print(t("wt_upload_log_empty"), 'yellow')
                else:
                    for line in lines[-50:]:
                        print(line.strip())
        except Exception as e:
            color_print(f"  Error: {e}", 'red')

    print()
    color_print("-" * 49, 'cyan')
    input(t("wt_press_enter"))


def clear_log():
    clear_screen()
    color_print(t("wt_clear_log_title"), 'cyan')
    print()

    choice = input(t("wt_clear_log_q")).strip().lower()
    if choice in ('y', 'yes', 'д', 'да'):
        try:
            if os.path.exists(LOGS_DIR):
                shutil.rmtree(LOGS_DIR)
                os.makedirs(LOGS_DIR, mode=0o755, exist_ok=True)
                color_print(t("wt_clear_log_ok"), 'green')
            else:
                color_print(t("wt_clear_log_missing"), 'yellow')
        except Exception as e:
            color_print(f"  Error: {e}", 'red')

    input(t("wt_press_enter"))


def clear_files():
    clear_screen()
    print_header()
    color_print(t("wt_clear_files_title"), 'cyan')
    print()
    color_print(t("wt_clear_files_warn", path=shorten_path(FILES_DIR)), 'orange')
    print()

    choice = input(t("wt_clear_files_q")).strip().lower()
    if choice in ('y', 'yes', 'д', 'да'):
        try:
            if os.path.exists(FILES_DIR):
                shutil.rmtree(FILES_DIR)
                ensure_directories()
                color_print(t("wt_clear_files_ok"), 'green')
                log_message(t("wt_clear_files_log"), 'INFO')
            else:
                color_print(t("wt_clear_files_missing"), 'yellow')
        except Exception as e:
            color_print(f"  Error: {e}", 'red')

    input(t("wt_press_enter"))


def manage_blacklist():
    clear_screen()
    print_header()
    color_print(t("wt_black_title"), 'cyan')
    print()

    with security.rate_lock:
        banned = dict(security.banned_ips)

    if not banned:
        color_print(t("wt_black_empty"), 'green')
    else:
        color_print(t("wt_black_banned"), 'yellow')
        for ip, ban_time in banned.items():
            remaining = int(CONFIG['BAN_DURATION'] - (time.time() - ban_time))
            if remaining > 0:
                color_print(t("wt_black_rem", ip=ip, sec=remaining), 'red')
            else:
                color_print(t("wt_black_exp", ip=ip), 'yellow')

    print()
    color_print("-" * 49, 'cyan')
    choice = input(f"\n  [1] {t('wt_black_opt1').strip()[4:]}\n  [2] {t('wt_black_opt2').strip()[4:]}\n  {t('wt_black_sel').strip()}").strip()

    if choice == "1":
        with security.rate_lock:
            security.banned_ips.clear()
            security._save_blacklist()
        color_print(t("wt_black_cleared"), 'green')
        time.sleep(1)


def change_port():
    global CONFIG
    clear_screen()
    print_header()
    color_print(t("wt_port_title"), 'cyan')
    print()
    try:
        new_port_str = input(t("wt_port_prompt", port=CONFIG['PORT'])).strip()
        new_port = int(new_port_str if new_port_str else str(CONFIG['PORT']))
        if 1024 <= new_port <= 65535:
            CONFIG['PORT'] = new_port
            log_message(f"Port changed to {new_port}", 'INFO')
            color_print(t("wt_port_ok", port=new_port), 'green')
            input(t("wt_press_enter"))
            return CONFIG['PORT']
        else:
            color_print(t("wt_port_err"), 'red')
            input(t("wt_press_enter"))
            return CONFIG['PORT']
    except (ValueError, EOFError):
        color_print(t("wt_port_bad_in"), 'red')
        input(t("wt_press_enter"))
        return CONFIG['PORT']


def run_server():
    global CONFIG, STOP_SERVER, SERVER_INSTANCE
    STOP_SERVER = False
    SERVER_INSTANCE = None
    clear_screen()
    print_header()

    ensure_directories()
    security.rotate_token()

    ip = get_local_ip()
    port = CONFIG['PORT']

    print_status(ip, port, running=True)

    log_message(t("wt_srv_started", port=port), 'INFO')
    log_message(t("wt_pin_msg", token=security.get_token()), 'INFO')
    audit_log(f"Server started on {ip}:{port}", 'INFO')

    color_print(t("wt_run_pin_lbl"), 'yellow')
    color_print(f"     {security.get_token()}", 'cyan')
    color_print(t("wt_run_link", ip=ip, port=port), 'blue')
    color_print(t("wt_run_stop_hint"), 'orange')
    color_print("-" * 49, 'cyan')
    print()

    orig_cwd = os.getcwd()
    os.chdir(FILES_DIR)
    if HAVE_BACKGROUND:
        background.keep_alive()
        log_message(t("wt_bg_active"), 'INFO')

    SERVER_INSTANCE = ThreadedFastHTTPServer(('', port), SecureHTTPRequestHandler)

    try:
        SERVER_INSTANCE.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        log_message(t("wt_srv_stopped"), 'INFO')
        audit_log("Server stopped", 'INFO')
        if SERVER_INSTANCE:
            SERVER_INSTANCE.server_close()
            SERVER_INSTANCE = None
        try:
            os.chdir(orig_cwd)
        except Exception:
            pass

    color_print(t("wt_stopped_ret"), 'green')
    time.sleep(1)
    return


def interactive_menu():
    while True:
        clear_screen()
        print_header()

        cur_lang_display = get_lang().upper()

        color_print(t("wt_menu_title"), 'cyan')
        print()
        color_print(t("wt_m1"), 'white')
        color_print(t("wt_m2"), 'white')
        color_print(t("wt_m3"), 'white')
        color_print(t("wt_m4"), 'white')
        color_print(t("wt_m5"), 'white')
        color_print(t("wt_m6"), 'white')
        color_print(t("wt_m7"), 'white')
        color_print(t("wt_m8"), 'white')
        color_print(t("wt_m9"), 'white')
        color_print(t("wt_m10"), 'white')
        color_print(t("wt_m11"), 'orange')
        color_print(t("wt_m12", lang=cur_lang_display), 'white')
        color_print(t("wt_m0"), 'white')
        print()
        color_print("-" * 49, 'cyan')
        print()

        choice = input(t("wt_select")).strip()

        if choice == "1":
            run_server()
            continue
        elif choice == "2":
            show_security_info()
        elif choice == "3":
            show_ip()
        elif choice == "4":
            change_port()
        elif choice == "5":
            view_security_logs()
        elif choice == "6":
            view_upload_log()
        elif choice == "7":
            manage_blacklist()
        elif choice == "8":
            open_files_folder()
        elif choice == "9":
            new_token = security.rotate_token()
            color_print(f"  New PIN: {new_token}", 'green')
            time.sleep(2)
        elif choice == "10":
            clear_log()
        elif choice == "11":
            clear_files()
        elif choice == "12":
            new_lang = "en" if get_lang() == "ru" else "ru"
            set_lang(new_lang, persist=True)
            color_print(t("wt_lang_switched"), 'green')
            time.sleep(1)
        elif choice == "0":
            clear_screen()
            color_print(t("wt_goodbye"), 'cyan')
            print()
            sys.exit(0)
        else:
            color_print("  Invalid choice.", 'red')
            time.sleep(1)


def show_ip():
    clear_screen()
    print_header()
    ip = get_local_ip()
    color_print(t("wt_ip_title"), 'cyan')
    print()
    color_print(t("wt_ip_loc", ip=ip, port=CONFIG['PORT']), 'blue')
    color_print(t("wt_ip_host", port=CONFIG['PORT']), 'blue')
    print()
    color_print("-" * 49, 'cyan')
    input(t("wt_press_enter"))


def open_files_folder():
    clear_screen()
    print_header()
    color_print(t("wt_files_title"), 'cyan')
    print()
    color_print(f"  Path: {shorten_path(FILES_DIR)}", 'blue')
    print()
    color_print("-" * 49, 'cyan')
    print()

    try:
        files = []
        if os.path.exists(FILES_DIR):
            files = [f for f in os.listdir(FILES_DIR)
                     if os.path.isfile(os.path.join(FILES_DIR, f)) and not f.startswith('.')]

        if not files:
            color_print(t("wt_files_empty"), 'yellow')
        else:
            files.sort(key=lambda f: os.path.getmtime(os.path.join(FILES_DIR, f)), reverse=True)
            for idx, file in enumerate(files, 1):
                fpath = os.path.join(FILES_DIR, file)
                fsize = os.path.getsize(fpath) / 1024 / 1024
                mtime = datetime.datetime.fromtimestamp(os.path.getmtime(fpath)).strftime('%Y-%m-%d %H:%M')
                color_print(f"  [{idx}] {file} ({fsize:.2f} MB) - {mtime}", 'white')
    except Exception as e:
        color_print(f"  Error: {e}", 'red')

    print()
    color_print("-" * 49, 'cyan')
    input(t("wt_press_enter"))


def main():
    args = _parse_cli_args()
    init_i18n(lang=args.lang, persist=(args.lang is not None))
    ensure_directories()
    try:
        interactive_menu()
    except KeyboardInterrupt:
        clear_screen()
        color_print(t("wt_goodbye"), 'cyan')
        print()
        sys.exit(0)


if __name__ == '__main__':
    main()
