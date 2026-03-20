// ===== Easy AIGC — App Entry Point =====
import { API } from './api.js';
import { $, $$, toast, log, initLightbox, openLightbox } from './components.js';
import { initGeneration, loadHistory } from './generation.js';
import { initModels, loadModelList } from './models.js';

// ===== Expose lightbox to window for inline onclick =====
window.__lightbox = openLightbox;

// ===== Tab Switching =====
export function switchTab(tabName) {
    $$('.tab-btn').forEach(b => b.classList.remove('active'));
    $$('.tab-page').forEach(p => p.classList.remove('active'));
    const btn = document.querySelector(`.tab-btn[data-tab="${tabName}"]`);
    if (btn) btn.classList.add('active');
    const page = document.getElementById('tab-' + tabName);
    if (page) page.classList.add('active');
    if (tabName === 'models') loadModelList();
}
window.__switchTab = switchTab;

// ===== Settings Panel =====
function openSettings() {
    $('#settingsBackdrop').classList.add('active');
    $('#settingsPanel').classList.add('active');
    loadApiKeyStatus();
}
function closeSettings() {
    $('#settingsBackdrop').classList.remove('active');
    $('#settingsPanel').classList.remove('active');
}
window.__openSettings = openSettings;
window.__closeSettings = closeSettings;

async function loadApiKeyStatus() {
    try {
        const cfg = await API.getConfig();
        const providers = cfg.providers || {};

        // SiliconFlow
        const sfInfo = providers.siliconflow;
        const sfStatus = $('#sfKeyStatus');
        if (sfInfo && sfInfo.has_api_key) {
            sfStatus.textContent = '✓ 已配置';
            sfStatus.className = 'key-status configured';
            $('#sfApiKey').placeholder = 'sk-****已配置 (留空则保持不变)';
        } else {
            sfStatus.textContent = '✗ 未配置';
            sfStatus.className = 'key-status missing';
        }

        // Evolink
        const evInfo = providers.evolink;
        const evStatus = $('#evKeyStatus');
        if (evInfo && evInfo.has_api_key) {
            evStatus.textContent = '✓ 已配置';
            evStatus.className = 'key-status configured';
            $('#evApiKey').placeholder = 'sk-****已配置 (留空则保持不变)';
        } else {
            evStatus.textContent = '✗ 未配置';
            evStatus.className = 'key-status missing';
        }
    } catch (e) {
        console.error('获取 Key 配置状态失败', e);
    }
}

async function saveApiKeys() {
    const sfKey = $('#sfApiKey').value.trim();
    const evKey = $('#evApiKey').value.trim();
    if (!sfKey && !evKey) { toast('请至少填写一个 API Key', 'error'); return; }

    const btn = $('#btnSaveKeys');
    btn.disabled = true;
    btn.textContent = '保存中...';

    const providers = {};
    if (sfKey) providers.siliconflow = { api_key: sfKey };
    if (evKey) providers.evolink = { api_key: evKey };

    try {
        await API.updateConfig({ providers });
        toast('API Key 已保存并持久化', 'success');
        log('success', 'API Key 更新成功');
        $('#sfApiKey').value = '';
        $('#evApiKey').value = '';
        await loadApiKeyStatus();
    } catch (e) {
        toast('保存失败: ' + e.message, 'error');
    }
    btn.disabled = false;
    btn.textContent = '💾 保存 API Key';
}
window.__saveApiKeys = saveApiKeys;

function toggleKeyVis(inputId) {
    const inp = document.getElementById(inputId);
    inp.type = inp.type === 'password' ? 'text' : 'password';
}
window.__toggleKeyVis = toggleKeyVis;

// ===== Health Check =====
async function checkHealth() {
    try {
        const ok = await API.health();
        if (ok) {
            $('#statusDot').style.background = 'var(--success)';
            $('#statusText').textContent = '已连接';
            return true;
        }
    } catch {}
    $('#statusDot').style.background = 'var(--error)';
    $('#statusText').textContent = '未连接';
    return false;
}

// ===== Boot =====
(async () => {
    initLightbox();
    initGeneration();
    initModels();

    const ok = await checkHealth();
    if (ok) {
        // Load provider models for generation page
        loadHistory();
        log('success', '后端服务已连接');

        // Check if API keys configured, if not hint
        try {
            const cfg = await API.getConfig();
            const p = cfg.providers || {};
            const hasAny = (p.siliconflow && p.siliconflow.has_api_key) || (p.evolink && p.evolink.has_api_key);
            if (!hasAny) {
                toast('💡 首次使用？请点击右上角 ⚙️ 配置 API Key', 'error');
            }
        } catch {}
    } else {
        log('error', '后端服务未连接，请确认已启动');
    }
})();
