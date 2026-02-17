const API_BASE = ""; // Relative path

async function fetchStatus() {
    try {
        const res = await fetch(`${API_BASE}/health`);
        const data = await res.json();
        const statusEl = document.getElementById('server-status');
        statusEl.textContent = data.status === 'healthy' ? '🟢 Online' : '🔴 Issues';
    } catch (e) {
        document.getElementById('server-status').textContent = '🔴 Offline';
    }
}

async function fetchPending() {
    try {
        // Authenticated fetch (Token hardcoded for dev/demo simplicity, ideally injected or prompted)
        // For this demo, we assume the browser session or a proxy handles auth, OR we rely on localhost trust.
        // But the server requires X-Sentinel-Token. 
        // We will fetch from /pending directly. 
        // NOTE: In a real app, we'd handle login. Here we'll try without token first (if localhost trusted)
        // or add a simple prompt/storage if it fails.

        // For now, let's assume Development Mode where localhost is allowed plain access or we add the header if stored.
        const headers = {
            'Content-Type': 'application/json'
        };

        const token = localStorage.getItem('sentinel_token');
        if (token) {
            headers['X-Sentinel-Token'] = token;
        }

        const res = await fetch(`${API_BASE}/pending`, { headers });
        if (res.status === 401) {
            // Simple Auth prompt for demo
            const newToken = prompt("Enter Sentinel Auth Token:");
            if (newToken) {
                localStorage.setItem('sentinel_token', newToken);
                return fetchPending(); // Retry
            }
        }

        const data = await res.json();
        renderPending(data);
    } catch (e) {
        console.error("Failed to fetch pending requests", e);
    }
}

function renderPending(requests) {
    const list = document.getElementById('pending-list');
    list.innerHTML = '';

    // API returns dict: {id: RequestObj}
    const items = Object.values(requests);

    if (items.length === 0) {
        list.innerHTML = '<p class="empty-state">No pending approvals.</p>';
        return;
    }

    items.forEach(req => {
        const card = document.createElement('div');
        card.className = 'card';
        card.innerHTML = `
            <div class="card-content">
                <strong>${req.command}</strong><br>
                <small>${req.reason || 'No reason provided'}</small>
            </div>
            <div class="card-actions">
                <button class="btn-approve" onclick="approveRequest('${req.id}')">Approve</button>
            </div>
        `;
        list.appendChild(card);
    });
}

async function approveRequest(id) {
    const token = localStorage.getItem('sentinel_token');
    if (!token) {
        alert("Missing Auth Token");
        return;
    }

    try {
        const res = await fetch(`${API_BASE}/approve/${id}`, {
            method: 'POST',
            headers: {
                'X-Sentinel-Token': token
            }
        });

        if (res.ok) {
            fetchPending(); // Refresh
        } else {
            const err = await res.json();
            alert(`Error: ${err.detail}`);
        }
    } catch (e) {
        alert(`Error approving: ${e.message}`);
    }
}

// Poll every 2 seconds
setInterval(() => {
    fetchStatus();
    fetchPending();
}, 2000);

// Initial load
fetchStatus();
fetchPending();

// Provide a way to manually set token for testing
window.setToken = (t) => {
    localStorage.setItem('sentinel_token', t);
    console.log("Token set.");
};
