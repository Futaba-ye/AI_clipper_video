/**
 * 全自动切片机 — 前端逻辑
 *
 * 功能：
 *   - 三 Tab 切换
 *   - 视频上传（拖拽 + 点击）
 *   - 任务创建（FormData → POST /api/tasks）
 *   - SSE 实时进度流
 *   - 任务列表 & 切片预览
 *   - 全局设置模态框
 */

// ============================================================
// 状态
// ============================================================
const STATE = {
    currentTab: 'tab-new',
    selectedFile: null,
    currentTaskId: null,
    isRunning: false,
    sseConnection: null,
    tasks: [],
    currentClipsTaskId: null,
};

// ============================================================
// DOM 缓存
// ============================================================
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// ============================================================
// 初始化
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initUpload();
    initStartButton();
    initProgressTab();
    initLibraryTab();
    initConfigModal();
    initPreviewModal();
    loadSavedConfig();
});

// ============================================================
// Tab 切换
// ============================================================
function initTabs() {
    $$('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            const target = tab.dataset.tab;
            switchTab(target);
        });
    });
}

function switchTab(target) {
    STATE.currentTab = target;
    $$('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === target));
    $$('.tab-content').forEach(c => c.classList.toggle('active', c.id === target));

    if (target === 'tab-library') {
        loadTaskList();
    }
    if (target === 'tab-progress' && STATE.currentTaskId) {
        // 回到进度页时刷新状态
        refreshProgressTab();
    }
}

// ============================================================
// 视频上传
// ============================================================
function initUpload() {
    const zone = $('#upload-zone');
    const input = $('#file-input');
    const btn = $('#btn-select-file');
    const clearBtn = $('#btn-clear-file');

    // 点击上传区域
    zone.addEventListener('click', () => input.click());
    btn.addEventListener('click', (e) => {
        e.stopPropagation();
        input.click();
    });

    // 文件选择
    input.addEventListener('change', () => {
        if (input.files.length > 0) {
            setFile(input.files[0]);
        }
    });

    // 拖拽上传
    zone.addEventListener('dragover', (e) => {
        e.preventDefault();
        zone.classList.add('drag-over');
    });
    zone.addEventListener('dragleave', () => {
        zone.classList.remove('drag-over');
    });
    zone.addEventListener('drop', (e) => {
        e.preventDefault();
        zone.classList.remove('drag-over');
        const file = e.dataTransfer.files[0];
        if (file && file.type.startsWith('video/')) {
            setFile(file);
        } else {
            toast('请选择视频文件', 'error');
        }
    });

    // 清除选择
    clearBtn.addEventListener('click', () => {
        STATE.selectedFile = null;
        input.value = '';
        $('#file-info').classList.add('hidden');
        $('#upload-zone').classList.remove('hidden');
        updateStartButton();
    });
}

function setFile(file) {
    STATE.selectedFile = file;
    $('#upload-zone').classList.add('hidden');
    $('#file-info').classList.remove('hidden');
    $('#file-name').textContent = file.name;

    const sizeMB = file.size / (1024 * 1024);
    $('#file-size').textContent = sizeMB > 1024
        ? `${(sizeMB / 1024).toFixed(1)} GB`
        : `${sizeMB.toFixed(0)} MB`;

    updateStartButton();
}

function updateStartButton() {
    const btn = $('#btn-start');
    const hint = $('#hint-start');
    if (STATE.selectedFile && !STATE.isRunning) {
        btn.disabled = false;
        hint.textContent = '点击开始自动切片流水线';
    } else if (STATE.isRunning) {
        btn.disabled = true;
        hint.textContent = '当前有任务正在运行，请等待完成';
    } else {
        btn.disabled = true;
        hint.textContent = '请先选择视频文件';
    }
}

// ============================================================
// 开始任务
// ============================================================
function initStartButton() {
    $('#btn-start').addEventListener('click', startTask);
}

async function startTask() {
    if (!STATE.selectedFile || STATE.isRunning) return;

    // 检查 API Key
    const audioKey = $('#cfg-audio-key').value.trim();
    const videoKey = $('#cfg-video-key').value.trim();
    if (!audioKey || !videoKey) {
        toast('请填写音频和视频通道的 API Key', 'warning');
        return;
    }

    STATE.isRunning = true;
    updateStartButton();

    const btn = $('#btn-start');
    btn.disabled = true;
    btn.innerHTML = '<span class="step-indicator" style="animation:spin 1s linear infinite;display:inline-block;">⏳</span> 正在上传…';

    // 构造 FormData
    const formData = new FormData();
    formData.append('video', STATE.selectedFile);
    formData.append('audio_api_key', audioKey);
    formData.append('audio_base_url', $('#cfg-audio-url').value.trim());
    formData.append('audio_model', $('#cfg-audio-model').value);
    formData.append('video_api_key', videoKey);
    formData.append('video_base_url', $('#cfg-video-url').value.trim());
    formData.append('video_model', $('#cfg-video-model').value);

    const summaryKey = $('#cfg-summary-key').value.trim();
    if (summaryKey) {
        formData.append('summary_api_key', summaryKey);
        formData.append('summary_base_url', $('#cfg-summary-url').value.trim());
        formData.append('summary_model', $('#cfg-summary-model').value);
    }

    try {
        const resp = await fetch('/api/tasks', { method: 'POST', body: formData });
        const result = await resp.json();

        if (!resp.ok || !result.success) {
            throw new Error(result.message || result.detail || '创建任务失败');
        }

        STATE.currentTaskId = result.data.task_id;
        toast('任务已创建，流水线开始运行', 'success');

        // 自动切换到进度页
        switchTab('tab-progress');
        startProgressStream(STATE.currentTaskId);

        // 显示运行中标识
        $('#badge-running').style.display = 'inline';

    } catch (err) {
        toast(`启动失败: ${err.message}`, 'error');
        STATE.isRunning = false;
        updateStartButton();
    }

    btn.innerHTML = '🚀 开始自动切片';
}

// ============================================================
// 进度页 & SSE
// ============================================================
function initProgressTab() {
    // 初始化步骤列表的静态结构
    const stepList = $('#step-list');
    const steps = [
        { id: 'extract_audio', name: '提取音频' },
        { id: 'extract_video', name: '提取视频' },
        { id: 'asr', name: '语音识别 (ASR)' },
        { id: 'audio_summary', name: '音频内容总结' },
        { id: 'scene_detect', name: '场景检测' },
        { id: 'video_summary', name: '画面内容总结' },
        { id: 'fusion', name: '双通道融合' },
        { id: 'clip', name: '裁剪视频片段' },
    ];

    stepList.innerHTML = steps.map(s => `
        <div class="step-item pending" data-step="${s.id}">
            <div class="step-indicator">○</div>
            <span class="step-name">${s.name}</span>
            <span class="step-msg"></span>
        </div>
    `).join('');
}

function refreshProgressTab() {
    if (!STATE.currentTaskId) return;
    // 如果 SSE 未连接，重新连接
    if (!STATE.sseConnection || STATE.sseConnection.readyState === EventSource.CLOSED) {
        startProgressStream(STATE.currentTaskId);
    }
}

function startProgressStream(taskId) {
    // 关闭旧连接
    if (STATE.sseConnection) {
        STATE.sseConnection.close();
    }

    $('#progress-empty').classList.add('hidden');
    $('#progress-panel').classList.remove('hidden');
    $('#progress-title').textContent = `任务 ${taskId}`;
    $('#progress-pct').textContent = '0%';
    $('#progress-bar').style.width = '0%';
    $('#log-stream').innerHTML = '';

    // 重置步骤状态
    $$('.step-item').forEach(el => {
        el.className = 'step-item pending';
        el.querySelector('.step-indicator').textContent = '○';
        el.querySelector('.step-msg').textContent = '';
    });

    addLog('开始连接进度流…', 'info');

    const startTime = Date.now();
    const elapsedEl = $('#progress-elapsed');

    // 定时更新耗时
    const elapsedTimer = setInterval(() => {
        const sec = Math.floor((Date.now() - startTime) / 1000);
        const m = Math.floor(sec / 60);
        const s = sec % 60;
        elapsedEl.textContent = `⏱ ${m}:${String(s).padStart(2, '0')}`;
    }, 1000);

    // 建立 SSE 连接
    const es = new EventSource(`/api/tasks/${taskId}/stream`);
    STATE.sseConnection = es;

    // 跟踪"真实进度事件"的时间戳（排除初始回放和 ping）
    // 用于检测管道是否已死（服务器重启后重连时）
    let lastRealProgressTime = 0;
    let stuckWarningShown = false;
    const STUCK_TIMEOUT = 30; // 30 秒无新进度 → 提示可能卡住

    es.addEventListener('progress', (e) => {
        try {
            const data = JSON.parse(e.data);
            // 初始回放事件的 type 是 "progress"（非 step_start/step_done/complete/error）
            // 真实流水线事件有具体的 type
            const isReplay = (data.type === 'progress' && !data.step);
            handleProgressEvent(data);
            if (!isReplay) {
                lastRealProgressTime = Date.now();
            }
        } catch (err) {
            console.error('解析进度事件失败:', err);
        }
    });

    es.addEventListener('ping', () => {
        // 检测是否卡住：30 秒内没收到任何真实进度
        if (lastRealProgressTime > 0 && !stuckWarningShown) {
            const idleSec = (Date.now() - lastRealProgressTime) / 1000;
            if (idleSec >= STUCK_TIMEOUT) {
                stuckWarningShown = true;
                addLog('⚠ 30 秒内无进度更新，任务可能因服务器重启而中断', 'warn');
                addLog('可在"片段库"中将此任务标记为失败后重试', 'warn');
            }
        }
    });

    es.addEventListener('done', () => {
        es.close();
        clearInterval(elapsedTimer);
        STATE.sseConnection = null;
        addLog('进度流已关闭', 'info');
    });

    // 跟踪重连次数，超过阈值则放弃
    let reconnectAttempts = 0;
    const MAX_RECONNECT = 5;

    es.onerror = () => {
        reconnectAttempts++;
        clearInterval(elapsedTimer);
        if (reconnectAttempts >= MAX_RECONNECT) {
            es.close();
            STATE.sseConnection = null;
            addLog('进度连接失败，已停止重试。请检查后端是否仍在运行', 'error');
            STATE.isRunning = false;
            updateStartButton();
            $('#badge-running').style.display = 'none';
        } else {
            addLog(`进度连接中断，重连中 (${reconnectAttempts}/${MAX_RECONNECT})…`, 'warn');
        }
    };

    // 成功连接后重置计数器
    es.addEventListener('open', () => {
        reconnectAttempts = 0;
    });
}

function handleProgressEvent(data) {
    const { type, step, step_label, status, message, progress, step_statuses } = data;

    // 更新进度条
    if (progress !== undefined) {
        const pct = Math.round(progress);
        $('#progress-pct').textContent = `${pct}%`;
        $('#progress-bar').style.width = `${pct}%`;
    }

    // 更新当前步骤
    if (step) {
        $('#progress-step').textContent = `当前: ${step_label || step}`;
    }

    // 更新步骤状态列表
    if (step_statuses) {
        for (const [stepId, stepStatus] of Object.entries(step_statuses)) {
            const el = $(`.step-item[data-step="${stepId}"]`);
            if (!el) continue;
            el.className = `step-item ${stepStatus}`;
            const indicator = el.querySelector('.step-indicator');
            if (stepStatus === 'completed') indicator.textContent = '✓';
            else if (stepStatus === 'running') indicator.textContent = '◉';
            else if (stepStatus === 'failed') indicator.textContent = '✕';
            else indicator.textContent = '○';
        }
    }

    // 更新单步消息
    if (step && status) {
        const el = $(`.step-item[data-step="${step}"]`);
        if (el) {
            el.className = `step-item ${status}`;
            const indicator = el.querySelector('.step-indicator');
            if (status === 'completed') indicator.textContent = '✓';
            else if (status === 'running') indicator.textContent = '◉';
            else if (status === 'failed') indicator.textContent = '✕';
            if (message) el.querySelector('.step-msg').textContent = message;
        }
    }

    // 添加日志
    if (message) {
        let logClass = 'info';
        if (status === 'completed') logClass = 'success';
        else if (status === 'failed') logClass = 'error';
        addLog(message, logClass);
    }

    // 完成或失败
    if (type === 'complete') {
        addLog('🎉 流水线全部完成！', 'success');
        STATE.isRunning = false;
        updateStartButton();
        $('#badge-running').style.display = 'none';
        toast('切片任务完成！', 'success');
    }
    if (type === 'error') {
        addLog(`❌ ${message}`, 'error');
        STATE.isRunning = false;
        updateStartButton();
        $('#badge-running').style.display = 'none';
        toast(`任务失败: ${message}`, 'error');
    }
}

function addLog(msg, cls = 'info') {
    const stream = $('#log-stream');
    const entry = document.createElement('div');
    entry.className = `log-entry log-${cls}`;
    entry.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
    stream.appendChild(entry);
    stream.scrollTop = stream.scrollHeight;
}

// ============================================================
// 片段库（任务列表）
// ============================================================
function initLibraryTab() {
    $('#btn-back-tasks').addEventListener('click', () => {
        $('#clips-card').classList.add('hidden');
        $('#task-list').parentElement.classList.remove('hidden');
        STATE.currentClipsTaskId = null;
    });
}

async function loadTaskList() {
    try {
        const resp = await fetch('/api/tasks?limit=50');
        const result = await resp.json();
        if (!result.success) throw new Error('加载失败');

        STATE.tasks = result.data.tasks || [];
        renderTaskList();

    } catch (err) {
        console.error('加载任务列表失败:', err);
    }
}

function renderTaskList() {
    const container = $('#task-list');
    const empty = $('#library-empty');
    const content = $('#library-content');

    if (STATE.tasks.length === 0) {
        empty.classList.remove('hidden');
        content.classList.add('hidden');
        return;
    }

    empty.classList.add('hidden');
    content.classList.remove('hidden');

    const statusLabels = {
        pending: '等待中',
        running: '运行中',
        completed: '已完成',
        failed: '失败',
    };

    container.innerHTML = STATE.tasks.map(t => `
        <div class="task-item" data-task-id="${t.id}">
            <div class="task-status ${t.status}">${statusLabels[t.status] || t.status}</div>
            <div class="task-info">
                <div class="task-name" title="${escHtml(t.video_filename)}">${escHtml(t.video_filename)}</div>
                <div class="task-date">${t.created_at}</div>
            </div>
            ${t.clip_count > 0 ? `<div class="task-count">✂ ${t.clip_count} 个片段</div>` : ''}
            ${t.status === 'running' ? `
                <button class="btn btn-sm btn-outline btn-force-fail" data-task-id="${t.id}" style="flex-shrink:0;color:var(--error);border-color:var(--error);" title="服务器重启后任务可能僵尸，强制标记为失败后可重试">⚠ 强制失败</button>
            ` : ''}
            ${t.status === 'failed' ? `
                <div class="task-error" style="color:var(--error);font-size:12px;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin:0 8px;" title="${escHtml(t.error_message || '')}">${escHtml(t.error_message || '未知错误')}</div>
                <button class="btn btn-sm btn-primary btn-retry" data-task-id="${t.id}" style="flex-shrink:0;">🔄 重试</button>
            ` : ''}
        </div>
    `).join('');

    // 点击任务查看切片
    container.querySelectorAll('.task-item').forEach(el => {
        el.addEventListener('click', () => {
            const taskId = el.dataset.taskId;
            const task = STATE.tasks.find(t => t.id === taskId);
            if (task && task.clip_count > 0) {
                showClips(task);
            } else if (task && task.status === 'running') {
                // 跳转到进度页
                STATE.currentTaskId = taskId;
                switchTab('tab-progress');
                startProgressStream(taskId);
            } else if (task && task.status === 'pending') {
                toast('该任务还在排队中', 'warning');
            } else {
                toast('该任务暂无切片', 'warning');
            }
        });
    });

    // 强制失败按钮：标记僵尸任务为 failed
    container.querySelectorAll('.btn-force-fail').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const btnEl = btn;
            btnEl.disabled = true;
            btnEl.textContent = '⏳…';
            try {
                await forceFailTask(btn.dataset.taskId);
            } finally {
                btnEl.disabled = false;
                btnEl.textContent = '⚠ 强制失败';
            }
        });
    });

    // 重试按钮：失败任务从断点重新开始
    container.querySelectorAll('.btn-retry').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const btnEl = btn;
            btnEl.disabled = true;
            btnEl.textContent = '⏳ 请求中…';
            try {
                await retryTask(btn.dataset.taskId);
            } finally {
                btnEl.disabled = false;
                btnEl.textContent = '🔄 重试';
            }
        });
    });
}

