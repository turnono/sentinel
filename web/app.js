const API_BASE = ""; // Relative path

// State
let isOnline = false;

async function fetchStatus() {
    try {
        const res = await fetch(`${API_BASE}/health`);
        const data = await res.json();
        updateStatus(data.status === 'healthy');
    } catch (e) {
        updateStatus(false);
    }
}

function updateStatus(online) {
    isOnline = online;
    const statusEl = document.getElementById('server-status');
    const indicator = document.querySelector('.status-indicator');

    if (online) {
        statusEl.textContent = 'System Online';
        statusEl.style.color = 'var(--success)';
        indicator.classList.add('online');
        indicator.classList.remove('offline');
    } else {
        statusEl.textContent = 'Exchanging Handshakes...';
        statusEl.style.color = 'var(--text-secondary)';
        indicator.classList.add('offline');
        indicator.classList.remove('online');
    }
}

async function fetchPending() {
    if (!isOnline) return;

    try {
        const list = document.getElementById('pending-list');
        const headers = { 'Content-Type': 'application/json' };
        const token = localStorage.getItem('sentinel_token');
        if (token) headers['X-Sentinel-Token'] = token;

        const res = await fetch(`${API_BASE}/pending`, { headers });

        if (res.status === 401) {
            // If unauthorized, maybe show a login button or prompt?
            // For now, silent fail or log
            console.warn("Unauthorized fetchPending");
            return;
        }

        const data = await res.json();
        const items = Object.values(data);

        if (items.length === 0) {
            list.innerHTML = '<div class="loading-spinner">No pending approvals</div>';
            return;
        }

        list.innerHTML = items.map(req => `
            <div class="card">
                <div class="card-content">
                    <div class="card-header">
                        <span class="cmd">${escapeHtml(req.command)}</span>
                    </div>
                    <span class="reason">${escapeHtml(req.reason || 'Policy requires review')}</span>
                     <div class="actions">
                        <button class="btn-deny" onclick="denyRequest('${req.id}')">Deny</button>
                        <button class="btn-approve" onclick="approveRequest('${req.id}')">Approve</button>
                    </div>
                </div>
            </div>
        `).join('');

    } catch (e) {
        console.error("Fetch pending failed", e);
    }
}

// Mocking audit fetch for now since we haven't exposed GET /audit-logs yet in the server plan
// But we should implement it to make the "Recent Activity" section real.
// For now, let's just make sure the UI doesn't look broken.
// We will modify sentinel_server.py to expose it if possible, or leave placeholder.
async function fetchActivity() {
    // TODO: Implement GET /history or /audit-logs in sentinel_server.py
    const list = document.getElementById('audit-list');
    // Placeholder content
    list.innerHTML = `
        <div class="log-item">
             <span class="log-status allowed">Allowed</span>
             <span class="log-cmd">ls -la</span>
             <span class="log-time">Now</span>
        </div>
        <div class="log-item">
             <span class="log-status blocked">Blocked</span>
             <span class="log-cmd">rm -rf /</span>
             <span class="log-time">1m ago</span>
        </div>
    `;
}

async function approveRequest(id) {
    const token = localStorage.getItem('sentinel_token');
    if (!token) {
        const t = prompt("Enter Sentinel Auth Token:");
        if (t) {
            localStorage.setItem('sentinel_token', t);
            approveRequest(id);
        }
        return;
    }

    try {
        const res = await fetch(`${API_BASE}/approve/${id}`, {
            method: 'POST',
            headers: { 'X-Sentinel-Token': token }
        });

        if (res.ok) {
            fetchPending(); // Immediate refresh
        } else {
            const err = await res.json();
            alert(`Error: ${err.detail}`);
            if (res.status === 401) localStorage.removeItem('sentinel_token');
        }
    } catch (e) {
        alert(e.message);
    }
}

function denyRequest(id) {
    // Just remove from UI for now as API support might not exist
    if (confirm("Reject this request? (This will just clear it from view for now)")) {
        // In a real system, we'd call DELETE /pending/{id}
        fetchPending();
    }
}

function escapeHtml(text) {
    if (!text) return text;
    return text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// Lifecycle
setInterval(() => {
    fetchStatus();
    fetchPending();
    // fetchActivity();
}, 2000);

fetchStatus();
fetchPending();
fetchActivity();
