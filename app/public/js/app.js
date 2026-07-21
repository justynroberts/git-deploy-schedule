const API_BASE = window.location.origin;

// Tab Management
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const tab = btn.dataset.tab;

        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

        btn.classList.add('active');
        document.getElementById(`${tab}-tab`).classList.add('active');
    });
});

// Dashboard Functions
async function loadDashboard() {
    await Promise.all([
        loadStatus(),
        loadStats(),
        loadHistory()
    ]);
}

async function loadStatus() {
    try {
        const response = await fetch(`${API_BASE}/api/status`);
        const data = await response.json();

        const statusBadge = document.getElementById('scheduler-status');
        const statusText = document.getElementById('status-text');

        statusBadge.className = 'status-badge';

        if (!data.running) {
            statusBadge.classList.add('stopped');
            statusText.textContent = 'Stopped';
        } else if (data.paused) {
            statusBadge.classList.add('paused');
            statusText.textContent = 'Paused';
        } else {
            statusText.textContent = 'Running';
        }

        document.getElementById('last-run').textContent = data.lastRun
            ? new Date(data.lastRun).toLocaleString()
            : 'Never';

        document.getElementById('next-run').textContent = data.nextRun
            ? new Date(data.nextRun).toLocaleString()
            : 'Not scheduled';

    } catch (error) {
        console.error('Error loading status:', error);
    }
}

async function loadStats() {
    try {
        const response = await fetch(`${API_BASE}/api/stats`);
        const data = await response.json();

        document.getElementById('total-commits').textContent = data.total_commits || 0;
        document.getElementById('successful-commits').textContent = data.successful_commits || 0;
        document.getElementById('files-changed').textContent = data.total_files_changed || 0;
        document.getElementById('ollama-usage').textContent = data.ollama_usage_count || 0;

    } catch (error) {
        console.error('Error loading stats:', error);
    }
}

async function loadHistory() {
    try {
        const response = await fetch(`${API_BASE}/api/history?limit=10`);
        const data = await response.json();

        const feed = document.getElementById('commit-feed');

        if (!data.commits || data.commits.length === 0) {
            feed.innerHTML = '<div class="loading">No commits yet</div>';
            return;
        }

        feed.innerHTML = data.commits.map(commit => `
            <div class="commit-item ${commit.success ? 'success' : 'failed'}">
                <div class="commit-header">
                    <span class="commit-hash">${commit.commit_hash.substring(0, 7)}</span>
                    <span class="commit-time">${new Date(commit.timestamp).toLocaleString()}</span>
                </div>
                <div class="commit-message">${commit.message}</div>
                <div class="commit-meta">
                    <span class="meta-badge">
                        <i class="ph ph-file" style="font-size: 0.9rem;"></i>
                        ${commit.files_changed} files
                    </span>
                    ${commit.used_ollama ? '<span class="meta-badge ai"><i class="ph ph-brain" style="font-size: 0.9rem;"></i> AI</span>' : ''}
                    ${commit.theme ? `<span class="meta-badge">${commit.theme}</span>` : ''}
                    ${commit.push_success ? '<span class="meta-badge"><i class="ph ph-cloud-check" style="font-size: 0.9rem;"></i> Pushed</span>' : ''}
                </div>
            </div>
        `).join('');

    } catch (error) {
        console.error('Error loading history:', error);
    }
}

// Progress Bar Functions
function showProgress(message = 'Processing...') {
    const container = document.getElementById('progress-container');
    const fill = document.getElementById('progress-fill');
    const text = document.getElementById('progress-text');

    container.style.display = 'block';
    fill.className = 'progress-fill indeterminate';
    text.textContent = message;
}

function hideProgress() {
    const container = document.getElementById('progress-container');
    container.style.display = 'none';
}

// Control Actions
async function controlAction(action) {
    const actionMessages = {
        'pause': 'Pausing scheduler...',
        'resume': 'Resuming scheduler...',
        'trigger': 'Triggering commit now...',
        'start': 'Starting scheduler...',
        'stop': 'Stopping scheduler...'
    };

    try {
        showProgress(actionMessages[action] || 'Processing...');

        const response = await fetch(`${API_BASE}/api/control`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action })
        });

        const data = await response.json();

        if (data.success) {
            await loadDashboard();
        }

        hideProgress();

    } catch (error) {
        console.error(`Error performing ${action}:`, error);
        hideProgress();
        alert(`Failed to ${action} scheduler`);
    }
}

document.getElementById('pause-btn').addEventListener('click', () => controlAction('pause'));
document.getElementById('resume-btn').addEventListener('click', () => controlAction('resume'));
document.getElementById('trigger-btn').addEventListener('click', () => controlAction('trigger'));

// Settings Functions
async function loadSettings() {
    await Promise.all([
        loadCredentialsStatus(),
        loadConfig()
    ]);
}

async function loadCredentialsStatus() {
    try {
        const response = await fetch(`${API_BASE}/api/settings/credentials`);
        const data = await response.json();

        const indicator = document.getElementById('credentials-indicator');
        if (!indicator) {
            console.warn('Credentials indicator element not found');
            return;
        }

        indicator.className = 'status-indicator';

        if (data.hasCredentials) {
            indicator.classList.add('has-credentials');
            indicator.textContent = '✓ Credentials are stored securely';
            indicator.style.display = 'flex';
        } else {
            indicator.textContent = '○ No credentials stored';
            indicator.style.display = 'flex';
        }

        console.log('Credentials status loaded:', data.hasCredentials ? 'Stored' : 'Not stored');

    } catch (error) {
        console.error('Error loading credentials status:', error);
    }
}