function showClips(task) {
    STATE.currentClipsTaskId = task.id;
    $('#task-list').parentElement.classList.add('hidden');
    $('#clips-card').classList.remove('hidden');

    const grid = $('#clips-grid');
    grid.innerHTML = task.clips.map(c => `
        <div class="clip-card">
            <div class="clip-thumb" data-clip-url="/api/clips/${task.id}/${encodeURIComponent(c.video_filename)}">
                <div class="play-icon">▶</div>
            </div>
            <div class="clip-body">
                <h3 title="${escHtml(c.title)}">${escHtml(c.title)}</h3>
                <div class="clip-time">🕐 ${c.start_time} → ${c.end_time}</div>
                <div class="clip-summary">${escHtml(c.summary)}</div>
            </div>
            <div class="clip-actions">
                <button class="btn btn-sm btn-primary btn-play" data-clip-url="/api/clips/${task.id}/${encodeURIComponent(c.video_filename)}" data-title="${escHtml(c.title)}" data-summary="${escHtml(c.summary)}">▶ 播放</button>
            </div>
        </div>
    `).join('');

    // 绑定播放按钮
    grid.querySelectorAll('.btn-play').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            openPreview(btn.dataset.clipUrl, btn.dataset.title, btn.dataset.summary);
        });
    });

    // 点击缩略图也可播放
    grid.querySelectorAll('.clip-thumb').forEach(thumb => {
        thumb.addEventListener('click', () => {
            const btn = thumb.parentElement.querySelector('.btn-play');
            openPreview(btn.dataset.clipUrl, btn.dataset.title, btn.dataset.summary);
        });
    });
}

