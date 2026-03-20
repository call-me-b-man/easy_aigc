// ===== Easy AIGC — 图片生成页逻辑 =====
import { API, resolveImageUrl } from './api.js';
import { $, $$, toast, log, openLightbox } from './components.js';

let selectedFile = null;
let subjectImagePath = null;

// ===== Init =====
export function initGeneration() {
    const uploadArea = $('#uploadArea');
    const fileInput = $('#fileInput');
    const btnExtract = $('#btnExtract');
    const btnPipeline = $('#btnPipeline');
    const providerSel = $('#provider');
    const modelSel = $('#model');
    const advToggle = $('#advToggle');
    const advBody = $('#advBody');
    const viewsGroup = $('#viewsGroup');

    if (!uploadArea) return; // not on this page

    // --- Upload ---
    uploadArea.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', (e) => handleFile(e.target.files[0]));
    uploadArea.addEventListener('dragover', (e) => { e.preventDefault(); uploadArea.classList.add('dragover'); });
    uploadArea.addEventListener('dragleave', () => uploadArea.classList.remove('dragover'));
    uploadArea.addEventListener('drop', (e) => { e.preventDefault(); uploadArea.classList.remove('dragover'); handleFile(e.dataTransfer.files[0]); });

    function handleFile(file) {
        if (!file || !file.type.startsWith('image/')) return;
        selectedFile = file;
        const reader = new FileReader();
        reader.onload = (e) => {
            $('#previewImg').src = e.target.result;
            $('#previewImg').style.display = 'block';
            $('#uploadPlaceholder').style.display = 'none';
            btnExtract.disabled = false;
            btnPipeline.disabled = false;
            log('info', `已选择图片: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`);
        };
        reader.readAsDataURL(file);
    }

    // --- Collapsible ---
    advToggle.addEventListener('click', () => {
        advToggle.classList.toggle('open');
        advBody.classList.toggle('open');
    });

    // --- View Tags ---
    viewsGroup.querySelectorAll('.checkbox-tag').forEach(tag => {
        tag.addEventListener('click', () => tag.classList.toggle('active'));
    });

    // --- Provider / Model ---
    providerSel.addEventListener('change', () => {
        localStorage.setItem('aigc_provider', providerSel.value);
        loadProviderModels();
    });
    modelSel.addEventListener('change', () => {
        localStorage.setItem('aigc_model', modelSel.value);
    });

    // --- Buttons ---
    btnExtract.addEventListener('click', doExtract);
    btnPipeline.addEventListener('click', doPipeline);

    // --- Initial load ---
    loadProviderModels();
}

// ===== Load Provider Models into <select> =====
async function loadProviderModels() {
    const providerSel = $('#provider');
    const modelSel = $('#model');
    try {
        const providers = await API.getProviders();
        const savedProvider = localStorage.getItem('aigc_provider');
        if (savedProvider && !providerSel.value) providerSel.value = savedProvider;

        modelSel.innerHTML = '<option value="">默认</option>';
        const selected = providerSel.value;
        for (const p of providers) {
            if (!selected || p.name === selected) {
                for (const m of p.models) {
                    if (m.capabilities.includes('img2img') || m.capabilities.includes('edit')) {
                        const opt = document.createElement('option');
                        opt.value = m.id;
                        opt.textContent = `${m.name} (${p.name})`;
                        modelSel.appendChild(opt);
                    }
                }
            }
        }
        const savedModel = localStorage.getItem('aigc_model');
        if (savedModel) modelSel.value = savedModel;
    } catch (e) {
        log('error', '获取模型列表失败');
    }
}

// ===== Build FormData =====
function getSelectedViews() {
    return [...$$('#viewsGroup .checkbox-tag.active')].map(t => t.dataset.view);
}