async function loadConfig() {
    try {
        const response = await fetch(`${API_BASE}/api/settings/config`);
        const config = await response.json();

        const theme = config.ollama.theme || '';
        const predefinedThemes = ['kubernetes', 'docker', 'terraform', 'aws', 'microservices', ''];

        if (predefinedThemes.includes(theme)) {
            document.getElementById('ollama-theme').value = theme;
        } else if (theme) {
            // Custom theme
            document.getElementById('ollama-theme').value = 'custom';
            document.getElementById('custom-theme').value = theme;
            document.getElementById('custom-theme-group').style.display = 'block';
        }

        document.getElementById('base-interval').value = config.schedule.base_interval;
        document.getElementById('jitter-range').value = config.schedule.jitter_range;
        document.getElementById('push-enabled').checked = config.git.push_enabled;

    } catch (error) {
        console.error('Error loading config:', error);
    }
}

// Credentials Form
document.getElementById('credentials-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const credentials = {
        pat_token: document.getElementById('pat-token').value,
        git_username: document.getElementById('git-username').value,
        git_email: document.getElementById('git-email').value
    };

    try {
        const response = await fetch(`${API_BASE}/api/settings/credentials`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(credentials)
        });

        const data = await response.json();

        if (data.success) {
            alert('Credentials saved securely!');
            document.getElementById('pat-token').value = '';
            await loadCredentialsStatus();
        }

    } catch (error) {
        console.error('Error saving credentials:', error);
        alert('Failed to save credentials');
    }
});

document.getElementById('delete-credentials-btn').addEventListener('click', async () => {
    if (!confirm('Are you sure you want to delete stored credentials?')) {
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/api/settings/credentials`, {
            method: 'DELETE'
        });

        const data = await response.json();

        if (data.success) {
            alert('Credentials deleted');
            await loadCredentialsStatus();
        }

    } catch (error) {
        console.error('Error deleting credentials:', error);
        alert('Failed to delete credentials');
    }
});

// Repository form handling
document.getElementById('repository-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const url = document.getElementById('repo-url').value;

    try {
        const response = await fetch(`${API_BASE}/api/repository`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });

        const data = await response.json();

        if (data.success) {
            showRepositoryStatus('Repository URL updated successfully', 'success');
        } else {
            showRepositoryStatus(data.error || 'Failed to update repository', 'error');
        }

    } catch (error) {
        console.error('Error updating repository:', error);
        showRepositoryStatus('Failed to update repository', 'error');
    }
});

document.getElementById('get-repo-btn').addEventListener('click', async () => {
    try {
        const response = await fetch(`${API_BASE}/api/repository`);
        const data = await response.json();

        if (data.url) {
            document.getElementById('repo-url').value = data.url;
            showRepositoryStatus(`Current repository: ${data.url}`, 'success');
        } else {
            showRepositoryStatus('No repository configured', 'warning');
        }

    } catch (error) {
        console.error('Error getting repository:', error);
        showRepositoryStatus('Failed to get repository', 'error');
    }
});

function showRepositoryStatus(message, type) {
    const indicator = document.getElementById('repository-indicator');
    indicator.textContent = message;
    indicator.className = `status-indicator ${type}`;
    setTimeout(() => {
        indicator.textContent = '';
        indicator.className = 'status-indicator';
    }, 3000);
}

// Theme selector handler
document.getElementById('ollama-theme').addEventListener('change', (e) => {
    const customThemeGroup = document.getElementById('custom-theme-group');
    if (e.target.value === 'custom') {
        customThemeGroup.style.display = 'block';
    } else {
        customThemeGroup.style.display = 'none';
    }
});

// Config Form
document.getElementById('config-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const themeSelector = document.getElementById('ollama-theme').value;
    let theme;

    if (themeSelector === 'custom') {
        theme = document.getElementById('custom-theme').value || undefined;
    } else {
        theme = themeSelector || undefined;
    }

    const updates = {
        ollama: {
            theme: theme
        },
        schedule: {
            base_interval: parseInt(document.getElementById('base-interval').value),
            jitter_range: parseInt(document.getElementById('jitter-range').value)
        },
        git: {
            push_enabled: document.getElementById('push-enabled').checked
        }
    };

    try {
        const response = await fetch(`${API_BASE}/api/settings/config`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updates)
        });

        const data = await response.json();

        if (data.success) {
            alert('Configuration updated!');
        }

    } catch (error) {
        console.error('Error updating config:', error);
        alert('Failed to update configuration');
    }
});

// Auto-refresh
let refreshInterval;

function startAutoRefresh() {
    refreshInterval = setInterval(() => {
        const activeTab = document.querySelector('.tab-content.active').id;
        if (activeTab === 'dashboard-tab') {
            loadDashboard();
        }
    }, 5000);
}

function stopAutoRefresh() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadDashboard();
    loadSettings();
    startAutoRefresh();
});

window.addEventListener('beforeunload', stopAutoRefresh);