// ============================================================
// 视频预览模态框
// ============================================================
function initPreviewModal() {
    $('#btn-close-preview').addEventListener('click', closePreview);
    $('#modal-preview').addEventListener('click', (e) => {
        if (e.target === $('#modal-preview')) closePreview();
    });
}

function openPreview(url, title, summary) {
    $('#preview-title').textContent = title;
    $('#preview-summary').textContent = summary;
    const video = $('#preview-video');
    video.src = url;
    video.load();
    $('#modal-preview').classList.remove('hidden');
    // 自动播放
    setTimeout(() => video.play().catch(() => {}), 300);
}

function closePreview() {
    const video = $('#preview-video');
    video.pause();
    video.src = '';
    $('#modal-preview').classList.add('hidden');
}

// ============================================================
// 设置模态框
// ============================================================
function initConfigModal() {
    // 打开
    $('#btn-config').addEventListener('click', async () => {
        // 加载已保存的配置
        try {
            const resp = await fetch('/api/config');
            const result = await resp.json();
            if (result.success && result.data.config) {
                const cfg = result.data.config;
                $('#saved-audio-key').value = cfg.audio_api_key || '';
                $('#saved-audio-url').value = cfg.audio_base_url || '';
                $('#saved-audio-model').value = cfg.audio_model || '';
                $('#saved-video-key').value = cfg.video_api_key || '';
                $('#saved-video-url').value = cfg.video_base_url || '';
                $('#saved-video-model').value = cfg.video_model || '';
            }
        } catch (err) {
            console.error('加载配置失败:', err);
        }
        $('#modal-config').classList.remove('hidden');
    });

    // 关闭
    const closeModal = () => $('#modal-config').classList.add('hidden');
    $('#btn-close-config').addEventListener('click', closeModal);
    $('#btn-cancel-config').addEventListener('click', closeModal);
    $('#modal-config').addEventListener('click', (e) => {
        if (e.target === $('#modal-config')) closeModal();
    });

    // 保存
    $('#btn-save-config').addEventListener('click', async () => {
        const config = {
            audio_api_key: $('#saved-audio-key').value.trim(),
            audio_base_url: $('#saved-audio-url').value.trim(),
            audio_model: $('#saved-audio-model').value.trim(),
            video_api_key: $('#saved-video-key').value.trim(),
            video_base_url: $('#saved-video-url').value.trim(),
            video_model: $('#saved-video-model').value.trim(),
            summary_api_key: '',
            summary_base_url: '',
            summary_model: '',
        };

        try {
            const resp = await fetch('/api/config', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config),
            });
            const result = await resp.json();
            if (result.success) {
                toast('配置已保存', 'success');
                closeModal();
                // 同步到新建任务页
                loadSavedConfig();
            } else {
                throw new Error(result.message || '保存失败');
            }
        } catch (err) {
            toast(`保存配置失败: ${err.message}`, 'error');
        }
    });
}

