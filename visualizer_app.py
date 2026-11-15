"""
FinGuard Parallel Process Visualizer
A Flask web application to run multiple Python scripts in parallel and visualize their outputs.
"""

from flask import Flask, render_template_string, jsonify, request
import subprocess
import threading
import os

app = Flask(__name__)

# Store process outputs
process_outputs = {"process_1": [], "process_2": [], "process_3": []}
process_status = {"process_1": "idle", "process_2": "idle", "process_3": "idle"}
current_params = {}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <title>FinGuard - İşlem Monitörü</title>
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }
        
        body {
            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            min-height: 100vh;
            color: #e2e8f0;
            padding: 2rem;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        
        header {
            text-align: center;
            margin-bottom: 2rem;
        }
        
        header h1 {
            font-size: 2rem;
            font-weight: 700;
            color: #ffffff;
            margin-bottom: 0.5rem;
        }
        
        header p {
            color: #94a3b8;
            font-size: 0.95rem;
        }
        
        .input-panel {
            background: rgba(30, 41, 59, 0.8);
            border: 1px solid #334155;
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 2rem;
            backdrop-filter: blur(10px);
        }
        
        .input-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 1rem;
            margin-bottom: 1rem;
        }
        
        .input-group {
            display: flex;
            flex-direction: column;
        }
        
        .input-group label {
            font-size: 0.8rem;
            font-weight: 600;
            color: #94a3b8;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 0.5rem;
        }
        
        .input-group input[type="text"],
        .input-group input[type="date"] {
            background: #0f172a;
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 0.75rem 1rem;
            font-size: 0.95rem;
            color: #e2e8f0;
            transition: border-color 0.2s, box-shadow 0.2s;
        }
        
        .input-group input:focus {
            outline: none;
            border-color: #3b82f6;
            box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.2);
        }
        
        .input-group input::placeholder {
            color: #64748b;
        }
        
        .checkbox-row {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.5rem 0.75rem;
            background: rgba(59, 130, 246, 0.15);
            border-top: 1px solid #27272a;
        }
        
        .checkbox-row input[type="checkbox"] {
            width: 16px;
            height: 16px;
            accent-color: #3b82f6;
            cursor: pointer;
        }
        
        .checkbox-row label {
            font-size: 0.75rem;
            color: #94a3b8;
            cursor: pointer;
        }
        
        .terminals-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 1.5rem;
            margin-bottom: 2rem;
        }
        
        .terminal-card {
            background: #0a0a0a;
            border: 1px solid #27272a;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
        }
        
        .terminal-header {
            background: linear-gradient(to right, #18181b, #27272a);
            padding: 0.75rem 1rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #27272a;
        }
        
        .terminal-title {
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        
        .terminal-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: #52525b;
        }
        
        .terminal-dot.running {
            background: #fbbf24;
            animation: pulse 1.5s infinite;
        }
        
        .terminal-dot.completed {
            background: #22c55e;
        }
        
        .terminal-dot.error {
            background: #ef4444;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        .terminal-name {
            font-size: 0.85rem;
            font-weight: 600;
            color: #a1a1aa;
        }
        
        .terminal-status {
            font-size: 0.7rem;
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            text-transform: uppercase;
            font-weight: 600;
        }
        
        .terminal-status.idle {
            background: #27272a;
            color: #71717a;
        }
        
        .terminal-status.running {
            background: rgba(251, 191, 36, 0.2);
            color: #fbbf24;
        }
        
        .terminal-status.completed {
            background: rgba(34, 197, 94, 0.2);
            color: #22c55e;
        }
        
        .terminal-output {
            height: 250px;
            overflow-y: auto;
            padding: 1rem;
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 0.8rem;
            line-height: 1.5;
            color: #22c55e;
        }
        
        .terminal-output::-webkit-scrollbar {
            width: 6px;
        }
        
        .terminal-output::-webkit-scrollbar-track {
            background: #18181b;
        }
        
        .terminal-output::-webkit-scrollbar-thumb {
            background: #3f3f46;
            border-radius: 3px;
        }
        
        .actions-panel {
            display: flex;
            justify-content: center;
            gap: 1rem;
        }
        
        .btn {
            padding: 0.875rem 2rem;
            font-size: 0.95rem;
            font-weight: 600;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        
        .btn-primary {
            background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
            color: white;
            box-shadow: 0 4px 14px rgba(59, 130, 246, 0.4);
        }
        
        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(59, 130, 246, 0.5);
        }
        
        .btn-success {
            background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%);
            color: white;
            box-shadow: 0 4px 14px rgba(34, 197, 94, 0.4);
        }
        
        .btn-success:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(34, 197, 94, 0.5);
        }
        
        .btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none;
        }
        
        .progress-bar {
            margin-top: 1.5rem;
            background: #1e293b;
            border-radius: 8px;
            padding: 1rem;
        }
        
        .progress-track {
            height: 8px;
            background: #334155;
            border-radius: 4px;
            overflow: hidden;
        }
        
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #3b82f6, #22c55e);
            border-radius: 4px;
            width: 0%;
            transition: width 0.3s;
        }
        
        .progress-text {
            text-align: center;
            margin-top: 0.5rem;
            font-size: 0.85rem;
            color: #94a3b8;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🔍 FinGuard İşlem Monitörü</h1>
            <p>Paralel Python işlemlerini başlatın ve çıktıları gerçek zamanlı izleyin</p>
        </header>
        
        <div class="input-panel">
            <div class="input-grid">
                <div class="input-group">
                    <label>Başlangıç Tarihi</label>
                    <input type="date" id="startDate" value="2024-01-01">
                </div>
                <div class="input-group">
                    <label>Bitiş Tarihi</label>
                    <input type="date" id="endDate" value="2025-12-31">
                </div>
                <div class="input-group">
                    <label>Şirket Adı</label>
                    <input type="text" id="companyName" placeholder="Örn: Aselsan">
                </div>
                <div class="input-group">
                    <label>Ofis Konumu</label>
                    <input type="text" id="officeLocation" placeholder="Örn: Ankara">
                </div>
            </div>
        </div>
        
        <div class="terminals-grid">
            <div class="terminal-card">
                <div class="terminal-header">
                    <div class="terminal-title">
                        <div class="terminal-dot" id="dot1"></div>
                        <span class="terminal-name">İhale Tarayıcı</span>
                    </div>
                    <span class="terminal-status idle" id="status1">Bekliyor</span>
                </div>
                <div class="terminal-output" id="term1"></div>
            </div>
            
            <div class="terminal-card">
                <div class="terminal-header">
                    <div class="terminal-title">
                        <div class="terminal-dot" id="dot2"></div>
                        <span class="terminal-name">Sicil Tarayıcı</span>
                    </div>
                    <span class="terminal-status idle" id="status2">Bekliyor</span>
                </div>
                <div class="terminal-output" id="term2"></div>
            </div>
            
            <div class="terminal-card">
                <div class="terminal-header">
                    <div class="terminal-title">
                        <div class="terminal-dot" id="dot3"></div>
                        <span class="terminal-name">Haber Tarayıcı</span>
                    </div>
                    <span class="terminal-status idle" id="status3">Bekliyor</span>
                </div>
                <div class="terminal-output" id="term3"></div>
                <div class="checkbox-row">
                    <input type="checkbox" id="useLocalModel">
                    <label for="useLocalModel">Yerel Model Kullan (OpenAI yerine)</label>
                </div>
            </div>
        </div>
        
        <div class="progress-bar">
            <div class="progress-track">
                <div class="progress-fill" id="progressFill"></div>
            </div>
            <div class="progress-text" id="progressText">İşlem başlatılmadı</div>
        </div>
        
        <div class="actions-panel" style="margin-top: 1.5rem;">
            <button class="btn btn-primary" id="startBtn" onclick="startProcesses()">
                ▶ İşlemleri Başlat
            </button>
            <button class="btn btn-success" id="pdfBtn" onclick="generatePDF()" disabled>
                📄 PDF Oluştur
            </button>
        </div>
    </div>
    
    <script>
        let completedCount = 0;
        let pollInterval = null;
        
        function formatDateForScript(dateStr) {
            // Convert YYYY-MM-DD to DD.MM.YYYY
            const parts = dateStr.split('-');
            if (parts.length === 3) {
                return parts[2] + '.' + parts[1] + '.' + parts[0];
            }
            return dateStr;
        }
        
        function startProcesses() {
            const params = {
                'start-date': formatDateForScript(document.getElementById('startDate').value),
                'end-date': formatDateForScript(document.getElementById('endDate').value),
                'company-name': document.getElementById('companyName').value,
                'office-location': document.getElementById('officeLocation').value,
                'use-local-model': document.getElementById('useLocalModel').checked
            };
            
            // Validate inputs
            if (!params['company-name']) {
                alert('Lütfen şirket adı girin');
                return;
            }
            
            // Reset UI
            completedCount = 0;
            ['term1', 'term2', 'term3'].forEach(id => {
                document.getElementById(id).textContent = '';
            });
            updateProgress(0);
            document.getElementById('pdfBtn').disabled = true;
            document.getElementById('startBtn').disabled = true;
            
            // Start processes
            fetch('/start', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(params)
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'started') {
                    startPolling();
                }
            });
        }
        
        function startPolling() {
            pollInterval = setInterval(pollStatus, 500);
        }
        
        function pollStatus() {
            fetch('/status')
            .then(res => res.json())
            .then(data => {
                // Update terminals
                ['process_1', 'process_2', 'process_3'].forEach((proc, idx) => {
                    const termId = 'term' + (idx + 1);
                    const dotId = 'dot' + (idx + 1);
                    const statusId = 'status' + (idx + 1);
                    
                    const output = data.outputs[proc].join('\\n');
                    document.getElementById(termId).textContent = output;
                    document.getElementById(termId).scrollTop = document.getElementById(termId).scrollHeight;
                    
                    const status = data.status[proc];
                    const dot = document.getElementById(dotId);
                    const statusEl = document.getElementById(statusId);
                    
                    dot.className = 'terminal-dot ' + status;
                    statusEl.className = 'terminal-status ' + status;
                    
                    if (status === 'running') {
                        statusEl.textContent = 'Çalışıyor';
                    } else if (status === 'completed') {
                        statusEl.textContent = 'Tamamlandı';
                    } else if (status === 'error') {
                        statusEl.textContent = 'Hata';
                    }
                });
                
                // Count completed
                completedCount = Object.values(data.status).filter(s => s === 'completed').length;
                updateProgress(completedCount);
                
                // Check if all done
                if (completedCount === 3) {
                    clearInterval(pollInterval);
                    document.getElementById('pdfBtn').disabled = false;
                    document.getElementById('startBtn').disabled = false;
                }
            });
        }
        
        function updateProgress(count) {
            const percent = (count / 3) * 100;
            document.getElementById('progressFill').style.width = percent + '%';
            document.getElementById('progressText').textContent = 
                count === 0 ? 'İşlem başlatılıyor...' :
                count === 3 ? 'Tüm işlemler tamamlandı!' :
                count + '/3 işlem tamamlandı';
        }
        
        function generatePDF() {
            document.getElementById('pdfBtn').disabled = true;
            document.getElementById('pdfBtn').textContent = '⏳ PDF Oluşturuluyor...';
            
            fetch('/generate_pdf', {method: 'POST'})
            .then(res => res.json())
            .then(data => {
                document.getElementById('pdfBtn').textContent = '📄 PDF Oluştur';
                document.getElementById('pdfBtn').disabled = false;
                if (data.status === 'success') {
                    alert('PDF başarıyla oluşturuldu: ' + data.path);
                } else {
                    alert('PDF oluşturulurken hata: ' + data.error);
                }
            });
        }
    </script>
