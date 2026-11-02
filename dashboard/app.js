/**
 * Autonomous Software Engineer — Dashboard
 * Single-file SPA with hash-based routing and live polling.
 */

/* ── API Client ──────────────────────────────────────────────────────── */
const API = {
  base: window.location.origin,

  async get(path) {
    const r = await fetch(this.base + path);
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
  },

  async post(path, body) {
    const r = await fetch(this.base + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: r.statusText }));
      throw new Error(err.detail || r.statusText);
    }
    return r.json();
  },

  health:       () => API.get('/health'),
  listTasks:    () => API.get('/process-issue'),
  getTask:      (id) => API.get(`/process-issue/${id}`),
  listIndices:  () => API.get('/indices'),
  indexRepo:    (path) => API.post('/index-repository', { repository_path: path }),
  submitIssue:  (body) => API.post('/process-issue', body),
  submitGH:     (body) => API.post('/process-github-issue', body),
};

/* ── Toast ───────────────────────────────────────────────────────────── */
const toastEl = document.createElement('div');
toastEl.className = 'toast-container';
document.body.appendChild(toastEl);

function toast(msg, type = 'info') {
  const t = document.createElement('div');
  const icons = { success: '✅', error: '❌', info: 'ℹ️' };
  t.className = `toast ${type}`;
  t.innerHTML = `<span>${icons[type] || ''}</span><span>${msg}</span>`;
  toastEl.appendChild(t);
  setTimeout(() => { t.style.opacity = '0'; t.style.transition = 'opacity 0.3s'; setTimeout(() => t.remove(), 300); }, 3000);
}

/* ── Router ──────────────────────────────────────────────────────────── */
const main = document.getElementById('main-content');
let _pollTimer = null;
let _healthTimer = null;

function navigate(hash) {
  clearInterval(_pollTimer);
  _pollTimer = null;

  const [view, param] = hash.replace('#', '').split('/');
  // update nav active state
  document.querySelectorAll('.nav-item').forEach(el => {
    el.classList.toggle('active', el.dataset.view === view);
  });

  switch (view) {
    case 'overview':     renderOverview();              break;
    case 'submit':       renderSubmit();                break;
    case 'history':      renderHistory();               break;
    case 'repositories': renderRepositories();          break;
    case 'task':         renderTask(param);             break;
    default:             renderOverview();              break;
  }
}

window.addEventListener('hashchange', () => navigate(location.hash || '#overview'));
window.addEventListener('DOMContentLoaded', () => {
  startHealthCheck();
  navigate(location.hash || '#overview');
});

/* ── Health check ────────────────────────────────────────────────────── */
function startHealthCheck() {
  const dot   = document.getElementById('health-dot');
  const label = document.getElementById('health-label');

  async function check() {
    try {
      const data = await API.health();
      dot.className = 'health-dot online';
      label.textContent = `v${data.version}`;
    } catch {
      dot.className = 'health-dot offline';
      label.textContent = 'Offline';
    }
  }
  check();
  _healthTimer = setInterval(check, 10000);
}

/* ── Helpers ─────────────────────────────────────────────────────────── */
function badge(status) {
  const map = {
    completed: ['badge-green',  'Completed'],
    running:   ['badge-amber',  'Running'],
    pending:   ['badge-blue',   'Pending'],
    failed:    ['badge-red',    'Failed'],
    done:      ['badge-green',  'Done'],
  };
  const [cls, label] = map[status] || ['badge-muted', status];
  return `<span class="badge ${cls}">${label}</span>`;
}