async function loadSavedConfig() {
    try {
        const resp = await fetch('/api/config');
        const result = await resp.json();
        if (result.success && result.data.config) {
            const cfg = result.data.config;
            // 只在用户未手动输入时填充
            if (!$('#cfg-audio-key').value) $('#cfg-audio-key').value = cfg.audio_api_key || '';
            if (!$('#cfg-audio-url').value || $('#cfg-audio-url').value === 'https://api.deepseek.com') {
                $('#cfg-audio-url').value = cfg.audio_base_url || 'https://api.deepseek.com';
            }
            if (!$('#cfg-video-key').value) $('#cfg-video-key').value = cfg.video_api_key || '';
            if (!$('#cfg-video-url').value || $('#cfg-video-url').value === 'https://dashscope.aliyuncs.com/compatible-mode/v1') {
                $('#cfg-video-url').value = cfg.video_base_url || 'https://dashscope.aliyuncs.com/compatible-mode/v1';
            }
        }
    } catch (err) {
        console.error('加载配置失败:', err);
    }
}

// ============================================================
// Toast 通知
// ============================================================
async function forceFailTask(taskId) {
    try {
        const resp = await fetch(`/api/tasks/${taskId}/mark-failed`, { method: 'POST' });
        const result = await resp.json();

        if (!resp.ok || !result.success) {
            throw new Error(result.message || result.detail || '操作失败');
        }

        toast('任务已标记为失败，现在可以重试', 'success');
        // 刷新任务列表
        loadTaskList();

    } catch (err) {
        toast(`操作失败: ${err.message}`, 'error');
    }
}

