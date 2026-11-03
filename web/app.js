'use strict';

/* =========================================================================
 * 学伴 · AI 学习资料总结 — 前端逻辑
 * 纯原生 JavaScript，无构建、无外部依赖，所有接口均为同源相对路径。
 * ========================================================================= */

/* ------------------------------ 常量定义 ------------------------------ */

const KIND_BY_EXT = {
  pdf: 'pdf',
  ppt: 'ppt',
  pptx: 'ppt',
  doc: 'word',
  docx: 'word',
  txt: 'text',
  md: 'text',
  xlsx: 'sheet',
  xls: 'sheet',
  mp4: 'video',
  mkv: 'video',
  mov: 'video',
  avi: 'video',
  webm: 'video',
  mp3: 'audio',
  wav: 'audio',
  m4a: 'audio',
  flac: 'audio',
  ogg: 'audio',
};

const KIND_LABEL = {
  pdf: 'PDF',
  ppt: 'PPT',
  word: 'Word',
  sheet: '表格',
  video: '视频',
  audio: '音频',
  text: '文本',
  other: '文件',
};

const PROFILE_LABELS = { quick: '快速', standard: '标准', deep: '深度' };

const STAGE_INDEX = { extract: 1, transcribe: 2, analyze: 3, render: 4, done: 4 };

const STAGE_TEXT = {
  extract: '正在解析学习资料…',
  transcribe: '正在转写音视频内容…',
  analyze: '正在用 AI 提炼知识点…',
  render: '正在排版生成 PDF…',
  done: '即将完成…',
};

const STATUS_META = {
  done: { label: '完成', tone: 'success' },
  failed: { label: '失败', tone: 'danger' },
  running: { label: '进行中', tone: 'info' },
  pending: { label: '进行中', tone: 'info' },
  cancelled: { label: '已取消', tone: 'muted' },
};

const MAX_POLL_FAILURES = 5;

const PANEL_IDS = ['progressPanel', 'resultPanel', 'errorPanel'];

const ICONS = {
  check:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 12.6 4.2 4.2L19 6.4"/></svg>',
  x:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>',
  download:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 4v11"/><path d="m7.5 10.7 4.5 4.5 4.5-4.5"/><path d="M5 19.5h14"/></svg>',
  trash:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4.5 6.5h15"/><path d="M9 6.5V4.7c0-.7.6-1.2 1.2-1.2h3.6c.7 0 1.2.6 1.2 1.2v1.8"/><path d="M6.5 6.5l.8 12.2c0 .9.8 1.6 1.7 1.6h6c.9 0 1.7-.7 1.7-1.6l.8-12.2"/><path d="M10 10.5v6M14 10.5v6"/></svg>',
  checkCircle:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="m8 12.3 2.8 2.8 5.4-5.4"/></svg>',
  alertCircle:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7.5v5.2"/><circle cx="12" cy="16.4" r="1.1" fill="currentColor" stroke="none"/></svg>',
  infoCircle:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 11v5.5"/><circle cx="12" cy="7.8" r="1.1" fill="currentColor" stroke="none"/></svg>',
};

/* ------------------------------ 运行时状态 ------------------------------ */

const state = {
  files: [], // { file, name, size, kind, key }
  profile: 'standard',
  providers: [],
  settings: null,
  jobId: null,
  job: null,
  busy: false,
  pollTimer: null,
  pollToken: 0,
  pollFailures: 0,
  history: [],
};

const el = {};
let overlayStack = [];
let confirmResolver = null;
let dragDepth = 0;

/* ------------------------------ 通用工具 ------------------------------ */

