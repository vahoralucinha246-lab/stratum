
import os, json, threading, webbrowser
from flask import Flask, jsonify, request, make_response
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash

auth = HTTPBasicAuth()
app = Flask(__name__)

# 存储仪表盘数据
dashboard_data_cache = {}

# 从密码文件读取明文密码，生成哈希
def load_password():
    try:
        with open("panel_password.txt", "r") as f:
            pwd = f.read().strip()
        if pwd:
            return generate_password_hash(pwd)
    except:
        pass
    # 如果没找到密码文件，返回None，后续面板将无法通过验证
    return None

hashed_password = None

@auth.verify_password
def verify_password(username, password):
    global hashed_password
    if hashed_password is None:
        hashed_password = load_password()
    if hashed_password is None:
        # 没有设置密码，直接拒绝访问
        return False
    # 用户名随意，只要密码正确
    return check_password_hash(hashed_password, password)

@app.route("/")
@auth.login_required
def index():
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Stratum 思想地层仪表盘</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            color: #f0f0f0;
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            min-height: 100vh;
            padding: 2rem;
        }
        .dashboard-title {
            font-size: 2.5rem;
            font-weight: 300;
            letter-spacing: 2px;
            text-align: center;
            margin-bottom: 2rem;
            text-shadow: 0 0 20px rgba(100, 200, 255, 0.3);
        }
        .stat-card {
            background: rgba(255,255,255,0.08);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 1.5rem;
            transition: transform 0.2s;
            border: 1px solid rgba(255,255,255,0.1);
        }
        .stat-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        }
        .stat-value {
            font-size: 2.5rem;
            font-weight: bold;
            background: linear-gradient(45deg, #00d2ff, #3a7bd5);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .chart-container {
            background: rgba(255,255,255,0.05);
            border-radius: 20px;
            padding: 1rem;
            backdrop-filter: blur(10px);
        }
        .list-group-item {
            background: rgba(255,255,255,0.05);
            border: none;
            color: #ccc;
            margin-bottom: 0.5rem;
            border-radius: 10px;
        }
        .badge-glow {
            background: linear-gradient(45deg, #00d2ff, #3a7bd5);
            color: white;
            padding: 0.4em 0.8em;
            border-radius: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1 class="dashboard-title"><i class="fas fa-brain"></i> Stratum 思想地层</h1>
        <div class="row mb-4" id="stats-cards"></div>
        <div class="row mb-4">
            <div class="col-md-8">
                <div class="chart-container p-4">
                    <h5 class="mb-3"><i class="fas fa-chart-line"></i> 近期情绪波动</h5>
                    <canvas id="moodChart" height="200"></canvas>
                </div>
            </div>
            <div class="col-md-4">
                <div class="chart-container p-4 h-100">
                    <h5 class="mb-3"><i class="fas fa-cloud"></i> 情绪分布</h5>
                    <canvas id="sentimentDoughnut" height="200"></canvas>
                </div>
            </div>
        </div>
        <div class="row">
            <div class="col-md-6">
                <div class="chart-container p-4">
                    <h5 class="mb-3"><i class="fas fa-fire"></i> 高频观念</h5>
                    <div id="hot-concepts"></div>
                </div>
            </div>
            <div class="col-md-6">
                <div class="chart-container p-4">
                    <h5 class="mb-3"><i class="fas fa-code-branch"></i> 最新演化链</h5>
                    <div id="recent-chains"></div>
                </div>
            </div>
        </div>
    </div>

    <script>
        fetch('/data')
        .then(res => res.json())
        .then(data => {
            const stats = [
                { icon: 'atom', label: '观念原子', value: data.atom_count },
                { icon: 'link', label: '演化链', value: data.chain_count },
                { icon: 'comment', label: '对话记录', value: data.trace_count },
                { icon: 'smile', label: '平均情绪', value: data.avg_sentiment?.toFixed(2) || '0' }
            ];
            let statsHTML = '';
            stats.forEach(s => {
                statsHTML += `
                <div class="col-md-3 col-sm-6 mb-3">
                    <div class="stat-card text-center">
                        <i class="fas fa-${s.icon} fa-2x mb-2" style="color:#00d2ff"></i>
                        <div class="stat-value">${s.value}</div>
                        <div class="text-muted">${s.label}</div>
                    </div>
                </div>`;
            });
            document.getElementById('stats-cards').innerHTML = statsHTML;

            const moodData = data.mood_series || [];
            const labels = moodData.map(m => m.timestamp?.substring(0,10));
            const values = moodData.map(m => m.sentiment);
            const ctx = document.getElementById('moodChart').getContext('2d');
            new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        label: '情感值',
                        data: values,
                        borderColor: '#00d2ff',
                        backgroundColor: 'rgba(0,210,255,0.1)',
                        tension: 0.4,
                        fill: true,
                        pointRadius: 4,
                        pointBackgroundColor: '#fff'
                    }]
                },
                options: {
                    responsive: true,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { ticks: { color: '#aaa' }, grid: { color: 'rgba(255,255,255,0.1)' } },
                        y: { ticks: { color: '#aaa' }, grid: { color: 'rgba(255,255,255,0.1)' } }
                    }
                }
            });

            const pos = data.positive_count || 0;
            const neg = data.negative_count || 0;
            const neu = (data.atom_count || 0) - pos - neg;
            const dctx = document.getElementById('sentimentDoughnut').getContext('2d');
            new Chart(dctx, {
                type: 'doughnut',
                data: {
                    labels: ['正面', '负面', '中性'],
                    datasets: [{
                        data: [pos, neg, neu],
                        backgroundColor: ['#6f9', '#f66', '#aaa'],
                        borderWidth: 0
                    }]
                },
                options: {
                    responsive: true,
                    plugins: { legend: { labels: { color: '#ccc' } } }
                }
            });

            const hotConcepts = data.hot_concepts || [];
            let hotHTML = '<ul class="list-group">';
            hotConcepts.forEach(c => {
                hotHTML += `<li class="list-group-item d-flex justify-content-between align-items-center">
                    <span>${c.subject} ↔ ${c.object}</span>
                    <span class="badge-glow">${c.count}次</span>
                </li>`;
            });
            hotHTML += '</ul>';
            document.getElementById('hot-concepts').innerHTML = hotHTML;

            const chains = data.recent_chains || [];
            let chainHTML = '';
            chains.forEach(ch => {
                chainHTML += `<div class="list-group-item">
                    <strong>${ch.subject}</strong> → <strong>${ch.object}</strong>
                    <span class="float-end badge bg-secondary">${ch.relation_type}</span>
                    <br><small class="text-muted">${ch.detected_at}</small>
                </div>`;
            });
            document.getElementById('recent-chains').innerHTML = chainHTML;
        });
    </script>
</body>
</html>"""

@app.route("/data")
@auth.login_required
def data():
    return jsonify(dashboard_data_cache)

def start_dashboard(data: dict, port=5500):
    global dashboard_data_cache
    dashboard_data_cache = data
    threading.Thread(target=lambda: app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)).start()
    webbrowser.open(f"http://127.0.0.1:{port}/")

if __name__ == "__main__":
    # 测试用
    start_dashboard({"atom_count":10, "chain_count":2, "trace_count":50, "avg_sentiment":0.2, "mood_series":[], "positive_count":5, "negative_count":2, "hot_concepts":[], "recent_chains":[]})