async function retryTask(taskId) {
    try {
        const resp = await fetch(`/api/tasks/${taskId}/retry`, { method: 'POST' });
        const result = await resp.json();

        if (!resp.ok || !result.success) {
            throw new Error(result.message || result.detail || '重试失败');
        }

        STATE.currentTaskId = taskId;
        STATE.isRunning = true;
        updateStartButton();

        // 切换到进度 Tab 并连接 SSE
        switchTab('tab-progress');
        startProgressStream(taskId);
        $('#badge-running').style.display = 'inline';

        toast(`重试已启动: ${result.message}`, 'success');

    } catch (err) {
        toast(`重试失败: ${err.message}`, 'error');
    }
}

function toast(msg, type = 'info') {
    const container = $('#toast-container');
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.textContent = msg;
    container.appendChild(el);

    setTimeout(() => {
        el.style.opacity = '0';
        el.style.transform = 'translateX(100%)';
        el.style.transition = '0.3s ease';
        setTimeout(() => el.remove(), 300);
    }, 4000);
}

// ============================================================
// 工具函数
// ============================================================
function escHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// ============================================================
// 键盘快捷键
// ============================================================
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closePreview();
        $('#modal-config').classList.add('hidden');
    }
    // Ctrl+1/2/3 切换 Tab
    if (e.ctrlKey && e.key === '1') { e.preventDefault(); switchTab('tab-new'); }
    if (e.ctrlKey && e.key === '2') { e.preventDefault(); switchTab('tab-progress'); }
    if (e.ctrlKey && e.key === '3') { e.preventDefault(); switchTab('tab-library'); }
});
