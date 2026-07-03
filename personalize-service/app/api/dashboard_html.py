DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BDC Lakehouse Control Center</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #080c14;
            --card-bg: rgba(17, 24, 39, 0.7);
            --card-hover: rgba(26, 36, 57, 0.85);
            --border-color: rgba(255, 255, 255, 0.08);
            --border-hover: rgba(99, 102, 241, 0.4);
            --text-primary: #f3f4f6;
            --text-secondary: #9ca3af;
            --text-muted: #6b7280;
            --primary: #6366f1;
            --primary-hover: #4f46e5;
            --primary-glow: rgba(99, 102, 241, 0.15);
            --accent-blue: #3b82f6;
            --accent-green: #10b981;
            --accent-red: #ef4444;
            --accent-orange: #f59e0b;
            --accent-purple: #8b5cf6;
            --accent-cyan: #06b6d4;
            --font-main: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            --font-mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Monaco, monospace;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            background-color: var(--bg-color);
            background-image: 
                radial-gradient(at 10% 10%, rgba(99, 102, 241, 0.08) 0px, transparent 50%),
                radial-gradient(at 90% 10%, rgba(6, 182, 212, 0.08) 0px, transparent 50%),
                radial-gradient(at 50% 90%, rgba(139, 92, 246, 0.05) 0px, transparent 50%);
            background-attachment: fixed;
            color: var(--text-primary);
            font-family: var(--font-main);
            min-height: 100vh;
            padding: 2rem 1.5rem;
            line-height: 1.5;
            -webkit-font-smoothing: antialiased;
        }

        /* Custom Scrollbar */
        ::-webkit-scrollbar {
            width: 8px;
            height: 8px;
        }
        ::-webkit-scrollbar-track {
            background: #080c14;
        }
        ::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.1);
            border-radius: 4px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: rgba(99, 102, 241, 0.5);
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            display: flex;
            flex-direction: column;
            gap: 1.5rem;
        }

        /* --- Header --- */
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1.5rem;
            background: var(--card-bg);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            box-shadow: 0 4px 30px rgba(0, 0, 0, 0.4);
            position: relative;
            overflow: hidden;
        }

        header::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 2px;
            background: linear-gradient(90deg, var(--primary), var(--accent-cyan));
        }

        .logo-group {
            display: flex;
            align-items: center;
            gap: 1rem;
        }

        .logo-icon {
            font-size: 2.2rem;
            background: linear-gradient(135deg, var(--primary), var(--accent-cyan));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            filter: drop-shadow(0 2px 8px rgba(99, 102, 241, 0.4));
            animation: pulse 3s infinite alternate;
        }

        h1 {
            font-size: 1.5rem;
            font-weight: 800;
            color: #ffffff;
            letter-spacing: -0.02em;
        }

        .subtitle {
            font-size: 0.8rem;
            color: var(--text-secondary);
            font-weight: 500;
            margin-top: 0.15rem;
        }

        .auth-badge {
            display: flex;
            align-items: center;
            gap: 0.6rem;
            background: rgba(255, 255, 255, 0.03);
            padding: 0.5rem 1.25rem;
            border-radius: 9999px;
            border: 1px solid var(--border-color);
            font-size: 0.75rem;
            font-weight: 600;
            color: #ffffff;
            transition: all 0.2s ease;
        }

        .auth-badge.connected {
            border-color: rgba(16, 185, 129, 0.3);
            background: rgba(16, 185, 129, 0.05);
        }

        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background-color: var(--accent-red);
            box-shadow: 0 0 8px var(--accent-red);
            transition: all 0.3s ease;
        }

        .status-dot.active {
            background-color: var(--accent-green);
            box-shadow: 0 0 12px var(--accent-green);
            animation: breathe 2s infinite alternate;
        }

        /* --- Stats Grid --- */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 1.25rem;
        }

        .stat-card {
            background: var(--card-bg);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.5rem;
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
        }

        .stat-card:hover {
            transform: translateY(-4px);
            border-color: var(--border-hover);
            box-shadow: 0 10px 30px rgba(99, 102, 241, 0.15);
        }

        .stat-label {
            font-size: 0.75rem;
            font-weight: 700;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.1em;
        }

        .stat-value {
            font-size: 2.25rem;
            font-weight: 800;
            color: #ffffff;
            font-family: var(--font-mono);
            background: linear-gradient(135deg, #ffffff 30%, var(--text-secondary));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .stat-desc {
            font-size: 0.75rem;
            color: var(--text-muted);
        }

        .stat-card::after {
            content: '';
            position: absolute;
            bottom: 0;
            left: 10%;
            width: 80%;
            height: 1px;
            background: linear-gradient(90deg, transparent, rgba(99, 102, 241, 0.2), transparent);
        }

        /* --- Controls & Configuration --- */
        .controls-grid {
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 1.25rem;
        }

        @media (max-width: 900px) {
            .controls-grid {
                grid-template-columns: 1fr;
            }
        }

        .panel-card {
            background: var(--card-bg);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.5rem;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }

        .panel-title {
            font-size: 0.85rem;
            font-weight: 700;
            color: #ffffff;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            padding-bottom: 0.6rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .button-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.875rem;
        }

        .input-group {
            display: flex;
            gap: 0.5rem;
        }

        .input-field {
            flex: 1;
            padding: 0.6rem 1rem;
            border-radius: 10px;
            border: 1px solid var(--border-color);
            background: rgba(0, 0, 0, 0.3);
            color: #ffffff;
            font-size: 0.875rem;
            transition: all 0.2s ease;
        }

        .input-field:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.25);
            background: rgba(0, 0, 0, 0.5);
        }

        .btn {
            background: linear-gradient(135deg, var(--primary), var(--primary-hover));
            color: #ffffff;
            border: none;
            padding: 0.6rem 1.25rem;
            font-size: 0.875rem;
            font-weight: 600;
            border-radius: 10px;
            cursor: pointer;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 0.5rem;
            box-shadow: 0 4px 12px rgba(99, 102, 241, 0.25);
        }

        .btn:hover {
            transform: translateY(-1px);
            box-shadow: 0 6px 16px rgba(99, 102, 241, 0.4);
            filter: brightness(1.1);
        }

        .btn:active {
            transform: translateY(1px);
        }

        .btn.secondary {
            background: rgba(255, 255, 255, 0.05);
            color: #ffffff;
            border: 1px solid var(--border-color);
            box-shadow: none;
        }

        .btn.secondary:hover {
            background: rgba(255, 255, 255, 0.1);
            border-color: rgba(255, 255, 255, 0.2);
            box-shadow: none;
        }

        /* --- Main Data Explorer --- */
        .explorer-card {
            background: var(--card-bg);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }

        .explorer-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1.25rem 1.5rem;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            background: rgba(0, 0, 0, 0.2);
            flex-wrap: wrap;
            gap: 1.25rem;
        }

        .tabs-container {
            display: flex;
            gap: 0.35rem;
            background: rgba(0, 0, 0, 0.3);
            padding: 0.3rem;
            border-radius: 10px;
            border: 1px solid var(--border-color);
        }

        .tab-item {
            background: transparent;
            border: none;
            color: var(--text-secondary);
            padding: 0.5rem 1.15rem;
            font-size: 0.825rem;
            font-weight: 600;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s ease;
        }

        .tab-item:hover {
            color: #ffffff;
            background: rgba(255, 255, 255, 0.02);
        }

        .tab-item.active {
            background: var(--primary);
            color: #ffffff;
            box-shadow: 0 2px 8px rgba(99, 102, 241, 0.3);
        }

        .search-bar {
            display: flex;
            align-items: center;
            gap: 1rem;
            flex-wrap: wrap;
        }

        /* --- Table Styling --- */
        .table-container {
            position: relative;
            overflow-x: auto;
            min-height: 350px;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            text-align: left;
            font-size: 0.875rem;
        }

        th {
            background: rgba(0, 0, 0, 0.15);
            color: var(--text-secondary);
            font-weight: 700;
            text-transform: uppercase;
            font-size: 0.725rem;
            letter-spacing: 0.08em;
            padding: 1rem 1.5rem;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }

        td {
            padding: 1rem 1.5rem;
            border-bottom: 1px solid rgba(255, 255, 255, 0.03);
            color: var(--text-primary);
            font-weight: 400;
            vertical-align: middle;
        }

        tr:last-child td {
            border-bottom: none;
        }

        tr:hover td {
            background-color: rgba(255, 255, 255, 0.015);
        }

        .mono-val {
            font-family: var(--font-mono);
            font-size: 0.8rem;
            background: rgba(255, 255, 255, 0.04);
            padding: 0.2rem 0.5rem;
            border-radius: 6px;
            color: var(--accent-cyan);
            border: 1px solid rgba(255, 255, 255, 0.03);
        }

        /* --- Badges --- */
        .badge {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 600;
        }

        /* Alert Types */
        .badge.alert-concept_struggle {
            background-color: rgba(239, 68, 68, 0.1);
            color: var(--accent-red);
            border: 1px solid rgba(239, 68, 68, 0.2);
        }

        .badge.alert-low_performance {
            background-color: rgba(245, 158, 11, 0.1);
            color: var(--accent-orange);
            border: 1px solid rgba(245, 158, 11, 0.2);
        }

        .badge.alert-inactivity {
            background-color: rgba(107, 114, 128, 0.1);
            color: var(--text-secondary);
            border: 1px solid rgba(107, 114, 128, 0.2);
        }

        .badge.alert-positive_reinforcement {
            background-color: rgba(16, 185, 129, 0.1);
            color: var(--accent-green);
            border: 1px solid rgba(16, 185, 129, 0.2);
        }

        .badge.alert-ai_suggestion {
            background-color: rgba(139, 92, 246, 0.1);
            color: var(--accent-purple);
            border: 1px solid rgba(139, 92, 246, 0.2);
        }

        .badge.alert-flashcard_suggestion {
            background-color: rgba(59, 130, 246, 0.1);
            color: var(--accent-blue);
            border: 1px solid rgba(59, 130, 246, 0.2);
        }

        /* Learning Styles */
        .badge.style-ai {
            background-color: rgba(139, 92, 246, 0.1);
            color: var(--accent-purple);
            border: 1px solid rgba(139, 92, 246, 0.25);
            box-shadow: 0 0 10px rgba(139, 92, 246, 0.1);
        }

        .badge.style-flashcard {
            background-color: rgba(59, 130, 246, 0.1);
            color: var(--accent-blue);
            border: 1px solid rgba(59, 130, 246, 0.25);
        }

        .badge.style-practice {
            background-color: rgba(16, 185, 129, 0.1);
            color: var(--accent-green);
            border: 1px solid rgba(16, 185, 129, 0.25);
        }

        .badge.style-theory {
            background-color: rgba(6, 182, 212, 0.1);
            color: var(--accent-cyan);
            border: 1px solid rgba(6, 182, 212, 0.25);
        }

        /* Engagement Levels */
        .badge.level-high {
            background-color: rgba(16, 185, 129, 0.12);
            color: var(--accent-green);
            border: 1px solid rgba(16, 185, 129, 0.3);
            position: relative;
            padding-left: 1.5rem;
        }

        .badge.level-high::before {
            content: '';
            position: absolute;
            left: 0.6rem;
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background-color: var(--accent-green);
            box-shadow: 0 0 8px var(--accent-green);
            animation: pulse-dot 1.5s infinite alternate;
        }

        .badge.level-mid {
            background-color: rgba(99, 102, 241, 0.12);
            color: var(--primary);
            border: 1px solid rgba(99, 102, 241, 0.3);
        }

        .badge.level-low {
            background-color: rgba(245, 158, 11, 0.12);
            color: var(--accent-orange);
            border: 1px solid rgba(245, 158, 11, 0.3);
        }

        /* Accuracy badges */
        .accuracy-pill {
            padding: 0.2rem 0.5rem;
            border-radius: 6px;
            font-weight: 700;
            font-family: var(--font-mono);
            font-size: 0.8rem;
        }
        .accuracy-pill.high { color: var(--accent-green); background: rgba(16, 185, 129, 0.08); }
        .accuracy-pill.mid { color: var(--accent-orange); background: rgba(245, 158, 11, 0.08); }
        .accuracy-pill.low { color: var(--accent-red); background: rgba(239, 68, 68, 0.08); }

        /* Struggle progress bar */
        .progress-bar-container {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            min-width: 150px;
        }

        .progress-bar {
            flex: 1;
            height: 6px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 3px;
            overflow: hidden;
            border: 1px solid rgba(255, 255, 255, 0.02);
        }

        .progress-fill {
            height: 100%;
            border-radius: 3px;
            transition: width 0.5s ease;
        }

        .progress-fill.high {
            background: linear-gradient(90deg, var(--accent-orange), var(--accent-red));
            box-shadow: 0 0 8px rgba(239, 68, 68, 0.5);
        }

        .progress-fill.low {
            background: linear-gradient(90deg, #818cf8, var(--primary));
        }

        .recommendation-chip {
            font-style: italic;
            font-size: 0.825rem;
            color: var(--text-secondary);
            border-left: 2px solid var(--primary);
            padding-left: 0.5rem;
            line-height: 1.3;
        }

        /* Loading & Empty State */
        .loading-overlay {
            position: absolute;
            inset: 0;
            background: rgba(8, 12, 20, 0.8);
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 10;
            backdrop-filter: blur(4px);
        }

        .spinner {
            width: 40px;
            height: 40px;
            border: 3px solid rgba(255, 255, 255, 0.05);
            border-top-color: var(--primary);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            box-shadow: 0 0 15px rgba(99, 102, 241, 0.2);
        }

        .empty-state {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 5rem 2rem;
            text-align: center;
            color: var(--text-secondary);
            gap: 1rem;
        }

        .empty-icon {
            font-size: 3rem;
            filter: drop-shadow(0 4px 12px rgba(99, 102, 241, 0.15));
            animation: float 4s infinite ease-in-out;
        }

        #emptyText {
            max-width: 450px;
            font-size: 0.9rem;
            color: var(--text-secondary);
        }

        /* Toast notifications */
        .toast-container {
            position: fixed;
            bottom: 2rem;
            right: 2rem;
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
            z-index: 999;
        }

        .toast {
            background: rgba(17, 24, 39, 0.9);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border-color);
            border-left: 4px solid var(--primary);
            border-radius: 10px;
            padding: 0.9rem 1.5rem;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
            display: flex;
            align-items: center;
            gap: 0.75rem;
            font-size: 0.875rem;
            font-weight: 600;
            color: #ffffff;
            transform: translateY(20px);
            opacity: 0;
            transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
        }

        .toast.show {
            transform: translateY(0);
            opacity: 1;
        }

        .toast.success { border-left-color: var(--accent-green); }
        .toast.error { border-left-color: var(--accent-red); }
        .toast.info { border-left-color: var(--accent-blue); }

        /* --- Animations --- */
        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        @keyframes pulse {
            from { filter: drop-shadow(0 2px 4px rgba(99, 102, 241, 0.3)); }
            to { filter: drop-shadow(0 2px 12px rgba(6, 182, 212, 0.5)); }
        }

        @keyframes breathe {
            from { opacity: 0.6; }
            to { opacity: 1; }
        }

        @keyframes pulse-dot {
            from { transform: scale(0.8); opacity: 0.6; }
            to { transform: scale(1.2); opacity: 1; }
        }

        @keyframes float {
            0% { transform: translateY(0px); }
            50% { transform: translateY(-10px); }
            100% { transform: translateY(0px); }
        }
    </style>