function buildFormData(mode) {
    const fd = new FormData();
    fd.append('image', selectedFile);

    const provider = $('#provider').value;
    const model = $('#model').value;
    const views = getSelectedViews();
    const subjectDesc = $('#subjectDesc').value.trim();
    const subjectType = $('#subjectType').value.trim();
    const extraReq = $('#extraReq').value.trim();
    const customPrompt = $('#customExtractPrompt').value.trim();

    if (provider) fd.append(mode === 'pipeline' ? 'extract_provider' : 'provider', provider);
    if (model) fd.append(mode === 'pipeline' ? 'extract_model' : 'model', model);

    if (mode === 'pipeline') {
        if (provider) fd.append('multiview_provider', provider);
        if (model) fd.append('multiview_model', model);
        if (customPrompt) fd.append('extract_custom_prompt', customPrompt);
    } else if (mode === 'extract') {
        if (customPrompt) fd.append('custom_prompt', customPrompt);
    }

    const vars = {};
    if (subjectDesc) vars.subject_description = subjectDesc;
    if (subjectType) vars.subject_type = subjectType;
    if (extraReq) vars.extra_requirements = extraReq;

    if (Object.keys(vars).length > 0) {
        if (mode === 'pipeline') {
            fd.append('extract_prompt_variables', JSON.stringify(vars));
            fd.append('multiview_prompt_variables', JSON.stringify(vars));
        } else {
            fd.append('prompt_variables', JSON.stringify(vars));
        }
    }

    if (views.length > 0 && (mode === 'pipeline' || mode === 'multiview')) {
        fd.append('views', JSON.stringify(views));
    }
    return fd;
}

// ===== Extract Subject =====
async function doExtract() {
    if (!selectedFile) return;
    const btn = $('#btnExtract');
    btn.disabled = true;
    btn.innerHTML = '<div class="spinner"></div> 提取中...';
    log('info', '开始主体提取...');

    try {
        const fd = buildFormData('extract');
        const data = await API.extractSubject(fd);

        if (data.status === 'completed' && data.subject_image_path) {
            subjectImagePath = data.subject_image_path;
            showSubjectResult(data);
            log('success', `主体提取成功: ${data.subject_image_path}`);
            toast('主体提取成功！', 'success');
            loadHistory();
        } else {
            log('error', `提取失败: ${data.error || JSON.stringify(data)}`);
            toast('主体提取失败: ' + (data.error || '未知错误'), 'error');
        }
    } catch (e) {
        log('error', `请求失败: ${e.message}`);
        toast('请求失败: ' + e.message, 'error');
    }
    btn.disabled = false;
    btn.innerHTML = '🎯 提取主体';
}

// ===== Pipeline =====
async function doPipeline() {
    if (!selectedFile) return;
    const btn = $('#btnPipeline');
    btn.disabled = true;
    btn.innerHTML = '<div class="spinner"></div> 生成中...';
    log('info', '开始完整流水线: 主体提取 + 多视角生成...');

    try {
        const fd = buildFormData('pipeline');
        const data = await API.pipeline(fd);

        if (data.subject_image_path) {
            subjectImagePath = data.subject_image_path;
            showSubjectResult(data);
            log('success', '主体提取完成');
        }
        if (data.views && data.views.length > 0) {
            showMultiviewResult(data.views);
            const ok = data.views.filter(v => v.status === 'completed').length;
            log('success', `多视角生成完成: ${ok}/${data.views.length} 成功`);
            toast(`生成完成！${ok}/${data.views.length} 视角成功`, ok === data.views.length ? 'success' : 'error');
            loadHistory();
        } else if (data.status === 'failed') {
            log('error', '流水线失败');
            toast('生成失败', 'error');
        }
    } catch (e) {
        log('error', `请求失败: ${e.message}`);
        toast('请求失败: ' + e.message, 'error');
    }
    btn.disabled = false;
    btn.innerHTML = '🚀 一键生成';
}

// ===== Display Results =====
function showSubjectResult(data) {
    const container = $('#subjectResult');
    const imgUrl = resolveImageUrl(data.subject_image_path);
    container.innerHTML = `
        <div class="results-grid">
            <div class="result-card">
                ${imgUrl
                    ? `<img src="${imgUrl}" alt="主体提取结果" style="object-fit:contain;" onclick="window.__lightbox(['${imgUrl}'],0)">`
                    : `<div style="width:100%;aspect-ratio:1;background:var(--bg-secondary);display:flex;align-items:center;justify-content:center;font-size:48px;">🎯</div>`
                }
                <div class="info">
                    <h4>提取主体 <span class="badge badge-success">完成</span></h4>
                    <p title="${data.prompt_used || ''}">${data.provider_used} / ${data.model_used}</p>
                </div>
            </div>
        </div>`;
}

