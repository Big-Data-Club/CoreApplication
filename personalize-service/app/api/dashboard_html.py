DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BDC Lakehouse Control Center</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #f8fafc;
            --card-bg: #ffffff;
            --border-color: #e2e8f0;
            --border-hover: #cbd5e1;
            --text-primary: #0f172a;
            --text-secondary: #334155;
            --text-muted: #64748b;
            --primary: #4f46e5;
            --primary-hover: #4338ca;
            --primary-light: #e0e7ff;
            --accent-blue: #2563eb;
            --accent-green: #16a34a;
            --accent-red: #dc2626;
            --accent-orange: #ea580c;
            --font-main: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            --font-mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Monaco, monospace;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            background-color: var(--bg-color);
            color: var(--text-primary);
            font-family: var(--font-main);
            min-height: 100vh;
            padding: 1.5rem;
            line-height: 1.5;
            -webkit-font-smoothing: antialiased;
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
            padding: 1rem 1.5rem;
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
        }

        .logo-group {
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }

        .logo-icon {
            font-size: 1.8rem;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        h1 {
            font-size: 1.25rem;
            font-weight: 700;
            color: var(--text-primary);
            letter-spacing: -0.01em;
        }

        .subtitle {
            font-size: 0.75rem;
            color: var(--text-muted);
            font-weight: 400;
        }

        .auth-badge {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            background: #f1f5f9;
            padding: 0.375rem 0.875rem;
            border-radius: 9999px;
            border: 1px solid var(--border-color);
            font-size: 0.75rem;
            font-weight: 500;
            color: var(--text-secondary);
        }

        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background-color: var(--accent-red);
            transition: all 0.2s ease;
        }

        .status-dot.active {
            background-color: var(--accent-green);
        }

        /* --- Stats Grid --- */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 1.25rem;
        }

        .stat-card {
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 1.25rem;
            display: flex;
            flex-direction: column;
            gap: 0.375rem;
            box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
            transition: border-color 0.2s ease;
        }

        .stat-card:hover {
            border-color: var(--border-hover);
        }

        .stat-label {
            font-size: 0.75rem;
            font-weight: 600;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .stat-value {
            font-size: 1.75rem;
            font-weight: 700;
            color: var(--text-primary);
        }

        .stat-desc {
            font-size: 0.75rem;
            color: var(--text-muted);
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
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 1.25rem;
            box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }

        .panel-title {
            font-size: 0.875rem;
            font-weight: 600;
            color: var(--text-primary);
            text-transform: uppercase;
            letter-spacing: 0.02em;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 0.5rem;
        }

        .button-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.75rem;
        }

        .input-group {
            display: flex;
            gap: 0.5rem;
        }

        .input-field {
            flex: 1;
            padding: 0.5rem 0.75rem;
            border-radius: 8px;
            border: 1px solid var(--border-color);
            background: #ffffff;
            color: var(--text-primary);
            font-size: 0.875rem;
            transition: all 0.15s ease;
        }

        .input-field:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.15);
        }

        .btn {
            background: var(--primary);
            color: #ffffff;
            border: 1px solid transparent;
            padding: 0.5rem 1rem;
            font-size: 0.875rem;
            font-weight: 500;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.15s ease;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 0.375rem;
        }

        .btn:hover {
            background: var(--primary-hover);
        }

        .btn:active {
            transform: scale(0.98);
        }

        .btn.secondary {
            background: #f1f5f9;
            color: var(--text-secondary);
            border: 1px solid var(--border-color);
        }

        .btn.secondary:hover {
            background: #e2e8f0;
            color: var(--text-primary);
        }

        /* --- Main Data Explorer --- */
        .explorer-card {
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }

        .explorer-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1rem 1.25rem;
            border-bottom: 1px solid var(--border-color);
            background: #f8fafc;
            flex-wrap: wrap;
            gap: 1rem;
        }

        .tabs-container {
            display: flex;
            gap: 0.25rem;
            background: #f1f5f9;
            padding: 0.25rem;
            border-radius: 8px;
        }

        .tab-item {
            background: transparent;
            border: none;
            color: var(--text-secondary);
            padding: 0.375rem 0.875rem;
            font-size: 0.825rem;
            font-weight: 500;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.15s ease;
        }

        .tab-item.active {
            background: #ffffff;
            color: var(--text-primary);
            box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
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
            min-height: 250px;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            text-align: left;
            font-size: 0.875rem;
        }

        th {
            background: #f8fafc;
            color: var(--text-muted);
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.7rem;
            letter-spacing: 0.05em;
            padding: 0.75rem 1.25rem;
            border-bottom: 1px solid var(--border-color);
        }

        td {
            padding: 0.75rem 1.25rem;
            border-bottom: 1px solid var(--border-color);
            color: var(--text-secondary);
            font-weight: 400;
        }

        tr:last-child td {
            border-bottom: none;
        }

        tr:hover td {
            background-color: #f8fafc;
        }

        .mono-val {
            font-family: var(--font-mono);
            font-size: 0.8rem;
            background: #f1f5f9;
            padding: 0.125rem 0.375rem;
            border-radius: 4px;
            color: var(--text-primary);
        }

        /* Badge design */
        .badge {
            display: inline-flex;
            padding: 0.125rem 0.5rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 500;
            text-transform: capitalize;
        }

        .badge.alert-concept_struggle {
            background-color: #fef2f2;
            color: var(--accent-red);
            border: 1px solid #fecaca;
        }

        .badge.alert-inactivity {
            background-color: #fff7ed;
            color: var(--accent-orange);
            border: 1px solid #ffedd5;
        }

        /* Loading & Empty State */
        .loading-overlay {
            position: absolute;
            inset: 0;
            background: rgba(255, 255, 255, 0.8);
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 10;
        }

        .spinner {
            width: 32px;
            height: 32px;
            border: 3px solid var(--border-color);
            border-top-color: var(--primary);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }

        .empty-state {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 4rem 2rem;
            text-align: center;
            color: var(--text-muted);
            gap: 0.75rem;
        }

        .empty-icon {
            font-size: 2rem;
        }

        #emptyText {
            max-width: 400px;
            font-size: 0.875rem;
        }

        /* Toast notifications */
        .toast-container {
            position: fixed;
            bottom: 1.5rem;
            right: 1.5rem;
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
            z-index: 999;
        }

        .toast {
            background: #ffffff;
            border: 1px solid var(--border-color);
            border-left: 4px solid var(--primary);
            border-radius: 8px;
            padding: 0.75rem 1.25rem;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
            display: flex;
            align-items: center;
            gap: 0.75rem;
            font-size: 0.875rem;
            font-weight: 500;
            color: var(--text-primary);
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
                <div class="logo-icon">📊</div>
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
            <div class="stat-card">
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
                try {
                    localStorage.setItem('bdc_ai_secret', secretKey);
                } catch (e) {
                    console.warn('LocalStorage is blocked. Key loaded in memory for this session.', e);
                }
                document.getElementById('secretKey').value = secretKey;
                
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
            const columns = Object.keys(firstRow);
            
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
                        td.innerHTML = '<span style="color: var(--text-muted);">NULL</span>';
                    } else if (col === 'user_id' || col === 'course_id' || col === 'node_id' || col === 'lesson_id' || col === 'interaction_id') {
                        td.innerHTML = `<span class="mono-val">${val}</span>`;
                    } else if (col === 'alert_type') {
                        td.innerHTML = `<span class="badge alert-${val}">${val}</span>`;
                    } else if (col === 'check_accuracy' || col === 'struggle_rate' || col === 'implicit_affinity_score') {
                        td.innerHTML = `<strong style="color: var(--primary);">${typeof val === 'number' ? val.toFixed(2) : val}</strong>`;
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
            
            csvContent += headers.join(",") + "\\n";
            
            tableData.forEach(row => {
                const rowValues = headers.map(header => {
                    const val = row[header];
                    if (val === null || val === undefined) return "";
                    const stringVal = String(val).replace(/"/g, '""');
                    return stringVal.includes(",") || stringVal.includes("\\n") ? `"${stringVal}"` : stringVal;
                });
                csvContent += rowValues.join(",") + "\\n";
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