</head>
<body>
    <script>
        window.addEventListener('error', function(e) {
            const errDiv = document.createElement('div');
            errDiv.style.cssText = 'position:fixed;top:0;left:0;width:100%;background:#ef4444;color:#fff;padding:12px;z-index:99999;font-family:monospace;font-size:13px;font-weight:bold;box-shadow:0 4px 15px rgba(0,0,0,0.5);text-align:center;';
            errDiv.innerHTML = '🚨 JS ERROR: ' + e.message + ' at ' + e.filename + ':' + e.lineno + ':' + e.colno;
            document.body.appendChild(errDiv);
        });
    </script>
    <div class="container">
        <!-- Header -->
        <header>
            <div class="logo-group">
                <div class="logo-icon">📊</div>
                <div>
                    <h1>BDC Lakehouse Control Center</h1>
                    <div class="subtitle">DuckDB Student Analytics & Personalization Ledger</div>
                </div>
            </div>
            <div class="auth-badge" id="authBadge">
                <div id="authDot" class="status-dot"></div>
                <span id="authText">API Disconnected (JS Pending)</span>
            </div>
        </header>

        <!-- Stats row -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Total Student Metrics</div>
                <div id="statStudents" class="stat-value">--</div>
                <div class="stat-desc">Unique user-course records in Gold layer</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Active Concept Struggles</div>
                <div id="statStruggles" class="stat-value">--</div>
                <div class="stat-desc">Concepts failed on Quick Checks</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Active Study Alerts</div>
                <div id="statAlerts" class="stat-value">--</div>
                <div class="stat-desc">Dynamic personalized triggers needing attention</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Archived Partition Status</div>
                <div id="statStorage" class="stat-value">Active</div>
                <div class="stat-desc">Bronze Parquet partitions in storage</div>
            </div>
        </div>

        <!-- Controls grid -->
        <div class="controls-grid">
            <div class="panel-card">
                <div class="panel-title">🛠️ Lakehouse Operations</div>
                <div class="button-row">
                    <button id="btnRefresh" class="btn" onclick="loadAllData()">
                        🔄 Refresh Data
                    </button>
                    <button id="btnExport" class="btn secondary" onclick="triggerServerExport()">
                        📦 Export Server Parquet
                    </button>
                    <button id="btnCSV" class="btn secondary" onclick="downloadActiveCSV()">
                        📥 Download Local CSV
                    </button>
                </div>
            </div>
            <div class="panel-card">
                <div class="panel-title">🔑 Access Authentication</div>
                <div class="input-group">
                    <input type="password" id="secretKey" class="input-field" placeholder="Enter X-AI-Secret token...">
                    <button class="btn" onclick="saveSecretKey()">Save</button>
                </div>
            </div>
        </div>

        <!-- Explorer panel -->
        <div class="explorer-card">
            <div class="explorer-header">
                <div class="tabs-container">
                    <button class="tab-item active" onclick="switchTab('student-metrics', this)">Metrics</button>
                    <button class="tab-item" onclick="switchTab('concept-struggles', this)">Struggles</button>
                    <button class="tab-item" onclick="switchTab('interaction-matrix', this)">Matrix</button>
                    <button class="tab-item" onclick="switchTab('struggle-alerts', this)">Alerts</button>
                </div>
                <div class="search-bar">
                    <input type="text" id="tableSearch" class="input-field" style="max-width: 400px;" placeholder="🔍 Search records..." oninput="filterTable()">
                    <div id="tableCount" class="stat-desc">Showing 0 rows</div>
                </div>
            </div>

            <div class="table-container">
                <div id="loadingOverlay" class="loading-overlay">
                    <div class="spinner"></div>
                </div>
                <table>
                    <thead id="tableHead"></thead>
                    <tbody id="tableBody"></tbody>
                </table>
                <div id="emptyState" class="empty-state">
                    <div class="empty-icon">📂</div>
                    <div id="emptyText">Please configure your X-AI-Secret token and refresh to load the Lakehouse.</div>
                </div>
            </div>
        </div>
    </div>

    <!-- Toast container -->
    <div class="toast-container" id="toastContainer"></div>

    <script>
        console.log("BDC Dashboard Script Tag Executing...");
        // State
        let activeTab = 'student-metrics';
        let tableData = [];
        let secretKey = '';

        // Initialize on load
        function initializeDashboard() {
            // Load key from LocalStorage or URL params
            const urlParams = new URLSearchParams(window.location.search);
            const urlSecret = urlParams.get('secret');
            
            if (urlSecret) {
                secretKey = urlSecret;
                try {
                    localStorage.setItem('bdc_ai_secret', secretKey);
                } catch (e) {
                    console.warn('LocalStorage is blocked. Key loaded in memory for this session.', e);
                }
                const secretInput = document.getElementById('secretKey');
                if (secretInput) {
                    secretInput.value = secretKey;
                }
                
                // Clean URL safely
                try {
                    window.history.replaceState({}, document.title, window.location.pathname);
                } catch (e) {
                    console.warn('Could not clean secret from address bar history.', e);
                }
            } else {
                try {
                    secretKey = localStorage.getItem('bdc_ai_secret') || '';
                } catch (e) {
                    console.warn('LocalStorage is blocked. Please enter secret manually.', e);
                }
                const secretInput = document.getElementById('secretKey');
                if (secretInput) {
                    secretInput.value = secretKey;
                }
            }

            updateAuthStatus();
            if (secretKey) {
                loadAllData();
            }
        }

        // Initialize immediately if DOM is already ready
        if (document.readyState === 'complete' || document.readyState === 'interactive') {
            initializeDashboard();
        } else {
            window.addEventListener('DOMContentLoaded', initializeDashboard);
        }

        function saveSecretKey() {
            const inputVal = document.getElementById('secretKey').value.trim();
            secretKey = inputVal;
            try {
                localStorage.setItem('bdc_ai_secret', secretKey);
            } catch (e) {
                console.warn('Failed to save to localStorage:', e);
            }
            updateAuthStatus();
            showToast('API Key saved successfully', 'success');
            loadAllData();
        }

        function updateAuthStatus() {
            const dot = document.getElementById('authDot');
            const text = document.getElementById('authText');
            const badge = document.getElementById('authBadge');
            if (!dot || !text || !badge) return;
            if (secretKey) {
                dot.classList.add('active');
                text.innerText = 'Authenticated';
                badge.classList.add('connected');
            } else {
                dot.classList.remove('active');
                text.innerText = 'API Key Required';
                badge.classList.remove('connected');
            }
        }

        function getHeaders() {
            return {
                'Content-Type': 'application/json',
                'X-AI-Secret': secretKey
            };
        }

        // Alert helper
        function showToast(message, type = 'info') {
            const container = document.getElementById('toastContainer');
            const toast = document.createElement('div');
            toast.className = `toast ${type}`;
            toast.innerHTML = `<span>${type === 'success' ? '✅' : type === 'error' ? '❌' : 'ℹ️'}</span><span>${message}</span>`;
            container.appendChild(toast);
            
            // Trigger animation
            setTimeout(() => toast.classList.add('show'), 10);
            
            // Remove after 4s
            setTimeout(() => {
                toast.classList.remove('show');
                setTimeout(() => toast.remove(), 400);
            }, 4000);
        }

        // Switch table tab
        function switchTab(tabName, element) {
            document.querySelectorAll('.tab-item').forEach(btn => btn.classList.remove('active'));
            element.classList.add('active');
            activeTab = tabName;
            document.getElementById('tableSearch').value = '';
            renderTable();
        }

        // Fetch data wrapper
        async function fetchAPI(endpoint) {
            const response = await fetch(endpoint, {
                method: 'GET',
                headers: getHeaders()
            });
            if (response.status === 401) {
                throw new Error('Unauthorized: X-AI-Secret is invalid');
            }
            if (!response.ok) {
                throw new Error(`Server returned code ${response.status}`);
            }
            return await response.json();
        }

        // Load metrics for dashboard
        async function loadAllData() {
            if (!secretKey) {
                showToast('Please configure X-AI-Secret key first', 'error');
                return;
            }

            const loader = document.getElementById('loadingOverlay');
            loader.style.display = 'flex';
            document.getElementById('emptyState').style.display = 'none';

            try {
                const metricsUrl = '/personalize/analytics/gold/student-metrics';
                const strugglesUrl = '/personalize/analytics/gold/concept-struggles';
                const matrixUrl = '/personalize/analytics/gold/interaction-matrix';
                const alertsUrl = '/personalize/analytics/gold/struggle-alerts';

                const [metrics, struggles, matrix, alerts] = await Promise.all([
                    fetchAPI(metricsUrl).catch(e => { if (e.message && e.message.includes('Unauthorized')) throw e; console.error(e); return []; }),
                    fetchAPI(strugglesUrl).catch(e => { if (e.message && e.message.includes('Unauthorized')) throw e; console.error(e); return []; }),
                    fetchAPI(matrixUrl).catch(e => { if (e.message && e.message.includes('Unauthorized')) throw e; console.error(e); return []; }),
                    fetchAPI(alertsUrl).catch(e => { if (e.message && e.message.includes('Unauthorized')) throw e; console.error(e); return []; })
                ]);

                // Update Overview Cards
                document.getElementById('statStudents').innerText = metrics.length;
                document.getElementById('statStruggles').innerText = struggles.length;
                document.getElementById('statAlerts').innerText = alerts.length;

                // Cache active table data
                window.cachedData = {
                    'student-metrics': metrics,
                    'concept-struggles': struggles,
                    'interaction-matrix': matrix,
                    'struggle-alerts': alerts
                };

                showToast('Lakehouse data loaded successfully', 'success');
                renderTable();

            } catch (error) {
                console.error(error);
                showToast(error.message, 'error');
                document.getElementById('emptyState').style.display = 'flex';
                document.getElementById('emptyText').innerText = `Error: ${error.message}. Please verify your key and network connection.`;
            } finally {
                loader.style.display = 'none';
            }
        }

        // Render tables dynamically
        function renderTable() {
            const tableHead = document.getElementById('tableHead');
            const tableBody = document.getElementById('tableBody');
            const emptyState = document.getElementById('emptyState');
            
            tableHead.innerHTML = '';
            tableBody.innerHTML = '';

            tableData = (window.cachedData && window.cachedData[activeTab]) || [];

            if (tableData.length === 0) {
                emptyState.style.display = 'flex';
                document.getElementById('emptyText').innerText = "No data found for this selection.";
                document.getElementById('tableCount').innerText = "Showing 0 rows";
                return;
            }

            emptyState.style.display = 'none';
            
            const firstRow = tableData[0];
            const rawColumns = Object.keys(firstRow);
            
            // Map column names to pretty names, rearrange if necessary
            let columns = [...rawColumns];
            
            const trHead = document.createElement('tr');
            columns.forEach(col => {
                const th = document.createElement('th');
                th.innerText = col.replace(/_/g, ' ');
                trHead.appendChild(th);
            });
            tableHead.appendChild(trHead);

            tableData.forEach(row => {
                const tr = document.createElement('tr');
                columns.forEach(col => {
                    const td = document.createElement('td');
                    const val = row[col];
                    
                    if (val === null || val === undefined) {
                        td.innerHTML = '<span style="color: var(--text-muted); font-style: italic;">--</span>';
                    } else if (col === 'user_id' || col === 'course_id' || col === 'node_id' || col === 'lesson_id' || col === 'interaction_id') {
                        td.innerHTML = `<span class="mono-val">${val}</span>`;
                    } else if (col === 'alert_type') {
                        td.innerHTML = `<span class="badge alert-${val}">${val.replace(/_/g, ' ')}</span>`;
                    } else if (col === 'learning_style') {
                        let styleClass = 'style-theory';
                        if (val.includes('AI')) styleClass = 'style-ai';
                        else if (val.includes('Flashcard')) styleClass = 'style-flashcard';
                        else if (val.includes('Trắc nghiệm')) styleClass = 'style-practice';
                        td.innerHTML = `<span class="badge ${styleClass}">${val}</span>`;
                    } else if (col === 'engagement_level') {
                        let levelClass = 'level-low';
                        if (val === 'Rất tích cực') levelClass = 'level-high';
                        else if (val === 'Tích cực') levelClass = 'level-mid';
                        td.innerHTML = `<span class="badge ${levelClass}">${val}</span>`;
                    } else if (col === 'check_accuracy') {
                        let accuracyClass = 'low';
                        if (val >= 0.8) accuracyClass = 'high';
                        else if (val >= 0.6) accuracyClass = 'mid';
                        td.innerHTML = `<span class="accuracy-pill ${accuracyClass}">${(val * 100).toFixed(0)}%</span>`;
                    } else if (col === 'struggle_rate') {
                        const percent = (val * 100).toFixed(0);
                        const rateClass = val >= 0.5 ? 'high' : 'low';
                        td.innerHTML = `
                            <div class="progress-bar-container">
                                <div class="progress-bar">
                                    <div class="progress-fill ${rateClass}" style="width: ${percent}%"></div>
                                </div>
                                <span style="font-weight: 700; color: ${val >= 0.5 ? 'var(--accent-red)' : 'var(--text-primary)'};">${percent}%</span>
                            </div>
                        `;
                    } else if (col === 'study_recommendation') {
                        td.innerHTML = `<div class="recommendation-chip">${val}</div>`;
                    } else if (col === 'implicit_affinity_score') {
                        td.innerHTML = `<strong style="color: var(--primary); font-family: var(--font-mono); font-size: 0.95rem;">${typeof val === 'number' ? val.toFixed(2) : val}</strong>`;
                    } else if (col === 'last_active_at' || col === 'last_interaction_at' || col === 'last_attempt_at' || col === 'detected_at') {
                        try {
                            const date = new Date(val);
                            td.innerText = date.toLocaleString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' });
                        } catch (e) {
                            td.innerText = val;
                        }
                    } else if (typeof val === 'object') {
                        td.innerText = JSON.stringify(val);
                    } else {
                        td.innerText = val;
                    }
                    tr.appendChild(td);
                });
                tableBody.appendChild(tr);
            });

            document.getElementById('tableCount').innerText = `Showing ${tableData.length} rows`;
        }

        // Live search filter
        function filterTable() {
            const query = document.getElementById('tableSearch').value.toLowerCase().trim();
            const tableBody = document.getElementById('tableBody');
            const rows = tableBody.getElementsByTagName('tr');
            let visibleCount = 0;

            for (let i = 0; i < rows.length; i++) {
                const cells = rows[i].getElementsByTagName('td');
                let found = false;
                for (let j = 0; j < cells.length; j++) {
                    if (cells[j].innerText.toLowerCase().includes(query)) {
                        found = true;
                        break;
                    }
                }
                if (found) {
                    rows[i].style.display = '';
                    visibleCount++;
                } else {
                    rows[i].style.display = 'none';
                }
            }

            document.getElementById('tableCount').innerText = `Showing ${visibleCount} of ${tableData.length} rows`;
        }

        // Trigger Server-side Parquet Export
        async function triggerServerExport() {
            if (!secretKey) {
                showToast('Secret key required', 'error');
                return;
            }

            showToast('Starting Parquet export on server...', 'info');
            try {
                const response = await fetch('/personalize/analytics/gold/export', {
                    method: 'POST',
                    headers: getHeaders()
                });
                const res = await response.json();
                if (response.ok) {
                    showToast('Server Parquet export successful', 'success');
                    console.log('Exported files:', res.files);
                } else {
                    showToast(res.detail || 'Export failed', 'error');
                }
            } catch (err) {
                showToast(err.message, 'error');
            }
        }

        // Generate Local CSV download
        function downloadActiveCSV() {
            if (!tableData || tableData.length === 0) {
                showToast('No data available to download', 'error');
                return;
            }

            const headers = Object.keys(tableData[0]);
            let csvContent = "data:text/csv;charset=utf-8,";
            
            csvContent += headers.join(",") + "\n";
            
            tableData.forEach(row => {
                const rowValues = headers.map(header => {
                    const val = row[header];
                    if (val === null || val === undefined) return "";
                    const stringVal = String(val).replace(/"/g, '""');
                    return stringVal.includes(",") || stringVal.includes("\n") ? `"${stringVal}"` : stringVal;
                });
                csvContent += rowValues.join(",") + "\n";
            });

            const encodedUri = encodeURI(csvContent);
            const link = document.createElement("a");
            link.setAttribute("href", encodedUri);
            link.setAttribute("download", `bdc_lakehouse_${activeTab}_${new Date().toISOString().slice(0,10)}.csv`);
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            showToast('CSV downloaded successfully', 'success');
        }
    </script>
</body>
</html>
"""