</body>
</html>
"""


def run_ihale_script(params):
    """Run ihale scanner script."""
    process_status["process_1"] = "running"
    process_outputs["process_1"] = []

    try:
        # Convert dates from DD.MM.YYYY to YYYY.MM.DD format
        from datetime import datetime
        start_date = params.get("start-date", "")
        end_date = params.get("end-date", "")
        
        if start_date:
            try:
                dt = datetime.strptime(start_date, "%d.%m.%Y")
                start_date = dt.strftime("%Y.%m.%d")
            except:
                pass
        
        if end_date:
            try:
                dt = datetime.strptime(end_date, "%d.%m.%Y")
                end_date = dt.strftime("%Y.%m.%d")
            except:
                pass
        
        cmd = [
            "python",
            "arama_motoru.py",
            "-i",
            params.get("company-name", ""),
            "-b",
            start_date,
            "-s",
            end_date,
        ]

        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True, 
            bufsize=1,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"}
        )

        for line in iter(process.stdout.readline, ""):
            process_outputs["process_1"].append(line.strip())

        process.wait()
        process_status["process_1"] = (
            "completed" if process.returncode == 0 else "error"
        )

    except Exception as e:
        process_outputs["process_1"].append(f"Error: {str(e)}")
        process_status["process_1"] = "error"


def run_sicil_script(params):
    """Run sicil scanner script with office-location."""
    process_status["process_2"] = "running"
    process_outputs["process_2"] = []

    try:
        # Convert dates from DD.MM.YYYY to YYYY-MM-DD
        from datetime import datetime
        start_date = params.get("start-date", "")
        end_date = params.get("end-date", "")
        
        if start_date:
            try:
                start_date = datetime.strptime(start_date, "%d.%m.%Y").strftime("%Y-%m-%d")
            except:
                pass
        
        if end_date:
            try:
                end_date = datetime.strptime(end_date, "%d.%m.%Y").strftime("%Y-%m-%d")
            except:
                pass
        
        cmd = [
            "python",
            "trade_registry/ticaret_sicil_scraper.py",
            "--office",
            params.get("office-location", ""),
            "--title",
            params.get("company-name", ""),
            "--start-date",
            start_date,
            "--end-date",
            end_date,
        ]

        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
        )

        for line in iter(process.stdout.readline, ""):
            process_outputs["process_2"].append(line.strip())

        process.wait()
        process_status["process_2"] = (
            "completed" if process.returncode == 0 else "error"
        )

    except Exception as e:
        process_outputs["process_2"].append(f"Error: {str(e)}")
        process_status["process_2"] = "error"


def run_news_script(params):
    """Run news scanner script with optional --uselocalmodel flag."""
    process_status["process_3"] = "running"
    process_outputs["process_3"] = []

    try:
        cmd = [
            "python",
            "run_all_parts.py",
            "--start-date",
            params.get("start-date", ""),
            "--end-date",
            params.get("end-date", ""),
            "--company-name",
            params.get("company-name", ""),
        ]

        # Add --uselocalmodel if checkbox was checked
        if params.get("use-local-model", False):
            cmd.append("--uselocalmodel")

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            cwd="news_sentiment",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )

        for line in iter(process.stdout.readline, b""):
            try:
                decoded_line = line.decode("utf-8", errors="replace").strip()
            except:
                decoded_line = line.decode("latin-1", errors="replace").strip()
            process_outputs["process_3"].append(decoded_line)

        process.wait()
        process_status["process_3"] = (
            "completed" if process.returncode == 0 else "error"
        )

    except Exception as e:
        process_outputs["process_3"].append(f"Error: {str(e)}")
        process_status["process_3"] = "error"


@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/start", methods=["POST"])
def start_processes():
    global current_params
    current_params = request.json

    # Reset outputs
    for key in process_outputs:
        process_outputs[key] = []
        process_status[key] = "idle"

    # Start each script in its own thread
    thread1 = threading.Thread(target=run_ihale_script, args=(current_params,))
    thread2 = threading.Thread(target=run_sicil_script, args=(current_params,))
    thread3 = threading.Thread(target=run_news_script, args=(current_params,))

    thread1.daemon = True
    thread2.daemon = True
    thread3.daemon = True

    thread1.start()
    thread2.start()
    thread3.start()

    return jsonify({"status": "started"})


@app.route("/status")
def get_status():
    return jsonify({"outputs": process_outputs, "status": process_status})


@app.route("/generate_pdf", methods=["POST"])
def generate_pdf():
    try:
        cmd = [
            "python",
            "report/generator.py",
            "--start-date",
            current_params.get("start-date", ""),
            "--end-date",
            current_params.get("end-date", ""),
            "--company-name",
            current_params.get("company-name", ""),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            return jsonify({"status": "success", "path": "Final_Report.html"})
        else:
            return jsonify({"status": "error", "error": result.stderr})

    except Exception as e:
        return jsonify({"status": "error", "error": str(e)})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