const viewLabels = { front:'正面', left_side:'左侧', right_side:'右侧', back:'背面', top:'俯视', three_quarter:'3/4视角' };

function showMultiviewResult(views) {
    const container = $('#multiviewResult');
    const allUrls = views.filter(v => v.image_path).map(v => resolveImageUrl(v.image_path));

    let html = '<div class="results-grid">';
    views.forEach((v, idx) => {
        const label = viewLabels[v.view_name] || v.view_name;
        const ok = v.status === 'completed';
        const badgeClass = ok ? 'badge-success' : 'badge-error';
        const badgeText = ok ? '完成' : '失败';
        const imgUrl = resolveImageUrl(v.image_path);
        html += `
            <div class="result-card">
                ${imgUrl
                    ? `<img src="${imgUrl}" alt="${label}" style="object-fit:contain;" onclick="window.__lightbox(${JSON.stringify(allUrls)},${idx})">`
                    : `<div style="width:100%;aspect-ratio:1;background:var(--bg-secondary);display:flex;align-items:center;justify-content:center;font-size:36px;color:var(--text-muted);">${ok ? '🖼️' : '❌'}</div>`
                }
                <div class="info">
                    <h4>${label} <span class="badge ${badgeClass}">${badgeText}</span></h4>
                    <p title="${v.prompt_used || ''}">${v.prompt_used ? v.prompt_used.substring(0, 40) + '...' : ''}</p>
                </div>
            </div>`;
    });
    html += '</div>';
    container.innerHTML = html;
}

// ===== History =====
export async function loadHistory() {
    try {
        const records = await API.history(20);
        const list = $('#historyList');
        const countEl = $('#historyCount');

        if (!records || records.length === 0) {
            list.innerHTML = '<div class="empty-state" style="padding:24px 10px;"><p style="font-size:13px;">暂无生成记录</p></div>';
            countEl.textContent = '';
            return;
        }

        countEl.textContent = records.length + ' 条';
        let html = '';
        for (const r of records) {
            const firstImg = r.images && r.images.length > 0
                ? '/output/' + r.dir + '/' + r.images[0] : '';
            const typeLabel = r.type === 'subject_extraction' ? '提取'
                : r.type === 'multiview' ? '多视角' : r.type;
            const imgCount = r.images ? r.images.length : 0;
            const imagesJson = JSON.stringify(r.images || []).replace(/"/g, '&quot;');
            html += `<div class="history-item" data-dir="${r.dir}" data-images="${imagesJson}" onclick="window.__showHistory(this)">`;
            if (firstImg) {
                html += `<img class="thumb" src="${firstImg}" alt="">`;
            } else {
                html += '<div class="thumb" style="display:flex;align-items:center;justify-content:center;font-size:18px;">📄</div>';
            }
            html += `<div class="meta">`;
            html += `<h5>${typeLabel} · ${r.task_id}</h5>`;
            html += `<p>${r.date} · ${r.provider || ''} · ${imgCount} 张图片</p>`;
            html += '</div></div>';
        }
        list.innerHTML = html;
    } catch (e) {
        console.error('加载历史失败', e);
    }
}

// Exposed to window for inline onclick
window.__showHistory = function(el) {
    $$('.history-item').forEach(i => i.classList.remove('active'));
    el.classList.add('active');

    const dir = el.dataset.dir;
    const images = JSON.parse(el.dataset.images || '[]');
    const detail = $('#historyDetail');

    if (images.length === 0) { detail.style.display = 'none'; return; }

    const urls = images.map(img => '/output/' + dir + '/' + img);
    let html = '<div class="history-images">';
    images.forEach((img, i) => {
        const url = '/output/' + dir + '/' + img;
        html += `<img src="${url}" alt="${img}" title="${img}" onclick="window.__lightbox(${JSON.stringify(urls)},${i})">`;
    });
    html += '</div>';
    detail.innerHTML = html;
    detail.style.display = 'block';
};
