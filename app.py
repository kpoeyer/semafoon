import eventlet
eventlet.monkey_patch()

import os
import json
import signal
import datetime
from eventlet.green import subprocess
from flask import Flask, render_template_string
from flask_socketio import SocketIO

app = Flask(__name__)
app.config['SECRET_KEY'] = 'geheim_p2000_sleutel'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

sdr_process = None
current_freq = "169.650M"
is_running = False
keywords = []
capcodes = {}
raw_capcodes_str = ""

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "p2000_matches.log")
FILTER_FILE = os.path.join(BASE_DIR, "filters.json")

def load_filters():
    global keywords, capcodes, raw_capcodes_str
    if os.path.exists(FILTER_FILE):
        try:
            with open(FILTER_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                keywords = data.get("keywords", [])
                raw_capcodes_str = data.get("raw_capcodes", "")
                parse_capcodes(raw_capcodes_str)
        except Exception as e:
            print(f"Fout bij laden filters: {e}")

def save_filters():
    try:
        with open(FILTER_FILE, "w", encoding="utf-8") as f:
            json.dump({"keywords": keywords, "raw_capcodes": raw_capcodes_str}, f, indent=2)
    except Exception as e:
        print(f"Fout bij opslaan filters: {e}")

def parse_capcodes(raw_str):
    global capcodes
    capcodes = {}
    lines = raw_str.replace(',', '\n').split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if '=' in line:
            code, desc = line.split('=', 1)
            capcodes[code.strip()] = desc.strip()
        else:
            capcodes[line] = ""

HTML_PAGE = """
<!DOCTYPE html>
<html lang="nl" data-bs-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SDR Semafoon & P2000 Decoder</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
    <style>
        .log-box { height: 420px; overflow-y: scroll; background-color: #1e1e1e; font-family: monospace; font-size: 0.9rem; }
        .match-box { height: 220px; overflow-y: scroll; background-color: #2c1518; font-family: monospace; font-size: 0.9rem; }
        .msg-row { border-bottom: 1px solid #333; padding: 4px 8px; }
        .msg-sys { color: #0dcaf0; font-style: italic; }
        .msg-match { background-color: #dc3545 !important; color: white; font-weight: bold; }
        .time-badge { color: #888; margin-right: 10px; }
        textarea.cap-input { font-family: monospace; font-size: 0.85rem; }
    </style>
</head>
<body class="bg-body-tertiary">
<div class="container-fluid py-3">
    <div class="row mb-3">
        <div class="col-md-12 d-flex justify-content-between align-items-center">
            <h2>📻 P2000 & Semafoon Monitor</h2>
            <div>
                Status: <span id="status-badge" class="badge bg-secondary">Verbinden...</span>
                Frequentie: <span id="freq-badge" class="badge bg-info text-dark">-</span>
            </div>
        </div>
    </div>

    <div class="row mb-3 g-3">
        <div class="col-md-4">
            <div class="card h-100">
                <div class="card-header">📡 Frequentie Besturing</div>
                <div class="card-body">
                    <div class="btn-group w-100 mb-2" role="group">
                        <button type="button" class="btn btn-primary btn-sm" onclick="setFreq('169.650M')">🚨 P2000 (169.650)</button>
                        <button type="button" class="btn btn-info btn-sm" onclick="setFreq('172.450M')">📟 KPN (172.450)</button>
                        <button type="button" class="btn btn-danger btn-sm" onclick="stopSDR()">⏹️ Stop</button>
                    </div>
                    <div class="input-group input-group-sm mt-3">
                        <input type="text" id="custom-freq" class="form-control" placeholder="Handmatig (bijv. 169.800M)">
                        <button class="btn btn-outline-secondary" type="button" onclick="setCustomFreq()">Stel in</button>
                    </div>
                </div>
            </div>
        </div>

        <div class="col-md-4">
            <div class="card h-100">
                <div class="card-header">🔍 Zoekwoorden Filter</div>
                <div class="card-body">
                    <p class="small text-muted mb-1">Woorden gescheiden door een komma:</p>
                    <div class="input-group input-group-sm">
                        <input type="text" id="keyword-input" class="form-control" placeholder="Bijv: Prio 1, Brand, Reanimatie">
                        <button class="btn btn-success" type="button" onclick="updateKeywords()">Opslaan</button>
                    </div>
                    <div class="mt-2 small">
                        Actief: <span id="active-keywords" class="text-warning">Geen</span>
                    </div>
                </div>
            </div>
        </div>

        <div class="col-md-4">
            <div class="card h-100">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <span>🔢 CAP-code Filter (Lijst)</span>
                    <span id="cap-count" class="badge bg-warning text-dark">0 actief</span>
                </div>
                <div class="card-body p-2">
                    <textarea id="capcode-input" class="form-control cap-input mb-2" rows="3" placeholder="Één per regel of met komma. Optioneel met =Naam&#10;0120901=Traumaheli&#10;1400123=Brandweer"></textarea>
                    <button class="btn btn-success btn-sm w-100" type="button" onclick="updateCapcodes()">CAP-codes Opslaan</button>
                </div>
            </div>
        </div>
    </div>

    <div class="row mb-3">
        <div class="col-md-12">
            <div class="card border-danger">
                <div class="card-header bg-danger text-white d-flex justify-content-between">
                    <span>🔔 Gevonden Berichten (Matches op Woorden & CAP-codes -> <code>p2000_matches.log</code>)</span>
                    <button class="btn btn-sm btn-outline-light py-0" onclick="document.getElementById('match-container').innerHTML=''">Wis scherm</button>
                </div>
                <div class="card-body p-0 match-box" id="match-container"></div>
            </div>
        </div>
    </div>

    <div class="row">
        <div class="col-md-12">
            <div class="card">
                <div class="card-header d-flex justify-content-between">
                    <span>📡 Live Data Stream (Alle ontvangen berichten)</span>
                    <button class="btn btn-sm btn-outline-secondary py-0" onclick="document.getElementById('log-container').innerHTML=''">Wis scherm</button>
                </div>
                <div class="card-body p-0 log-box" id="log-container"></div>
            </div>
        </div>
    </div>
</div>

<script>
    const socket = io();

    socket.on('status_update', function(data) {
        const statusBadge = document.getElementById('status-badge');
        const freqBadge = document.getElementById('freq-badge');
        if(data.running) {
            statusBadge.className = 'badge bg-success';
            statusBadge.innerText = 'Ontvangt...';
        } else {
            statusBadge.className = 'badge bg-danger';
            statusBadge.innerText = 'Gestopt';
        }
        freqBadge.innerText = data.freq;
    });

    socket.on('keywords_update', function(data) {
        const kwSpan = document.getElementById('active-keywords');
        const kwInput = document.getElementById('keyword-input');
        if(data.keywords && data.keywords.length > 0) {
            kwSpan.innerText = data.keywords.join(', ');
            kwInput.value = data.keywords.join(', ');
        } else {
            kwSpan.innerText = 'Geen';
        }
    });

    socket.on('capcodes_update', function(data) {
        document.getElementById('capcode-input').value = data.raw_capcodes || '';
        document.getElementById('cap-count').innerText = (data.count || 0) + ' actief';
    });

    socket.on('new_message', function(msg) {
        const logContainer = document.getElementById('log-container');
        const matchContainer = document.getElementById('match-container');
        
        const div = document.createElement('div');
        div.className = 'msg-row';
        if (msg.match) div.classList.add('msg-match');
        if (msg.sys) div.classList.add('msg-sys');
        
        div.innerHTML = `<span class="time-badge">[${msg.time} | ${msg.freq}]</span> ${escapeHtml(msg.text)}`;
        logContainer.insertBefore(div, logContainer.firstChild);
        
        if(msg.match) {
            const matchDiv = div.cloneNode(true);
            matchDiv.classList.remove('msg-match');
            matchDiv.innerHTML = `<span class="badge bg-warning text-dark me-2">${escapeHtml(msg.match)}</span>` + matchDiv.innerHTML;
            matchContainer.insertBefore(matchDiv, matchContainer.firstChild);
        }

        if (logContainer.childElementCount > 200) {
            logContainer.removeChild(logContainer.lastChild);
        }
    });

    function setFreq(freq) {
        document.getElementById('status-badge').className = 'badge bg-warning text-dark';
        document.getElementById('status-badge').innerText = 'Schakelen...';
        socket.emit('change_freq', {freq: freq});
    }

    function setCustomFreq() {
        const freq = document.getElementById('custom-freq').value.trim();
        if(freq) setFreq(freq);
    }

    function stopSDR() { socket.emit('stop_sdr'); }

    function updateKeywords() {
        const kws = document.getElementById('keyword-input').value;
        socket.emit('update_keywords', {keywords: kws});
    }

    function updateCapcodes() {
        const caps = document.getElementById('capcode-input').value;
        socket.emit('update_capcodes', {capcodes: caps});
    }

    function escapeHtml(unsafe) {
        return unsafe.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
    }
</script>
</body>
</html>
"""

def log_to_file(message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")

def read_sdr_output():
    global sdr_process, is_running
    while is_running and sdr_process:
        try:
            line = sdr_process.stdout.readline()
            if not line:
                break
            decoded_line = line.decode('utf-8', errors='ignore').strip()
            if decoded_line and not decoded_line.startswith("multimon-ng") and not decoded_line.startswith("Available"):
                timestamp = datetime.datetime.now().strftime("%H:%M:%S")
                is_pager_msg = any(decoded_line.startswith(p) for p in ["FLEX", "POCSAG", "FSK"])
                matched_label = None
                if is_pager_msg:
                    for code, desc in capcodes.items():
                        if code.lower() in decoded_line.lower():
                            matched_label = f"CAP: {code} ({desc})" if desc else f"CAP: {code}"
                            break
                    for kw in keywords:
                        if kw.lower() in decoded_line.lower():
                            kw_label = f"Woord: {kw}"
                            matched_label = f"{matched_label} & {kw_label}" if matched_label else kw_label
                            break
                    if matched_label:
                        log_to_file(f"[{matched_label}] {decoded_line}")
                socketio.emit('new_message', {'time': timestamp, 'freq': current_freq, 'text': decoded_line, 'match': matched_label, 'sys': not is_pager_msg})
        except Exception as e:
            print(f"Leesfout: {e}")
            break
    if is_running:
        is_running = False
        socketio.emit('status_update', {'running': False, 'freq': current_freq})

def start_sdr(freq):
    global sdr_process, is_running, current_freq
    stop_sdr()
    os.system("killall -9 rtl_fm multimon-ng 2>/dev/null")
    eventlet.sleep(0.5)
    current_freq = freq
    cmd = f"rtl_fm -o 4 -A lut -s 22050 -f {freq} - | stdbuf -oL multimon-ng -t raw -a POCSAG512 -a POCSAG1200 -a POCSAG2400 -a FSK9600 -a FLEX -f alpha /dev/stdin"
    sdr_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True, preexec_fn=os.setsid)
    is_running = True
    socketio.emit('status_update', {'running': True, 'freq': current_freq})
    socketio.start_background_task(read_sdr_output)

def stop_sdr():
    global sdr_process, is_running
    is_running = False
    if sdr_process:
        try:
            os.killpg(os.getpgid(sdr_process.pid), signal.SIGTERM)
        except Exception:
            pass
        sdr_process = None
    os.system("killall -9 rtl_fm multimon-ng 2>/dev/null")
    socketio.emit('status_update', {'running': False, 'freq': current_freq})

@app.route('/')
def index():
    return render_template_string(HTML_PAGE)

@socketio.on('connect')
def handle_connect():
    socketio.emit('status_update', {'running': is_running, 'freq': current_freq})
    socketio.emit('keywords_update', {'keywords': keywords})
    socketio.emit('capcodes_update', {'raw_capcodes': raw_capcodes_str, 'count': len(capcodes)})

@socketio.on('change_freq')
def handle_change_freq(data):
    start_sdr(data.get('freq', '169.650M'))

@socketio.on('stop_sdr')
def handle_stop():
    stop_sdr()

@socketio.on('update_keywords')
def handle_keywords(data):
    global keywords
    keywords = [k.strip() for k in data.get('keywords', '').split(',') if k.strip()]
    save_filters()
    socketio.emit('keywords_update', {'keywords': keywords})

@socketio.on('update_capcodes')
def handle_capcodes(data):
    global raw_capcodes_str
    raw_capcodes_str = data.get('capcodes', '')
    parse_capcodes(raw_capcodes_str)
    save_filters()
    socketio.emit('capcodes_update', {'raw_capcodes': raw_capcodes_str, 'count': len(capcodes)})

if __name__ == '__main__':
    try:
        load_filters()
        print("Server wordt gestart op poort 5000...")
        start_sdr("169.650M")
        socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
    finally:
        stop_sdr()