function relativeTime(iso) {
  if (!iso) return '—';
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function repoSlug(url) {
  if (!url) return '—';
  return url.replace('https://github.com/', '');
}

function stepIcon(status) {
  if (status === 'done')    return `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>`;
  if (status === 'running') return `<div class="spinner"></div>`;
  if (status === 'failed')  return `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`;
  return `<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="4" opacity="0.4"/></svg>`;
}

const STEP_META = [
  { key: 'clone',    label: 'Clone / Pull Repository' },
  { key: 'index',    label: 'Index Repository (Tree-sitter + FAISS)' },
  { key: 'analyze',  label: 'Analyze Issue (LLM)' },
  { key: 'retrieve', label: 'Retrieve Context (Hybrid Search)' },
  { key: 'generate', label: 'Generate Fix (LLM)' },
  { key: 'apply',    label: 'Apply Patch & Format (ruff + black)' },
  { key: 'test',     label: 'Run Tests (Docker Sandbox)' },
  { key: 'pr',       label: 'Create Pull Request (GitHub)' },
];

/* ══ VIEWS ═══════════════════════════════════════════════════════════════ */

/* ── Overview ─────────────────────────────────────────────────────────── */
async function renderOverview() {
  main.innerHTML = `
    <div class="page-header">
      <h1 class="page-title">Overview</h1>
      <p class="page-subtitle">Real-time pipeline activity and system health</p>
    </div>
    <div class="stats-grid" id="stats-grid">
      ${[...Array(4)].map(() => `<div class="stat-card"><div class="loading" style="padding:10px">…</div></div>`).join('')}
    </div>
    <div class="card">
      <div class="card-title">Recent Activity</div>
      <div id="activity-list"><div class="loading"><div class="spinner"></div> Loading…</div></div>
    </div>`;

  try {
    const tasks = await API.listTasks();
    const total     = tasks.length;
    const completed = tasks.filter(t => t.status === 'completed').length;
    const failed    = tasks.filter(t => t.status === 'failed').length;
    const running   = tasks.filter(t => t.status === 'running' || t.status === 'pending').length;

    document.getElementById('stats-grid').innerHTML = `
      <div class="stat-card"><div class="stat-label">Total Tasks</div><div class="stat-value accent">${total}</div></div>
      <div class="stat-card"><div class="stat-label">Completed</div><div class="stat-value green">${completed}</div></div>
      <div class="stat-card"><div class="stat-label">Failed</div><div class="stat-value red">${failed}</div></div>
      <div class="stat-card"><div class="stat-label">In Progress</div><div class="stat-value amber">${running}</div></div>`;

    const recent = tasks.slice(0, 8);
    if (!recent.length) {
      document.getElementById('activity-list').innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">🚀</div>
          <div class="empty-title">No tasks yet</div>
          <div class="empty-sub">Submit your first issue to get started</div>
        </div>`;
      return;
    }

    const statusIcons = { completed: '✅', failed: '❌', running: '🔄', pending: '⏳' };
    const statusBg    = { completed: 'var(--green-bg)', failed: 'var(--red-bg)', running: 'var(--amber-bg)', pending: 'var(--blue-bg)' };

    document.getElementById('activity-list').innerHTML = `
      <div class="activity-list">
        ${recent.map(t => `
          <div class="activity-item" onclick="location.hash='#task/${t.task_id}'">
            <div class="activity-left">
              <div class="activity-icon" style="background:${statusBg[t.status] || 'var(--surface-2)'}">
                ${statusIcons[t.status] || '⬜'}
              </div>
              <div class="activity-info">
                <div class="activity-title">${escHtml(t.title)}</div>
                <div class="activity-repo">${repoSlug(t.github_url)}</div>
              </div>
            </div>
            <div style="display:flex;align-items:center;gap:10px">
              ${badge(t.status)}
              <span class="activity-time">${relativeTime(t.submitted_at)}</span>
            </div>
          </div>`).join('')}
      </div>`;
  } catch (e) {
    document.getElementById('activity-list').innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><div class="empty-title">Could not load tasks</div><div class="empty-sub">${e.message}</div></div>`;
  }
}

/* ── Submit ───────────────────────────────────────────────────────────── */
function renderSubmit() {
  main.innerHTML = `
    <div class="page-header">
      <h1 class="page-title">Submit Issue</h1>
      <p class="page-subtitle">Start the autonomous fix pipeline for a GitHub issue</p>
    </div>
    <div style="max-width:640px">
      <div class="tabs">
        <button class="tab-btn active" id="tab-manual" onclick="switchTab('manual')">Manual</button>
        <button class="tab-btn" id="tab-github" onclick="switchTab('github')">GitHub Native</button>
      </div>

      <!-- Manual form -->
      <div id="form-manual" class="card">
        <form onsubmit="submitManual(event)">
          <div class="form-group">
            <label class="form-label">Issue Title *</label>
            <input class="form-input" id="m-title" placeholder="e.g. Registration fails when email is null" required />
          </div>
          <div class="form-group">
            <label class="form-label">Description *</label>
            <textarea class="form-textarea" id="m-desc" placeholder="Describe the bug in detail…" required></textarea>
          </div>
          <div class="form-group">
            <label class="form-label">GitHub Repository URL *</label>
            <input class="form-input" id="m-url" placeholder="https://github.com/owner/repo" required />
          </div>
          <div class="form-group">
            <label class="form-label">Issue Number (optional)</label>
            <input class="form-input" id="m-num" type="number" placeholder="42" />
          </div>
          <button type="submit" class="btn btn-primary" id="submit-btn-manual">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="13 17 18 12 13 7"/><polyline points="6 17 11 12 6 7"/></svg>
            Start Pipeline
          </button>
        </form>
      </div>

      <!-- GitHub native form -->
      <div id="form-github" class="card" style="display:none">
        <div style="background:var(--blue-bg);border:1px solid rgba(59,130,246,0.2);border-radius:var(--radius);padding:12px 14px;margin-bottom:18px;font-size:13px;color:var(--text-dim)">
          ℹ️ This mode fetches the issue title and body directly from the GitHub API. Requires <code>GITHUB_TOKEN</code> to be configured.
        </div>
        <form onsubmit="submitGitHub(event)">
          <div class="form-group">
            <label class="form-label">GitHub Repository URL *</label>
            <input class="form-input" id="g-url" placeholder="https://github.com/owner/repo" required />
          </div>
          <div class="form-group">
            <label class="form-label">Issue Number *</label>
            <input class="form-input" id="g-num" type="number" placeholder="42" required />
          </div>
          <button type="submit" class="btn btn-primary" id="submit-btn-github">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="13 17 18 12 13 7"/><polyline points="6 17 11 12 6 7"/></svg>
            Fetch & Start Pipeline
          </button>
        </form>
      </div>
    </div>`;
}

window.switchTab = function(tab) {
  document.getElementById('tab-manual').classList.toggle('active', tab === 'manual');
  document.getElementById('tab-github').classList.toggle('active', tab === 'github');
  document.getElementById('form-manual').style.display = tab === 'manual' ? '' : 'none';
  document.getElementById('form-github').style.display = tab === 'github' ? '' : 'none';
};

window.submitManual = async function(e) {
  e.preventDefault();
  const btn = document.getElementById('submit-btn-manual');
  btn.disabled = true;
  btn.innerHTML = `<div class="spinner"></div> Starting…`;
  try {
    const result = await API.submitIssue({
      title:        document.getElementById('m-title').value,
      description:  document.getElementById('m-desc').value,
      github_url:   document.getElementById('m-url').value,
      issue_number: parseInt(document.getElementById('m-num').value) || null,
    });
    toast('Pipeline started!', 'success');
    location.hash = `#task/${result.task_id}`;
  } catch (err) {
    toast(`Failed: ${err.message}`, 'error');
    btn.disabled = false;
    btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="13 17 18 12 13 7"/><polyline points="6 17 11 12 6 7"/></svg> Start Pipeline`;
  }
};

window.submitGitHub = async function(e) {
  e.preventDefault();
  const btn = document.getElementById('submit-btn-github');
  btn.disabled = true;
  btn.innerHTML = `<div class="spinner"></div> Fetching & Starting…`;
  try {
    const result = await API.submitGH({
      github_url:   document.getElementById('g-url').value,
      issue_number: parseInt(document.getElementById('g-num').value),
    });
    toast('Pipeline completed!', 'success');
    // Sync endpoint returns result directly — show it differently
    showSyncResult(result);
  } catch (err) {
    toast(`Failed: ${err.message}`, 'error');
    btn.disabled = false;
    btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="13 17 18 12 13 7"/><polyline points="6 17 11 12 6 7"/></svg> Fetch & Start Pipeline`;
  }
};

function showSyncResult(r) {
  const extra = document.createElement('div');
  extra.className = 'result-panel';
  extra.style.maxWidth = '640px';
  extra.innerHTML = buildResultPanel(r);
  main.appendChild(extra);
}

/* ── Task / Live Pipeline View ────────────────────────────────────────── */
async function renderTask(taskId) {
  if (!taskId) { location.hash = '#history'; return; }

  main.innerHTML = `
    <div class="page-header" style="display:flex;align-items:center;gap:14px">
      <button class="btn btn-ghost" onclick="history.back()">← Back</button>
      <div>
        <h1 class="page-title" id="task-title">Loading task…</h1>
        <p class="page-subtitle" id="task-subtitle"></p>
      </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;align-items:start">
      <div>
        <div class="card">
          <div class="card-title">Pipeline Progress <span id="task-status-badge"></span></div>
          <div class="pipeline-tracker" id="pipeline-tracker">
            ${STEP_META.map(s => renderStepHtml(s.key, s.label, { status: 'pending' })).join('')}
          </div>
        </div>
      </div>
      <div id="result-col"></div>
    </div>`;

  async function poll() {
    try {
      const task = await API.getTask(taskId);

      document.getElementById('task-title').textContent = task.title || `Task ${taskId.slice(0, 8)}`;
      document.getElementById('task-subtitle').textContent = repoSlug(task.github_url);
      document.getElementById('task-status-badge').innerHTML = badge(task.status);

      // Update pipeline steps
      if (task.steps) {
        const tracker = document.getElementById('pipeline-tracker');
        if (tracker) {
          tracker.innerHTML = STEP_META.map(s => renderStepHtml(s.key, s.label, task.steps[s.key] || { status: 'pending' })).join('');
        }
      }

      // Show result panel when done
      const resultCol = document.getElementById('result-col');
      if (resultCol && task.status === 'completed' && task.result) {
        resultCol.innerHTML = `
          <div class="card">
            <div class="card-title">Results</div>
            ${buildResultPanel(task.result)}
          </div>`;
      } else if (resultCol && task.status === 'failed') {
        resultCol.innerHTML = `
          <div class="card">
            <div class="card-title" style="color:var(--red)">Pipeline Failed</div>
            <div class="terminal">${escHtml(task.error || 'Unknown error')}</div>
          </div>`;
      }

      // Keep polling if still running
      if (task.status === 'pending' || task.status === 'running') {
        _pollTimer = setTimeout(poll, 2000);
      }
    } catch (e) {
      toast(`Poll error: ${e.message}`, 'error');
    }
  }

  poll();
}

function renderStepHtml(key, label, step) {
  const s = step || { status: 'pending' };
  return `
    <div class="pipeline-step ${s.status}" id="step-${key}">
      <div class="step-icon">${stepIcon(s.status)}</div>
      <div class="step-body">
        <div class="step-name">${label}</div>
        ${s.detail ? `<div class="step-detail">${escHtml(s.detail)}</div>` : ''}
        ${s.duration != null ? `<div class="step-duration">${s.duration}s</div>` : ''}
      </div>
    </div>`;
}

function buildResultPanel(r) {
  const prBtn = r.pr_url
    ? `<a class="pr-button" href="${r.pr_url}" target="_blank" rel="noopener">
         <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><path d="M13 6h3a2 2 0 0 1 2 2v7"/><line x1="6" y1="9" x2="6" y2="21"/></svg>
         View Pull Request #${r.pr_number || ''}
       </a>`
    : `<span class="badge badge-muted">No PR created</span>`;

  const testBadge = r.test_passed
    ? `<span class="badge badge-green">✅ Tests Passed</span>`
    : `<span class="badge badge-red">❌ Tests Failed</span>`;

  return `
    <div style="margin-bottom:16px">${prBtn}</div>
    <div class="result-section">
      <div class="result-section-label">Test Result</div>
      <div>${testBadge}</div>
    </div>
    ${r.root_cause ? `
    <div class="result-section">
      <div class="result-section-label">Root Cause</div>
      <div class="result-section-value">${escHtml(r.root_cause)}</div>
    </div>` : ''}
    ${r.files_changed && r.files_changed.length ? `
    <div class="result-section">
      <div class="result-section-label">Files Changed</div>
      <div style="display:flex;flex-wrap:wrap;gap:6px">
        ${r.files_changed.map(f => `<code style="background:var(--surface-2);border:1px solid var(--border);border-radius:5px;padding:3px 8px;font-size:12px;font-family:'JetBrains Mono',monospace">${escHtml(f)}</code>`).join('')}
      </div>
    </div>` : ''}
    ${r.pr_title ? `
    <div class="result-section">
      <div class="result-section-label">PR Title</div>
      <div class="result-section-value" style="font-family:'JetBrains Mono',monospace;font-size:13px">${escHtml(r.pr_title)}</div>
    </div>` : ''}`;
}

/* ── History ──────────────────────────────────────────────────────────── */
async function renderHistory() {
  main.innerHTML = `
    <div class="page-header">
      <h1 class="page-title">Task History</h1>
      <p class="page-subtitle">All submitted pipeline tasks</p>
    </div>
    <div class="card" style="padding:0;overflow:hidden">
      <div id="history-content"><div class="loading"><div class="spinner"></div> Loading…</div></div>
    </div>`;

  try {
    const tasks = await API.listTasks();
    const el = document.getElementById('history-content');
    if (!tasks.length) {
      el.innerHTML = `<div class="empty-state"><div class="empty-icon">📋</div><div class="empty-title">No tasks yet</div><div class="empty-sub">Submit an issue to get started</div></div>`;
      return;
    }
    el.innerHTML = `
      <table class="data-table">
        <thead>
          <tr>
            <th>Issue</th>
            <th>Status</th>
            <th>Pull Request</th>
            <th>Submitted</th>
          </tr>
        </thead>
        <tbody>
          ${tasks.map(t => `
            <tr onclick="location.hash='#task/${t.task_id}'">
              <td>
                <div class="task-title">${escHtml(t.title)}</div>
                <div class="task-repo">${repoSlug(t.github_url)}</div>
              </td>
              <td>${badge(t.status)}</td>
              <td class="link-cell">
                ${t.pr_url ? `<a href="${t.pr_url}" target="_blank" rel="noopener" onclick="event.stopPropagation()">View PR →</a>` : '<span style="color:var(--text-muted)">—</span>'}
              </td>
              <td><span class="mono">${relativeTime(t.submitted_at)}</span></td>
            </tr>`).join('')}
        </tbody>
      </table>`;
  } catch (e) {
    document.getElementById('history-content').innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><div class="empty-title">Failed to load</div><div class="empty-sub">${e.message}</div></div>`;
  }
}

/* ── Repositories ────────────────────────────────────────────────────── */
async function renderRepositories() {
  main.innerHTML = `
    <div class="page-header" style="display:flex;align-items:flex-start;justify-content:space-between">
      <div>
        <h1 class="page-title">Repositories</h1>
        <p class="page-subtitle">Indexed repositories and their symbol databases</p>
      </div>
      <button class="btn btn-secondary" onclick="showIndexForm()">+ Index New Repo</button>
    </div>
    <div id="index-form-container"></div>
    <div id="repo-grid-container"><div class="loading"><div class="spinner"></div> Loading…</div></div>`;

  loadRepoGrid();
}

async function loadRepoGrid() {
  const el = document.getElementById('repo-grid-container');
  try {
    const indices = await API.listIndices();
    if (!indices.length) {
      el.innerHTML = `<div class="empty-state"><div class="empty-icon">📦</div><div class="empty-title">No indexed repositories</div><div class="empty-sub">Submit an issue or index a repository manually to see it here</div></div>`;
      return;
    }
    el.innerHTML = `<div class="repo-grid">${indices.map(r => repoCardHtml(r)).join('')}</div>`;
  } catch (e) {
    el.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><div class="empty-title">Failed to load</div><div class="empty-sub">${e.message}</div></div>`;
  }
}

function repoCardHtml(r) {
  const indexedAt = r.indexed_at ? new Date(r.indexed_at).toLocaleString() : '—';
  return `
    <div class="repo-card">
      <div class="repo-name">${escHtml(r.repo_name)}</div>
      <div class="repo-path" title="${escHtml(r.repository_path)}">${escHtml(r.repository_path)}</div>
      <div class="repo-stats">
        <div class="repo-stat">
          <div class="repo-stat-val">${r.total_symbols.toLocaleString()}</div>
          <div class="repo-stat-label">Symbols</div>
        </div>
        <div class="repo-stat">
          <div class="repo-stat-val">${r.total_files.toLocaleString()}</div>
          <div class="repo-stat-label">Files</div>
        </div>
      </div>
      <div class="repo-indexed-at">Last indexed: ${indexedAt}</div>
      <button class="btn btn-secondary" style="width:100%" onclick="reindexRepo('${escHtml(r.repository_path)}', this)">
        🔄 Re-index
      </button>
    </div>`;
}

window.reindexRepo = async function(path, btn) {
  btn.disabled = true;
  btn.innerHTML = `<div class="spinner" style="margin:0 auto"></div>`;
  try {
    const result = await API.indexRepo(path);
    toast(`Re-indexed: ${result.total_symbols} symbols`, 'success');
    loadRepoGrid();
  } catch (e) {
    toast(`Failed: ${e.message}`, 'error');
    btn.disabled = false;
    btn.innerHTML = '🔄 Re-index';
  }
};

window.showIndexForm = function() {
  const c = document.getElementById('index-form-container');
  if (c.innerHTML) { c.innerHTML = ''; return; }
  c.innerHTML = `
    <div class="card" style="max-width:540px;margin-bottom:20px">
      <div class="card-title">Index a Local Repository</div>
      <div class="form-group">
        <label class="form-label">Absolute Repository Path</label>
        <input class="form-input" id="idx-path" placeholder="/absolute/path/to/repo" />
      </div>
      <button class="btn btn-primary" onclick="manualIndex()">Index Repository</button>
    </div>`;
};

window.manualIndex = async function() {
  const path = document.getElementById('idx-path').value.trim();
  if (!path) return toast('Enter a repository path', 'error');
  try {
    const result = await API.indexRepo(path);
    toast(`Indexed ${result.total_symbols} symbols from ${result.total_files} files`, 'success');
    document.getElementById('index-form-container').innerHTML = '';
    loadRepoGrid();
  } catch (e) {
    toast(`Failed: ${e.message}`, 'error');
  }
};

/* ── Utility ─────────────────────────────────────────────────────────── */
function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