function escapeHtml(value) {
  const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  return String(value == null ? '' : value).replace(/[&<>"']/g, (ch) => map[ch]);
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function normalizeUrl(url) {
  return String(url || '').trim().replace(/\/+$/, '').toLowerCase();
}

function formatSize(bytes) {
  const value = Number(bytes);
  if (!Number.isFinite(value) || value < 0) return '—';
  if (value < 1024) return `${value} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let size = value / 1024;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  const digits = size >= 100 ? 0 : size >= 10 ? 1 : 2;
  return `${size.toFixed(digits)} ${units[unit]}`;
}

function formatTime(value) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  const pad = (num) => String(num).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function detectKind(filename) {
  const parts = String(filename || '').split('.');
  if (parts.length < 2) return null;
  const ext = parts.pop().toLowerCase();
  return KIND_BY_EXT[ext] || null;
}

function fileIconSvg(kind) {
  const shapes = {
    pdf:
      '<path d="M7 2.8h6.2L19 8.5v12.2H7z"/><path d="M13.2 2.8v5.7H19"/><path d="M9.6 13.2h4.8M9.6 16.4h4.8"/>',
    ppt:
      '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M12 16v4M8.5 20h7"/><path d="m10.6 8.2 3.4 1.9-3.4 1.9z" fill="currentColor" stroke="none"/>',
    word:
      '<path d="M7 2.8h6.2L19 8.5v12.2H7z"/><path d="M13.2 2.8v5.7H19"/><path d="M9.8 12.6h4.4M9.8 15h4.4M9.8 17.4h2.6"/>',
    text:
      '<path d="M7 2.8h6.2L19 8.5v12.2H7z"/><path d="M13.2 2.8v5.7H19"/><path d="M9.8 12h4.4M9.8 14.6h4.4M9.8 17.2h3"/>',
    sheet:
      '<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M4 9.5h16M4 14.5h16M9.5 4v16M14.5 4v16"/>',
    video:
      '<rect x="3" y="5" width="18" height="14" rx="2.5"/><path d="m10.5 9.2 4.8 2.8-4.8 2.8z" fill="currentColor" stroke="none"/>',
    audio:
      '<path d="M9 17.5V6.8l9-1.8v10.4"/><circle cx="6.8" cy="17.6" r="2.4"/><circle cx="15.8" cy="15.6" r="2.4"/>',
    other:
      '<path d="M7 2.8h6.2L19 8.5v12.2H7z"/><path d="M13.2 2.8v5.7H19"/>',
  };
  const shape = shapes[kind] || shapes.other;
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${shape}</svg>`;
}

/* ------------------------------ 接口请求 ------------------------------ */

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function api(path, options) {
  let response;
  try {
    response = await fetch(path, options || {});
  } catch (error) {
    throw new ApiError('网络连接失败，请检查学伴服务是否已启动', 0);
  }
  let data = null;
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    try {
      data = await response.json();
    } catch (error) {
      data = null;
    }
  }
  if (!response.ok) {
    const message = (data && (data.error || data.message)) || `请求失败（HTTP ${response.status}）`;
    throw new ApiError(message, response.status);
  }
  return data;
}

function postJSON(path, body) {
  return api(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

/* ------------------------------ 初始化 ------------------------------ */

function init() {
  cacheDom();
  bindEvents();
  selectProfile('standard');
  renderFileList();
  updateStartState();
  loadInitialData();
}

function cacheDom() {
  const ids = [
    'btnHistory', 'btnSettings', 'guideBanner', 'btnGuideSettings',
    'dropzone', 'fileInput', 'fileList', 'fileSummary', 'fileCount', 'btnClearFiles',
    'btnStart', 'actionHint',
    'progressPanel', 'progressFiles', 'btnCancel', 'stepper', 'progressTrack',
    'progressFill', 'progressPercent', 'progressMessage',
    'resultPanel', 'resultMeta', 'pdfFrame', 'btnDownload', 'btnAgain',
    'errorPanel', 'errorText', 'btnRetry', 'btnBack',
    'settingsModal', 'btnCloseSettings', 'setProvider', 'providerHint',
    'setBaseUrl', 'setModel', 'modelOptions', 'setApiKey', 'apiKeyState',
    'setTemp', 'tempValue', 'setAsrModel', 'setAsrPath', 'setAsrDevice', 'setAsrLanguage',
    'btnTest', 'btnSave', 'btnCancelSettings', 'testResult',
    'confirmModal', 'confirmTitle', 'confirmMessage', 'confirmOk', 'confirmCancel',
    'historyDrawer', 'btnCloseHistory', 'btnRefreshHistory',
    'historyList', 'historyEmpty', 'historyEmptyText', 'historyLoading',
    'toastStack', 'footerVersion',
  ];
  ids.forEach((id) => {
    el[id] = document.getElementById(id);
  });
}

async function loadInitialData() {
  const [settingsResult, providersResult, healthResult] = await Promise.allSettled([
    api('/api/settings'),
    api('/api/providers'),
    api('/api/health'),
  ]);

  if (settingsResult.status === 'fulfilled' && settingsResult.value) {
    state.settings = settingsResult.value;
  } else {
    toast('无法连接后端服务，请确认学伴服务已启动', 'error');
  }

  if (providersResult.status === 'fulfilled' && Array.isArray(providersResult.value)) {
    state.providers = providersResult.value;
  }

  if (healthResult.status === 'fulfilled' && healthResult.value) {
    setFooterVersion(healthResult.value.version);
  }

  updateGuideBanner();
}

function setFooterVersion(version) {
  if (!el.footerVersion) return;
  el.footerVersion.textContent = version ? `学伴 v${version} · 本地运行` : '学伴 · 本地运行';
}

/* ------------------------------ 文件管理 ------------------------------ */

function addFiles(fileList) {
  const incoming = Array.from(fileList || []);
  if (!incoming.length) return;

  let added = 0;
  let skipped = 0;

  incoming.forEach((file) => {
    const kind = detectKind(file.name);
    if (!kind) {
      skipped += 1;
      return;
    }
    const key = `${file.name}::${file.size}::${file.lastModified}`;
    if (state.files.some((item) => item.key === key)) {
      skipped += 1;
      return;
    }
    state.files.push({ file, name: file.name, size: file.size, kind, key });
    added += 1;
  });

  if (!added && !skipped) return;

  renderFileList();
  updateStartState();

  if (added) toast(`已添加 ${added} 个文件`, 'success');
  if (skipped) toast(`${skipped} 个文件格式不支持或已在列表中`, 'info');
}

function removeFile(index) {
  if (state.busy) return;
  if (!Number.isInteger(index) || index < 0 || index >= state.files.length) return;
  state.files.splice(index, 1);
  renderFileList();
  updateStartState();
}

function clearFiles() {
  if (state.busy) return;
  if (!state.files.length) return;
  state.files = [];
  renderFileList();
  updateStartState();
  toast('已清空文件列表', 'info');
}

function renderFileList() {
  const hasFiles = state.files.length > 0;
  el.fileSummary.hidden = !hasFiles;
  el.fileCount.textContent = `已添加 ${state.files.length} 个文件`;

  if (!hasFiles) {
    el.fileList.innerHTML = '';
    return;
  }

  el.fileList.innerHTML = state.files
    .map((file, index) => {
      const disabled = state.busy ? ' disabled' : '';
      return `
        <li class="file-item" style="--i:${index}">
          <span class="file-kind kind-${file.kind}" aria-hidden="true">${fileIconSvg(file.kind)}</span>
          <span class="file-info">
            <span class="file-name" title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</span>
            <span class="file-meta">${escapeHtml(KIND_LABEL[file.kind] || '文件')} · ${formatSize(file.size)}</span>
          </span>
          <button type="button" class="icon-btn file-remove" data-remove-index="${index}" aria-label="移除文件 ${escapeHtml(file.name)}"${disabled}>
            ${ICONS.trash}
          </button>
        </li>`;
    })
    .join('');
}

function updateStartState() {
  if (!el.btnStart) return;
  el.btnStart.disabled = state.busy || state.files.length === 0;
  if (state.busy) {
    el.actionHint.textContent = '正在生成学习报告，请稍候…';
  } else if (state.files.length) {
    el.actionHint.textContent = `将上传 ${state.files.length} 个文件，按「${PROFILE_LABELS[state.profile]}」档位生成`;
  } else {
    el.actionHint.textContent = '请先添加学习资料';
  }
}

function setBusy(busy) {
  state.busy = Boolean(busy);
  el.btnStart.classList.toggle('is-loading', state.busy);
  const label = el.btnStart.querySelector('.btn-label');
  if (label) label.textContent = state.busy ? '正在生成…' : '开始生成';
  const spinner = el.btnStart.querySelector('.btn-spinner');
  if (spinner) spinner.hidden = !state.busy;

  el.fileInput.disabled = state.busy;
  if (el.btnClearFiles) el.btnClearFiles.disabled = state.busy;
  el.dropzone.classList.toggle('is-disabled', state.busy);
  el.dropzone.setAttribute('aria-disabled', state.busy ? 'true' : 'false');

  renderFileList();
  updateStartState();
}

function selectProfile(profile) {
  const target = PROFILE_LABELS[profile] ? profile : 'standard';
  state.profile = target;
  document.querySelectorAll('.profile-card').forEach((card) => {
    const selected = card.dataset.profile === target;
    card.classList.toggle('is-selected', selected);
    const input = card.querySelector('input[name="profile"]');
    if (input) input.checked = selected;
  });
  updateStartState();
}

/* ------------------------------ 生成流程 ------------------------------ */

async function startGeneration() {
  if (state.busy) return;
  if (!state.files.length) {
    toast('请先添加学习资料', 'info');
    el.dropzone.focus({ preventScroll: true });
    return;
  }

  stopPolling();
  state.jobId = null;
  state.job = null;
  setBusy(true);
  showOnlyPanel('progress');
  el.progressFiles.textContent = state.files.map((item) => item.name).join('、');
  resetProgressUI();
  scrollPanelIntoView(el.progressPanel);

  try {
    const uploaded = await uploadFiles(
      state.files.map((item) => item.file),
      (percent) => updateProgressBar(percent, `正在上传文件 ${percent}%`)
    );

    const fileIds = uploaded.map((item) => item && item.id).filter(Boolean);
    if (!fileIds.length) throw new Error('上传失败：未获取到文件 ID，请重试。');

    updateProgressBar(100, '文件上传完成，正在创建生成任务…');
    const created = await postJSON('/api/jobs', { file_ids: fileIds, profile: state.profile });
    if (!created || !created.job_id) throw new Error('创建任务失败：服务未返回 job_id。');

    updateProgressBar(0, '任务已创建，正在开始解析…');
    startPolling(created.job_id);
  } catch (error) {
    stopPolling();
    setBusy(false);
    showOnlyPanel('error');
    el.errorText.textContent = (error && error.message) || '生成失败，请稍后重试。';
    scrollPanelIntoView(el.errorPanel);
  }
}

function uploadFiles(files, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/upload', true);
    xhr.responseType = 'json';

    xhr.upload.addEventListener('progress', (event) => {
      if (!event.lengthComputable) return;
      const percent = Math.min(100, Math.round((event.loaded / event.total) * 100));
      if (typeof onProgress === 'function') onProgress(percent);
    });

    xhr.addEventListener('load', () => {
      const data = xhr.response;
      if (xhr.status >= 200 && xhr.status < 300) {
        if (data && Array.isArray(data.files)) resolve(data.files);
        else reject(new Error('上传接口返回格式不正确，请检查后端服务。'));
        return;
      }
      const message = (data && (data.error || data.message)) || `文件上传失败（HTTP ${xhr.status}）`;
      reject(new ApiError(message, xhr.status));
    });

    xhr.addEventListener('error', () => reject(new ApiError('网络错误，文件上传失败', 0)));
    xhr.addEventListener('abort', () => reject(new ApiError('上传已中止', 0)));

    const form = new FormData();
    files.forEach((file) => form.append('files', file, file.name));
    xhr.send(form);
  });
}

function resetProgressUI() {
  updateStepper(1, false);
  updateProgressBar(0, '准备上传文件…');
  el.btnCancel.disabled = false;
  setBtnLoading(el.btnCancel, false, '取消');
}

function startPolling(jobId) {
  stopPolling();
  const token = state.pollToken;
  state.pollFailures = 0;
  state.jobId = jobId;
  state.job = null;
  pollJob(jobId, token);
}

function stopPolling() {
  if (state.pollTimer) {
    clearTimeout(state.pollTimer);
    state.pollTimer = null;
  }
  state.pollToken += 1;
}

async function pollJob(jobId, token) {
  if (token !== state.pollToken) return;

  let job;
  try {
    job = await api(`/api/jobs/${encodeURIComponent(jobId)}`);
  } catch (error) {
    if (token !== state.pollToken) return;
    if (error && error.status === 404) {
      failGeneration('任务不存在或已被删除，请重新生成。');
      return;
    }
    state.pollFailures += 1;
    if (state.pollFailures > MAX_POLL_FAILURES) {
      failGeneration('网络异常，多次尝试仍无法获取生成进度，请检查服务后重试。');
      return;
    }
    const delay = Math.min(8000, 1000 * Math.pow(2, state.pollFailures));
    setProgressMessage(`网络波动，正在重试（${state.pollFailures}/${MAX_POLL_FAILURES}）…`);
    state.pollTimer = setTimeout(() => pollJob(jobId, token), delay);
    return;
  }

  if (token !== state.pollToken) return;
  state.pollFailures = 0;
  state.job = job;
  renderJob(job);

  if (job.status === 'done') {
    stopPolling();
    finishGeneration(job);
  } else if (job.status === 'failed') {
    stopPolling();
    failGeneration(job.error || job.message || '生成失败，请稍后重试。');
  } else if (job.status === 'cancelled') {
    stopPolling();
    onJobCancelled();
  } else {
    state.pollTimer = setTimeout(() => pollJob(jobId, token), 1000);
  }
}

function renderJob(job) {
  const stage = STAGE_INDEX[job.stage] ? job.stage : 'extract';
  const activeStep = STAGE_INDEX[stage];
  const isDone = job.status === 'done';

  updateStepper(activeStep, isDone);

  const rawProgress = Number(job.progress);
  const percent = Number.isFinite(rawProgress) ? clamp(rawProgress, 0, 100) : 0;
  updateProgressBar(isDone ? 100 : percent, job.message || STAGE_TEXT[stage] || '正在处理…');

  if (Array.isArray(job.files) && job.files.length) {
    el.progressFiles.textContent = job.files.join('、');
  }

  el.btnCancel.disabled = ['done', 'failed', 'cancelled'].includes(job.status);
}

async function cancelRunningJob() {
  if (!state.jobId) return;
  setBtnLoading(el.btnCancel, true, '取消中…');
  try {
    await api(`/api/jobs/${encodeURIComponent(state.jobId)}/cancel`, { method: 'POST' });
    setProgressMessage('正在取消任务…');
  } catch (error) {
    toast(error.message || '取消失败，请稍后重试', 'error');
  } finally {
    setBtnLoading(el.btnCancel, false, '取消');
  }
}

function finishGeneration(job) {
  setBusy(false);
  showOnlyPanel('result');

  const result = job.result || {};
  const metaParts = [];
  if (result.filename) metaParts.push(result.filename);
  if (result.pages) metaParts.push(`共 ${result.pages} 页`);
  if (result.created_at) metaParts.push(formatTime(result.created_at));
  el.resultMeta.textContent = metaParts.join(' · ') || '报告已生成，可直接预览或下载。';

  const downloadUrl =
    result.download_url || `/api/jobs/${encodeURIComponent(job.id || state.jobId)}/download`;
  el.pdfFrame.src = downloadUrl;
  el.btnDownload.href = downloadUrl;
  el.btnDownload.setAttribute('download', result.filename || '学伴学习报告.pdf');

  updateStepper(4, true);
  updateProgressBar(100, job.message || '已完成');
  toast('学习报告已生成', 'success');
  scrollPanelIntoView(el.resultPanel);
}

function failGeneration(message) {
  stopPolling();
  setBusy(false);
  showOnlyPanel('error');
  el.errorText.textContent = message || '生成失败，请稍后重试。';
  scrollPanelIntoView(el.errorPanel);
}

function onJobCancelled() {
  stopPolling();
  state.jobId = null;
  state.job = null;
  setBusy(false);
  hideAllPanels();
  el.btnCancel.disabled = false;
  toast('已取消本次生成', 'info');
}

function backToUpload() {
  stopPolling();
  state.jobId = null;
  state.job = null;
  setBusy(false);
  hideAllPanels();
  el.pdfFrame.src = 'about:blank';
  el.btnDownload.removeAttribute('href');
  window.scrollTo({ top: 0, behavior: 'smooth' });
  window.setTimeout(() => el.dropzone.focus({ preventScroll: true }), 320);
}

function showOnlyPanel(name) {
  hideAllPanels();
  const map = { progress: 'progressPanel', result: 'resultPanel', error: 'errorPanel' };
  const target = map[name];
  if (target) el[target].hidden = false;
}

function hideAllPanels() {
  PANEL_IDS.forEach((id) => {
    el[id].hidden = true;
  });
}

function scrollPanelIntoView(panel) {
  if (!panel) return;
  const reduced =
    window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  panel.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' });
}

function updateStepper(activeStep, allDone) {
  Array.from(el.stepper.children).forEach((item, index) => {
    const step = index + 1;
    const done = allDone || step < activeStep;
    const active = !allDone && step === activeStep;
    item.classList.toggle('is-done', done);
    item.classList.toggle('is-active', active);
    item.setAttribute('aria-current', active ? 'step' : 'false');
    const dot = item.querySelector('.step-dot');
    if (dot) dot.innerHTML = done ? ICONS.check : String(step);
  });
}

function updateProgressBar(percent, message) {
  const value = Math.round(clamp(Number(percent) || 0, 0, 100));
  el.progressFill.style.width = `${value}%`;
  el.progressPercent.textContent = `${value}%`;
  el.progressTrack.setAttribute('aria-valuenow', String(value));
  if (typeof message === 'string' && message.trim()) setProgressMessage(message.trim());
}

function setProgressMessage(text) {
  el.progressMessage.textContent = text;
}

function setBtnLoading(button, loading, loadingText) {
  if (!button) return;
  const label = button.querySelector('.btn-label');
  if (!label) return;
  if (!button.dataset.idleLabel) button.dataset.idleLabel = label.textContent;
  const spinner = button.querySelector('.btn-spinner');
  button.classList.toggle('is-loading', Boolean(loading));
  label.textContent = loading ? loadingText || '处理中…' : button.dataset.idleLabel;
  button.disabled = Boolean(loading);
  if (spinner) spinner.hidden = !loading;
}

/* ------------------------------ 设置 ------------------------------ */

function getProviders() {
  return Array.isArray(state.providers) ? state.providers.filter((item) => item && item.id) : [];
}

function findProviderById(id) {
  return getProviders().find((item) => item.id === id) || null;
}

async function openSettings(trigger) {
  if (!el.settingsModal.hidden) return;
  openOverlay(el.settingsModal, trigger);
  clearTestResult();

  if (!state.settings || !state.providers.length) {
    await refreshSettingsData();
  }

  renderProviderOptions();
  fillSettingsForm(state.settings || {});
}

async function refreshSettingsData() {
  const tasks = [];

  if (!state.settings) {
    tasks.push(
      api('/api/settings')
        .then((data) => {
          if (data) state.settings = data;
        })
        .catch(() => {})
    );
  }

  if (!state.providers.length) {
    tasks.push(
      api('/api/providers')
        .then((data) => {
          if (Array.isArray(data)) state.providers = data;
        })
        .catch(() => {})
    );
  }

  await Promise.all(tasks);
  updateGuideBanner();
}

function updateGuideBanner() {
  const hasKey = Boolean(state.settings && state.settings.ai && state.settings.ai.api_key_set);
  el.guideBanner.hidden = hasKey;
}

function renderProviderOptions() {
  const options = getProviders().map(
    (provider) =>
      `<option value="${escapeHtml(provider.id)}">${escapeHtml(provider.name || provider.id)}</option>`
  );
  options.push('<option value="__custom__">自定义</option>');
  el.setProvider.innerHTML = options.join('');
}

function fillSettingsForm(settings) {
  const ai = (settings && settings.ai) || {};
  const asr = (settings && settings.asr) || {};

  const matched = getProviders().find(
    (provider) => normalizeUrl(provider.base_url) === normalizeUrl(ai.base_url)
  );
  el.setProvider.value = matched ? matched.id : '__custom__';

  el.setBaseUrl.value = ai.base_url || '';
  el.setModel.value = ai.model || '';
  el.setApiKey.value = '';

  const hasKey = Boolean(ai.api_key_set);
  const masked = ai.api_key_masked || '';
  el.setApiKey.placeholder = hasKey
    ? masked
      ? `已配置（${masked}），留空则不修改`
      : '已配置，留空则不修改'
    : '请输入 API Key，例如 sk-xxxxxxxx';

  el.apiKeyState.textContent = hasKey ? `当前已保存：${masked || '已配置'}` : '尚未配置 API Key';
  el.apiKeyState.classList.toggle('is-ok', hasKey);
  el.apiKeyState.classList.toggle('is-warn', !hasKey);

  const temperature = Number.isFinite(Number(ai.temperature)) ? Number(ai.temperature) : 0.3;
  const safeTemperature = clamp(temperature, 0, 1);
  el.setTemp.value = String(safeTemperature);
  el.tempValue.textContent = safeTemperature.toFixed(1);

  el.setAsrModel.value = ['tiny', 'base', 'small', 'medium', 'large-v3'].includes(asr.model_size)
    ? asr.model_size
    : 'small';
  el.setAsrDevice.value = ['auto', 'cpu', 'cuda'].includes(asr.device) ? asr.device : 'auto';
  el.setAsrLanguage.value = ['auto', 'zh', 'en'].includes(asr.language) ? asr.language : 'auto';
  if (el.setAsrPath) el.setAsrPath.value = asr.model_path || '';

  syncModelDatalist();
  updateProviderHint();
  clearTestResult();
}

function syncModelDatalist() {
  const provider = findProviderById(el.setProvider.value);
  const models = new Set();

  if (provider && Array.isArray(provider.models)) {
    provider.models.forEach((model) => models.add(model));
  } else {
    getProviders().forEach((item) => {
      if (Array.isArray(item.models)) item.models.forEach((model) => models.add(model));
    });
  }

  el.modelOptions.innerHTML = Array.from(models)
    .filter(Boolean)
    .map((model) => `<option value="${escapeHtml(model)}"></option>`)
    .join('');
}

function updateProviderHint() {
  const provider = findProviderById(el.setProvider.value);
  el.providerHint.classList.remove('is-warn');
  if (provider) {
    el.providerHint.textContent =
      provider.hint || `使用「${provider.name || provider.id}」的 OpenAI 兼容接口`;
  } else {
    el.providerHint.textContent = '自定义服务商：请填写兼容 OpenAI 接口协议的地址';
  }
}

function onProviderChange() {
  const provider = findProviderById(el.setProvider.value);
  if (provider) {
    if (provider.base_url) el.setBaseUrl.value = provider.base_url;
    if (Array.isArray(provider.models) && provider.models.length) {
      el.setModel.value = provider.models[0];
    }
  }
  syncModelDatalist();
  updateProviderHint();
  clearTestResult();
}

function onTempInput() {
  el.tempValue.textContent = Number(el.setTemp.value).toFixed(1);
}

function setTestResult(type, text) {
  if (!el.testResult) return;
  if (!text) {
    clearTestResult();
    return;
  }
  el.testResult.hidden = false;
  el.testResult.className = `test-result is-${type}`;
  el.testResult.textContent = text;
}

function clearTestResult() {
  if (!el.testResult) return;
  el.testResult.hidden = true;
  el.testResult.textContent = '';
  el.testResult.className = 'test-result';
}

async function testConnection() {
  const base_url = el.setBaseUrl.value.trim();
  const api_key = el.setApiKey.value.trim();
  const model = el.setModel.value.trim();

  if (!base_url) {
    setTestResult('error', '请先填写接口地址');
    el.setBaseUrl.focus();
    return;
  }
  if (!model) {
    setTestResult('error', '请先填写模型名称');
    el.setModel.focus();
    return;
  }

  setBtnLoading(el.btnTest, true, '测试中…');
  setTestResult('pending', '正在测试连接…');

  try {
    const data = await postJSON('/api/settings/test', { base_url, api_key, model });
    if (data && data.ok) {
      const latency = Number.isFinite(Number(data.latency_ms))
        ? `${Math.round(Number(data.latency_ms))}ms`
        : '—';
      setTestResult('success', `连接成功，延迟 ${latency}`);
      toast('AI 接口连接成功', 'success');
    } else {
      setTestResult('error', `连接失败：${(data && data.error) || '未知错误'}`);
    }
  } catch (error) {
    setTestResult('error', `连接失败：${error.message || '未知错误'}`);
  } finally {
    setBtnLoading(el.btnTest, false, '测试连接');
  }
}

async function saveSettings() {
  const base_url = el.setBaseUrl.value.trim();
  const model = el.setModel.value.trim();
  const api_key = el.setApiKey.value.trim();
  const temperature = clamp(Number(el.setTemp.value), 0, 1);

  if (!base_url) {
    toast('请填写接口地址', 'error');
    el.setBaseUrl.focus();
    return;
  }
  if (!model) {
    toast('请填写模型名称', 'error');
    el.setModel.focus();
    return;
  }

  const payload = {
    ai: { base_url, model, api_key, temperature },
    asr: {
      model_size: el.setAsrModel.value,
      model_path: (el.setAsrPath && el.setAsrPath.value ? el.setAsrPath.value : '').trim(),
      device: el.setAsrDevice.value,
      language: el.setAsrLanguage.value,
    },
    report: {
      profile:
        (state.settings && state.settings.report && state.settings.report.profile) || 'standard',
    },
  };

  setBtnLoading(el.btnSave, true, '保存中…');

  try {
    await postJSON('/api/settings', payload);

    try {
      const latest = await api('/api/settings');
      if (latest) state.settings = latest;
    } catch (error) {
      if (api_key && state.settings && state.settings.ai) {
        state.settings.ai.api_key_set = true;
        state.settings.ai.api_key_masked = state.settings.ai.api_key_masked || '****';
      }
    }

    updateGuideBanner();
    toast('设置已保存', 'success');
    closeOverlay(el.settingsModal);
  } catch (error) {
    toast(`保存失败：${error.message || '未知错误'}`, 'error');
  } finally {
    setBtnLoading(el.btnSave, false, '保存设置');
  }
}

/* ------------------------------ 历史记录 ------------------------------ */

function openHistoryDrawer() {
  if (!el.historyDrawer.hidden) {
    loadHistory();
    return;
  }
  openOverlay(el.historyDrawer, el.btnHistory);
  loadHistory();
}

async function loadHistory() {
  el.historyLoading.hidden = false;
  el.historyEmpty.hidden = true;
  el.historyEmptyText.textContent = '还没有生成记录';
  el.historyList.innerHTML = '';
  el.btnRefreshHistory.disabled = true;

  try {
    const data = await api('/api/jobs');
    state.history = data && Array.isArray(data.jobs) ? data.jobs : [];
    renderHistory();
  } catch (error) {
    state.history = [];
    el.historyEmpty.hidden = false;
    el.historyEmptyText.textContent = '历史记录加载失败，请点击刷新重试';
    toast(`历史记录加载失败：${error.message || '未知错误'}`, 'error');
  } finally {
    el.historyLoading.hidden = true;
    el.btnRefreshHistory.disabled = false;
  }
}

function renderHistory() {
  const jobs = state.history;

  if (!jobs.length) {
    el.historyList.innerHTML = '';
    el.historyEmpty.hidden = false;
    el.historyEmptyText.textContent = '还没有生成记录';
    return;
  }

  el.historyEmpty.hidden = true;
  el.historyList.innerHTML = jobs.map(historyItemHtml).join('');
}

function historyItemHtml(job) {
  const status = job.status || 'pending';
  const meta = STATUS_META[status] || STATUS_META.pending;
  const name = displayJobName(job);
  const time = formatTime(
    (job.result && job.result.created_at) || job.created_at || job.updated_at
  );
  const pages = job.result && job.result.pages ? `${job.result.pages} 页` : '';
  const safeId = escapeHtml(job.id || '');
  const canDownload = status === 'done' && Boolean(job.id);
  const downloadUrl =
    (job.result && job.result.download_url) ||
    (job.id ? `/api/jobs/${encodeURIComponent(job.id)}/download` : '#');
  const filename = (job.result && job.result.filename) || '学伴学习报告.pdf';

  const actions = [
    canDownload
      ? `<a class="icon-btn" href="${escapeHtml(downloadUrl)}" download="${escapeHtml(filename)}" title="下载 PDF" aria-label="下载 PDF">${ICONS.download}</a>`
      : '',
    `<button type="button" class="icon-btn icon-btn-danger" data-history-delete="${safeId}" title="删除记录" aria-label="删除记录">${ICONS.trash}</button>`,
  ].join('');

  return `
    <li class="history-item">
      <span class="status-dot dot-${escapeHtml(status)}" aria-hidden="true"></span>
      <div class="history-main">
        <p class="history-name" title="${escapeHtml(name)}">${escapeHtml(name)}</p>
        <p class="history-meta">
          <span class="badge badge-${meta.tone}">${meta.label}</span>
          <span>${escapeHtml(time)}</span>
          ${pages ? `<span>${escapeHtml(pages)}</span>` : ''}
        </p>
      </div>
      <div class="history-actions">${actions}</div>
    </li>`;
}

function displayJobName(job) {
  if (job && Array.isArray(job.files) && job.files.length) return job.files.join('、');
  if (job && job.result && job.result.filename) return job.result.filename;
  return job && job.id ? `任务 ${job.id}` : '未命名任务';
}

async function onHistoryListClick(event) {
  const button = event.target.closest('[data-history-delete]');
  if (!button) return;

  const jobId = button.getAttribute('data-history-delete');
  if (!jobId) return;

  const job = state.history.find((item) => item.id === jobId);
  const name = job ? displayJobName(job) : '这条记录';

  const confirmed = await confirmDialog({
    title: '删除历史记录',
    message: `确定删除「${name}」吗？删除后该任务与报告文件将无法恢复。`,
    confirmText: '删除',
    danger: true,
  });
  if (!confirmed) return;

  try {
    await api(`/api/jobs/${encodeURIComponent(jobId)}`, { method: 'DELETE' });
    state.history = state.history.filter((item) => item.id !== jobId);
    renderHistory();
    toast('已删除历史记录', 'success');
    if (state.jobId === jobId) backToUpload();
  } catch (error) {
    toast(`删除失败：${error.message || '未知错误'}`, 'error');
  }
}

/* ------------------------------ 弹窗与焦点 ------------------------------ */

function openOverlay(root, trigger) {
  if (!root) return;
  if (!root.hidden && root.classList.contains('is-open')) return;

  root._gen = (root._gen || 0) + 1;
  root._lastFocus = trigger || document.activeElement;
  root.hidden = false;

  if (!overlayStack.includes(root)) overlayStack.push(root);
  document.body.classList.add('no-scroll');

  requestAnimationFrame(() => root.classList.add('is-open'));

  window.setTimeout(() => {
    if (root.hidden) return;
    const target = root.querySelector('[data-autofocus]') || root.querySelector('[role="dialog"]') || root;
    if (target && typeof target.focus === 'function') target.focus({ preventScroll: true });
  }, 60);
}

function closeOverlay(root) {
  if (!root || root.hidden) return;

  root._gen = (root._gen || 0) + 1;
  const gen = root._gen;
  root.classList.remove('is-open');

  const index = overlayStack.indexOf(root);
  if (index >= 0) overlayStack.splice(index, 1);
  if (!overlayStack.length) document.body.classList.remove('no-scroll');

  window.setTimeout(() => {
    if (root._gen !== gen) return;
    root.hidden = true;
    const back = root._lastFocus;
    if (back && typeof back.focus === 'function' && document.contains(back)) {
      back.focus({ preventScroll: true });
    }
  }, 240);
}

function confirmDialog(options) {
  const config = options || {};
  return new Promise((resolve) => {
    if (confirmResolver) {
      const pending = confirmResolver;
      confirmResolver = null;
      pending(false);
    }

    el.confirmTitle.textContent = config.title || '确认操作';
    el.confirmMessage.textContent = config.message || '';
    el.confirmOk.textContent = config.confirmText || '确定';
    el.confirmCancel.textContent = config.cancelText || '取消';
    el.confirmOk.className = config.danger ? 'btn btn-danger' : 'btn btn-primary';

    confirmResolver = resolve;
    openOverlay(el.confirmModal, document.activeElement);
    window.setTimeout(() => el.confirmOk.focus({ preventScroll: true }), 80);
  });
}

function settleConfirm(value) {
  const resolver = confirmResolver;
  confirmResolver = null;
  if (resolver) resolver(Boolean(value));
  closeOverlay(el.confirmModal);
}

function trapFocus(root, event) {
  const selector =
    'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';
  const focusables = Array.from(root.querySelectorAll(selector)).filter(
    (node) => node.getClientRects().length > 0
  );
  if (!focusables.length) return;

  const first = focusables[0];
  const last = focusables[focusables.length - 1];
  const active = document.activeElement;

  if (event.shiftKey) {
    if (active === first || !root.contains(active)) {
      event.preventDefault();
      last.focus();
    }
  } else if (active === last || !root.contains(active)) {
    event.preventDefault();
    first.focus();
  }
}

function onDocumentKeydown(event) {
  if (event.key === 'Escape') {
    if (!el.confirmModal.hidden) {
      event.preventDefault();
      settleConfirm(false);
      return;
    }
    if (!el.settingsModal.hidden) {
      event.preventDefault();
      closeOverlay(el.settingsModal);
      return;
    }
    if (!el.historyDrawer.hidden) {
      event.preventDefault();
      closeOverlay(el.historyDrawer);
      return;
    }
  }

  if (event.key === 'Tab') {
    const top = overlayStack[overlayStack.length - 1];
    if (top) trapFocus(top, event);
  }
}

/* ------------------------------ Toast ------------------------------ */

function toast(message, type) {
  const kind = ['success', 'error', 'info'].includes(type) ? type : 'info';
  const icons = { success: ICONS.checkCircle, error: ICONS.alertCircle, info: ICONS.infoCircle };

  const node = document.createElement('div');
  node.className = `toast toast-${kind}`;
  node.setAttribute('role', kind === 'error' ? 'alert' : 'status');

  const icon = document.createElement('span');
  icon.className = 'toast-icon';
  icon.innerHTML = icons[kind];

  const text = document.createElement('span');
  text.className = 'toast-text';
  text.textContent = String(message);

  const close = document.createElement('button');
  close.type = 'button';
  close.className = 'toast-close';
  close.setAttribute('aria-label', '关闭提示');
  close.innerHTML = ICONS.x;
  close.addEventListener('click', () => removeToast(node));

  node.append(icon, text, close);
  el.toastStack.appendChild(node);

  node._timer = window.setTimeout(() => removeToast(node), 3000);

  const children = Array.from(el.toastStack.children);
  if (children.length > 4) children.slice(0, children.length - 4).forEach(removeToast);
}

function removeToast(node) {
  if (!node || node._removing) return;
  node._removing = true;
  window.clearTimeout(node._timer);
  node.classList.add('is-out');
  window.setTimeout(() => node.remove(), 220);
}

/* ------------------------------ 事件绑定 ------------------------------ */

function bindEvents() {
  // 顶栏
  el.btnHistory.addEventListener('click', openHistoryDrawer);
  el.btnSettings.addEventListener('click', () => openSettings(el.btnSettings));
  el.btnGuideSettings.addEventListener('click', () => openSettings(el.btnGuideSettings));

  // 上传区
  el.dropzone.addEventListener('click', onDropzoneClick);
  el.dropzone.addEventListener('keydown', onDropzoneKeydown);
  el.dropzone.addEventListener('dragenter', onDragEnter);
  el.dropzone.addEventListener('dragover', onDragOver);
  el.dropzone.addEventListener('dragleave', onDragLeave);
  el.dropzone.addEventListener('drop', onDrop);
  el.fileInput.addEventListener('change', onFileInputChange);
  el.btnClearFiles.addEventListener('click', clearFiles);
  el.fileList.addEventListener('click', onFileListClick);

  // 档位选择
  document.querySelectorAll('input[name="profile"]').forEach((input) => {
    input.addEventListener('change', () => {
      if (input.checked) selectProfile(input.value);
    });
  });

  // 生成流程
  el.btnStart.addEventListener('click', startGeneration);
  el.btnCancel.addEventListener('click', cancelRunningJob);
  el.btnRetry.addEventListener('click', startGeneration);
  el.btnBack.addEventListener('click', backToUpload);
  el.btnAgain.addEventListener('click', backToUpload);

  // 设置弹窗
  el.btnCloseSettings.addEventListener('click', () => closeOverlay(el.settingsModal));
  el.btnCancelSettings.addEventListener('click', () => closeOverlay(el.settingsModal));
  el.settingsModal
    .querySelector('[data-close-settings]')
    .addEventListener('click', () => closeOverlay(el.settingsModal));
  el.setProvider.addEventListener('change', onProviderChange);
  el.setTemp.addEventListener('input', onTempInput);
  el.btnTest.addEventListener('click', testConnection);
  el.btnSave.addEventListener('click', saveSettings);
  el.settingsModal.addEventListener('keydown', onSettingsKeydown);

  // 确认弹窗
  el.confirmOk.addEventListener('click', () => settleConfirm(true));
  el.confirmCancel.addEventListener('click', () => settleConfirm(false));
  el.confirmModal
    .querySelector('[data-confirm-cancel]')
    .addEventListener('click', () => settleConfirm(false));

  // 历史记录
  el.btnCloseHistory.addEventListener('click', () => closeOverlay(el.historyDrawer));
  el.historyDrawer
    .querySelector('[data-close-history]')
    .addEventListener('click', () => closeOverlay(el.historyDrawer));
  el.btnRefreshHistory.addEventListener('click', loadHistory);
  el.historyList.addEventListener('click', onHistoryListClick);

  // 全局键盘与拖拽
  document.addEventListener('keydown', onDocumentKeydown);
  window.addEventListener('dragover', (event) => event.preventDefault());
  window.addEventListener('drop', (event) => event.preventDefault());
}

function onDropzoneClick(event) {
  if (state.busy) return;
  if (event.target.closest('input')) return;
  el.fileInput.click();
}

function onDropzoneKeydown(event) {
  if (state.busy) return;
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault();
    el.fileInput.click();
  }
}

function onFileInputChange() {
  if (el.fileInput.files && el.fileInput.files.length) addFiles(el.fileInput.files);
  el.fileInput.value = '';
}

function onDragEnter(event) {
  if (state.busy) return;
  event.preventDefault();
  dragDepth += 1;
  el.dropzone.classList.add('is-drag');
}

function onDragOver(event) {
  event.preventDefault();
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy';
}

function onDragLeave() {
  dragDepth = Math.max(0, dragDepth - 1);
  if (dragDepth === 0) el.dropzone.classList.remove('is-drag');
}

function onDrop(event) {
  event.preventDefault();
  dragDepth = 0;
  el.dropzone.classList.remove('is-drag');
  if (state.busy) return;
  if (event.dataTransfer && event.dataTransfer.files) addFiles(event.dataTransfer.files);
}

function onFileListClick(event) {
  const button = event.target.closest('[data-remove-index]');
  if (!button) return;
  if (state.busy) return;
  const index = Number(button.getAttribute('data-remove-index'));
  removeFile(index);
}

function onSettingsKeydown(event) {
  if (event.key !== 'Enter') return;
  const target = event.target;
  if (target instanceof HTMLInputElement && target.classList.contains('input')) {
    event.preventDefault();
    saveSettings();
  }
}

/* ------------------------------ 启动 ------------------------------ */

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
