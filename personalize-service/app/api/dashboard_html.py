DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BDC Lakehouse Control Center</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #080612;
            --card-bg: rgba(20, 16, 38, 0.65);
            --border-color: rgba(139, 92, 246, 0.2);
            --border-hover: rgba(139, 92, 246, 0.4);
            --text-primary: #f3f4f6;
            --text-secondary: #9ca3af;
            --text-muted: #6b7280;
            --primary: #8b5cf6;
            --primary-glow: rgba(139, 92, 246, 0.3);
            --accent-blue: #3b82f6;
            --accent-cyan: #06b6d4;
            --accent-green: #10b981;
            --accent-red: #ef4444;
            --font-main: 'Inter', sans-serif;
            --font-title: 'Outfit', sans-serif;
            --font-mono: 'JetBrains Mono', monospace;
            --glow: 0 0 20px var(--primary-glow);
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            background-color: var(--bg-color);
            background-image: 
                radial-gradient(circle at 10% 20%, rgba(139, 92, 246, 0.08) 0%, transparent 40%),
                radial-gradient(circle at 90% 80%, rgba(59, 130, 246, 0.08) 0%, transparent 40%),
                radial-gradient(circle at 50% 50%, rgba(6, 182, 212, 0.03) 0%, transparent 60%);
            background-attachment: fixed;
            color: var(--text-primary);
            font-family: var(--font-main);
            min-height: 100vh;
            padding: 2rem;
            line-height: 1.5;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            display: flex;
            flex-direction: column;
            gap: 2rem;
        }

        /* --- Header --- */
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 1.5rem;
            border-bottom: 1px solid var(--border-color);
        }

        .logo-group {
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }

        .logo-icon {
            font-size: 2.2rem;
            animation: float 4s ease-in-out infinite;
        }

        h1 {
            font-family: var(--font-title);
            font-size: 1.8rem;
            font-weight: 800;
            background: linear-gradient(135deg, #fff 30%, #a78bfa 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            letter-spacing: -0.02em;
        }

        .subtitle {
            font-size: 0.875rem;
            color: var(--text-secondary);
            margin-top: 0.25rem;
        }

        .auth-badge {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            background: rgba(17, 24, 39, 0.5);
            padding: 0.5rem 1rem;
            border-radius: 9999px;
            border: 1px solid var(--border-color);
            font-size: 0.825rem;
            font-weight: 500;
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
            box-shadow: 0 0 8px var(--accent-green);
        }

        /* --- Stats Overview --- */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 1.5rem;
        }

        .stat-card {
            background: var(--card-bg);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.5rem;
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
            position: relative;
            overflow: hidden;
            transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1), border-color 0.3s ease;
        }

        .stat-card:hover {
            transform: translateY(-2px);
            border-color: var(--border-hover);
        }

        .stat-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 4px;
            background: linear-gradient(90deg, var(--primary), var(--accent-blue));
            opacity: 0.7;
        }

        .stat-card.alerts::before {
            background: linear-gradient(90deg, var(--accent-red), #f97316);
        }

        .stat-label {
            font-size: 0.825rem;
            font-weight: 600;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .stat-value {
            font-family: var(--font-title);
            font-size: 2.2rem;
            font-weight: 700;
            color: #fff;
            margin-top: 0.25rem;
        }

        .stat-desc {
            font-size: 0.75rem;
            color: var(--text-muted);
        }

        /* --- Configuration & Control --- */
        .controls-grid {
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 1.5rem;
        }

        @media (max-width: 900px) {
            .controls-grid {
                grid-template-columns: 1fr;
            }
        }

        .panel-card {
            background: var(--card-bg);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.5rem;
            display: flex;
            flex-direction: column;
            gap: 1.25rem;
        }

        .panel-title {
            font-family: var(--font-title);
            font-size: 1.1rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 0.5rem;
            color: #fff;
        }

        .input-group {
            display: flex;
            gap: 0.5rem;
            width: 100%;
        }

        .input-field {
            flex-grow: 1;
            background: rgba(10, 8, 20, 0.8);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            color: #fff;
            padding: 0.75rem 1rem;
            font-family: var(--font-mono);
            font-size: 0.875rem;
            transition: all 0.3s ease;
        }

        .input-field:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 10px rgba(139, 92, 246, 0.25);
        }

        .btn {
            background: linear-gradient(135deg, var(--primary) 0%, #6d28d9 100%);
            color: #fff;
            border: none;
            border-radius: 8px;
            padding: 0.75rem 1.25rem;
            font-weight: 600;
            font-size: 0.875rem;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 0.5rem;
            transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
            box-shadow: 0 4px 12px rgba(139, 92, 246, 0.2);
        }

        .btn:hover {
            transform: translateY(-1px);
            box-shadow: 0 6px 16px rgba(139, 92, 246, 0.35), var(--glow);
        }

        .btn:active {
            transform: translateY(1px);
        }

        .btn.secondary {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border-color);
            box-shadow: none;
        }

        .btn.secondary:hover {
            background: rgba(255, 255, 255, 0.1);
            border-color: var(--border-hover);
            box-shadow: none;
        }

        .btn.danger {
            background: linear-gradient(135deg, var(--accent-red) 0%, #b91c1c 100%);
            box-shadow: 0 4px 12px rgba(239, 68, 68, 0.2);
        }

        .btn.danger:hover {
            box-shadow: 0 6px 16px rgba(239, 68, 68, 0.35);
        }

        .btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none !important;
            box-shadow: none !important;
        }

        .button-row {
            display: flex;
            gap: 0.75rem;
            flex-wrap: wrap;
        }

        /* --- Tab System & Table --- */
        .tab-bar {
            display: flex;
            border-bottom: 1px solid var(--border-color);
            gap: 1.5rem;
            overflow-x: auto;
            scrollbar-width: none;
        }
        .tab-bar::-webkit-scrollbar {
            display: none;
        }

        .tab-item {
            font-family: var(--font-title);
            font-size: 0.95rem;
            font-weight: 600;
            color: var(--text-secondary);
            padding: 0.75rem 0.25rem 1rem;
            cursor: pointer;
            position: relative;
            background: none;
            border: none;
            transition: color 0.3s ease;
        }

        .tab-item:hover {
            color: #fff;
        }

        .tab-item.active {
            color: var(--primary);
        }

        .tab-item.active::after {
            content: '';
            position: absolute;
            bottom: -1px;
            left: 0;
            width: 100%;
            height: 2px;
            background-color: var(--primary);
            box-shadow: 0 0 10px var(--primary);
        }

        .search-bar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 1rem;
        }

        @media (max-width: 600px) {
            .search-bar {
                flex-direction: column;
                align-items: stretch;
            }
        }

        .table-container {
            width: 100%;
            overflow-x: auto;
            border: 1px solid var(--border-color);
            border-radius: 12px;
            background: rgba(10, 8, 20, 0.4);
            min-height: 250px;
            position: relative;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            text-align: left;
            font-size: 0.875rem;
        }

        th {
            background-color: rgba(15, 12, 28, 0.85);
            font-family: var(--font-title);
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.75rem;
            letter-spacing: 0.05em;
            color: var(--text-secondary);
            padding: 1rem 1.25rem;
            border-bottom: 1px solid var(--border-color);
        }

        td {
            padding: 1rem 1.25rem;
            border-bottom: 1px solid rgba(255, 255, 255, 0.03);
            color: var(--text-primary);
            font-family: var(--font-main);
        }

        tr:hover td {
            background-color: rgba(255, 255, 255, 0.02);
        }

        /* Special styled columns */
        .mono-val {
            font-family: var(--font-mono);
            font-size: 0.825rem;
            color: var(--accent-cyan);
            background: rgba(6, 182, 212, 0.07);
            padding: 0.2rem 0.4rem;
            border-radius: 4px;
            border: 1px solid rgba(6, 182, 212, 0.15);
        }

        .badge {
            display: inline-flex;
            align-items: center;
            padding: 0.25rem 0.6rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: capitalize;
        }

        .badge.alert-struggle {
            background-color: rgba(239, 68, 68, 0.15);
            color: var(--accent-red);
            border: 1px solid rgba(239, 68, 68, 0.25);
            box-shadow: 0 0 10px rgba(239, 68, 68, 0.05);
        }

        .badge.alert-inactivity {
            background-color: rgba(249, 115, 22, 0.15);
            color: #f97316;
            border: 1px solid rgba(249, 115, 22, 0.25);
        }

        .badge.success {
            background-color: rgba(16, 185, 129, 0.15);
            color: var(--accent-green);
            border: 1px solid rgba(16, 185, 129, 0.25);
        }

        /* --- Loading & Empty States --- */
        .loading-overlay {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(8, 6, 18, 0.8);
            display: flex;
            justify-content: center;
            align-items: center;
            backdrop-filter: blur(4px);
            border-radius: 12px;
            z-index: 10;
            display: none;
        }

        .spinner {
            width: 40px;
            height: 40px;
            border: 3px solid rgba(139, 92, 246, 0.1);
            border-top-color: var(--primary);
            border-radius: 50%;
            animation: spin 1s infinite linear;
            filter: drop-shadow(0 0 8px var(--primary));
        }

        .empty-state {
            padding: 4rem 2rem;
            text-align: center;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 1rem;
            color: var(--text-secondary);
        }

        .empty-icon {
            font-size: 3rem;
            opacity: 0.4;
        }

        /* --- Notifications / Toast --- */
        .toast-container {
            position: fixed;
            bottom: 2rem;
            right: 2rem;
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
            z-index: 100;
        }

        .toast {
            background: rgba(20, 16, 38, 0.9);
            border: 1px solid var(--border-color);
            border-left: 4px solid var(--primary);
            padding: 1rem 1.5rem;
            border-radius: 8px;
            color: #fff;
            font-size: 0.875rem;
            font-weight: 500;
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.5);
            display: flex;
            align-items: center;
            gap: 0.75rem;
            transform: translateX(120%);
            transition: transform 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
            backdrop-filter: blur(12px);
        }

        .toast.show {
            transform: translateX(0);
        }

        .toast.success {
            border-left-color: var(--accent-green);
        }

        .toast.error {
            border-left-color: var(--accent-red);
        }

        /* --- Animations --- */
        @keyframes float {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-6px); }
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <header>
            <div class="logo-group">
                <div class="logo-icon">🌌</div>
                <div>
                    <h1>BDC Lakehouse Control Center</h1>
                    <div class="subtitle">DuckDB Student Analytics & Personalization Ledger</div>
                </div>
            </div>
            <div class="auth-badge">
                <div id="authDot" class="status-dot"></div>
                <span id="authText">API Disconnected</span>
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
            <div class="stat-card alerts">
                <div class="stat-label">Active Struggle Alerts</div>
                <div id="statAlerts" class="stat-value">--</div>
                <div class="stat-desc">Triggered triggers needing attention</div>
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

        <!-- Tab bar & Table Section -->
        <div class="panel-card" style="min-height: 500px;">
            <div class="tab-bar">
                <button class="tab-item active" onclick="switchTab('student-metrics', this)">📊 Student Course Metrics</button>
                <button class="tab-item" onclick="switchTab('concept-struggles', this)">⚠️ Concept Struggles</button>
                <button class="tab-item" onclick="switchTab('interaction-matrix', this)">🔗 User-Item Affinity Matrix</button>
                <button class="tab-item" onclick="switchTab('struggle-alerts', this)">🚨 Struggle Alerts</button>
            </div>

            <div class="search-bar">
                <input type="text" id="tableSearch" class="input-field" style="max-width: 400px;" placeholder="🔍 Search records..." oninput="filterTable()">
                <div id="tableCount" class="stat-desc">Showing 0 rows</div>
            </div>

            <div class="table-container">
                <div id="loadingOverlay" class="loading-overlay">
                    <div class="spinner"></div>
                </div>
                <table id="dataTable">
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
        // State
        let activeTab = 'student-metrics';
        let tableData = [];
        let secretKey = '';

        // Initialize on load
        window.addEventListener('DOMContentLoaded', () => {
            // Load key from LocalStorage or URL params
            const urlParams = new URLSearchParams(window.location.search);
            const urlSecret = urlParams.get('secret');
            
            if (urlSecret) {
                secretKey = urlSecret;
                localStorage.setItem('bdc_ai_secret', secretKey);
                document.getElementById('secretKey').value = secretKey;
                // Clean URL
                window.history.replaceState({}, document.title, window.location.pathname);
            } else {
                secretKey = localStorage.getItem('bdc_ai_secret') || '';
                document.getElementById('secretKey').value = secretKey;
            }

            updateAuthStatus();
            if (secretKey) {
                loadAllData();
            }
        });

        function saveSecretKey() {
            const inputVal = document.getElementById('secretKey').value.trim();
            secretKey = inputVal;
            localStorage.setItem('bdc_ai_secret', secretKey);
            updateAuthStatus();
            showToast('API Key saved successfully', 'success');
            loadAllData();
        }

        function updateAuthStatus() {
            const dot = document.getElementById('authDot');
            const text = document.getElementById('authText');
            if (secretKey) {
                dot.classList.add('active');
                text.innerText = 'Authenticated';
            } else {
                dot.classList.remove('active');
                text.innerText = 'API Key Required';
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
                // Determine base path to correctly route in Traefik environments
                const pathParts = window.location.pathname.split('/');
                // Remove trailing file or page if exists
                if (pathParts[pathParts.length - 1].includes('.')) {
                    pathParts.pop();
                }
                
                // Fetch metrics, struggles, Alerts and Matrix concurrently
                const metricsUrl = '/personalize/analytics/gold/student-metrics';
                const strugglesUrl = '/personalize/analytics/gold/concept-struggles';
                const matrixUrl = '/personalize/analytics/gold/interaction-matrix';
                const alertsUrl = '/personalize/analytics/gold/struggle-alerts';

                const [metrics, struggles, matrix, alerts] = await Promise.all([
                    fetchAPI(metricsUrl).catch(e => { console.error(e); return []; }),
                    fetchAPI(strugglesUrl).catch(e => { console.error(e); return []; }),
                    fetchAPI(matrixUrl).catch(e => { console.error(e); return []; }),
                    fetchAPI(alertsUrl).catch(e => { console.error(e); return []; })
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

        // Render standard tables dynamically
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
            
            // Build dynamic headers based on keys in first item
            const firstRow = tableData[0];
            const columns = Object.keys(firstRow);
            
            const trHead = document.createElement('tr');
            columns.forEach(col => {
                const th = document.createElement('th');
                th.innerText = col.replace(/_/g, ' ');
                trHead.appendChild(th);
            });
            tableHead.appendChild(trHead);

            // Populate rows
            tableData.forEach(row => {
                const tr = document.createElement('tr');
                columns.forEach(col => {
                    const td = document.createElement('td');
                    const val = row[col];
                    
                    if (val === null || val === undefined) {
                        td.innerHTML = '<span style="color: var(--text-muted);">NULL</span>';
                    } else if (col === 'user_id' || col === 'course_id' || col === 'node_id' || col === 'lesson_id' || col === 'interaction_id') {
                        td.innerHTML = `<span class="mono-val">${val}</span>`;
                    } else if (col === 'alert_type') {
                        td.innerHTML = `<span class="badge alert-${val}">${val}</span>`;
                    } else if (col === 'check_accuracy' || col === 'struggle_rate' || col === 'implicit_affinity_score') {
                        td.innerHTML = `<strong style="color: #fff;">${typeof val === 'number' ? val.toFixed(2) : val}</strong>`;
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
            
            // Headers row
            csvContent += headers.join(",") + "\n";
            
            // Data rows
            tableData.forEach(row => {
                const rowValues = headers.map(header => {
                    const val = row[header];
                    if (val === null || val === undefined) return "";
                    // Escape commas and quotes
                    const stringVal = String(val).replace(/"/g, '""');
                    return stringVal.includes(",") || stringVal.includes("\n") ? `"${stringVal}"` : stringVal;
                });
                csvContent += rowValues.join(",") + "\n";
            });

            // Trigger download link
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
