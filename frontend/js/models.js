// ===== Easy AIGC — 模特管理页逻辑 =====
import { API, resolveImageUrl } from './api.js';
import { $, $$, toast, openLightbox } from './components.js';

let currentModelId = null;
let currentModelName = '';
let createMode = 'text';
let cmSelectedFile = null;

const viewLabels = {
    front:'正面', left_side:'左侧', right_side:'右侧', back:'背面',
    top:'俯视', three_quarter:'3/4角度', walking_front:'行走',
    sitting:'坐姿', hands_on_hips:'叉腰'
};

// ===== Model Log =====
function mlog(type, msg) {
    const logArea = $('#modelLogArea');
    if (!logArea) return;
    const cls = type === 'error' ? 'log-error' : type === 'success' ? 'log-success' : 'log-info';
    const time = new Date().toLocaleTimeString('zh-CN', { hour12: false });
    const line = document.createElement('div');
    line.className = 'log-line';
    line.innerHTML = `<span class="log-time">${time}</span><span class="${cls}">${msg}</span>`;
    logArea.appendChild(line);
    logArea.scrollTop = logArea.scrollHeight;
}

// ===== Init =====
export function initModels() {
    // Upload area in create form
    const cmUploadArea = $('#cmUploadArea');
    const cmFileInput = $('#cmFileInput');
    if (cmUploadArea && cmFileInput) {
        cmUploadArea.addEventListener('click', () => cmFileInput.click());
        cmUploadArea.addEventListener('dragover', (e) => { e.preventDefault(); cmUploadArea.classList.add('dragover'); });
        cmUploadArea.addEventListener('dragleave', () => cmUploadArea.classList.remove('dragover'));
        cmUploadArea.addEventListener('drop', (e) => { e.preventDefault(); cmUploadArea.classList.remove('dragover'); handleCmFile(e.dataTransfer.files[0]); });
        cmFileInput.addEventListener('change', (e) => handleCmFile(e.target.files[0]));
    }
}

function handleCmFile(f) {
    if (!f || !f.type.startsWith('image/')) return;
    cmSelectedFile = f;
    const reader = new FileReader();
    reader.onload = (ev) => {
        $('#cmPreviewImg').src = ev.target.result;
        $('#cmPreviewImg').style.display = 'block';
        $('#cmUploadPlaceholder').style.display = 'none';
    };
    reader.readAsDataURL(f);
    mlog('info', `已选择图片: ${f.name} (${(f.size / 1024).toFixed(1)} KB)`);
}

// ===== Mode Switching =====
function switchModelMode(mode, btn) {
    $$('#modelModeTabs .mode-tab').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    $('#modelModeCreate').style.display = mode === 'create' ? 'block' : 'none';
    $('#modelModeEnrich').style.display = mode === 'enrich' ? 'block' : 'none';
}

function switchCreateMode(mode, btn) {
    createMode = mode;
    const parent = btn.closest('.mode-tabs');
    parent.querySelectorAll('.mode-tab').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    $('#createModeText').style.display = mode === 'text' ? 'block' : 'none';
    $('#createModeImage').style.display = mode === 'image' ? 'block' : 'none';
}

// ===== Load Model List =====
export async function loadModelList() {
    try {
        const models = await API.listModels();
        const grid = $('#modelGrid');
        const countEl = $('#modelCount');

        countEl.textContent = models.length > 0 ? `${models.length} 个` : '';

        if (models.length === 0) {
            grid.innerHTML = `<div class="empty-state"><div class="icon-huge">👤</div><p>暂无模特，在左侧创建你的第一个模特</p></div>`;
            return;
        }

        let html = '';
        for (const m of models) {
            const thumbUrl = m.thumbnail ? resolveImageUrl(m.thumbnail) : '';
            const tagsHtml = (m.tags || []).slice(0, 3).map(t => `<span class="tag">${t}</span>`).join('');
            html += `
                <div class="model-card" onclick="window.__viewModel('${m.model_id}')">
                    <div class="thumb-area">
                        ${thumbUrl
                            ? `<img src="${thumbUrl}" alt="${m.name}">`
                            : '<div class="placeholder">👤</div>'
                        }
                        <span class="ref-count">📷 ${m.reference_count}</span>
                        <button class="delete-btn" onclick="event.stopPropagation();window.__deleteModel('${m.model_id}','${m.name}')">🗑</button>
                    </div>
                    <div class="card-body">
                        <h3>${m.name || '未命名'}</h3>
                        <div class="meta-line">
                            <span>${m.gender === 'male' ? '♂' : '♀'} ${m.style || ''}</span>
                            <span>·</span>
                            <span>${m.created_at ? m.created_at.substring(0, 10) : ''}</span>
                        </div>
                        ${tagsHtml ? `<div class="tag-row">${tagsHtml}</div>` : ''}
                    </div>
                </div>`;
        }
        grid.innerHTML = html;
        mlog('success', `已加载 ${models.length} 个模特`);
    } catch (e) {
        mlog('error', '加载模特列表失败: ' + e.message);
    }
}

// ===== View Model Detail =====
async function viewModelDetail(modelId) {
    currentModelId = modelId;
    mlog('info', `加载模特详情: ${modelId}`);

    try {
        const data = await API.getModel(modelId);
        currentModelName = data.name;

        // Show detail card, keep list card visible
        $('#modelDetailCard').style.display = 'block';

        $('#detailName').textContent = data.name;
        $('#detailMeta').textContent = `${data.gender === 'male' ? '♂ 男' : '♀ 女'} · ${data.style || ''} · ${data.model_id}`;
        $('#detailTags').innerHTML = (data.tags || []).map(t => `<span class="tag">${t}</span>`).join('');

        // Original image
        const origEl = $('#detailOriginal');
        if (data.original_image_path) {
            const origUrl = resolveImageUrl(data.original_image_path);
            origEl.innerHTML = `<img style="width:100%;border-radius:var(--radius-sm);cursor:pointer;" src="${origUrl}" onclick="window.__lightbox(['${origUrl}'],0)">`;
        } else {
            origEl.innerHTML = '<div style="width:100%;aspect-ratio:1;background:var(--bg-input);border-radius:var(--radius-sm);display:flex;align-items:center;justify-content:center;font-size:36px;opacity:0.3;">👤</div>';
        }

        // Side info
        const sideInfo = $('#detailSideInfo');
        sideInfo.innerHTML = `
            <div><span style="color:var(--text-secondary);">性别</span> ${data.gender === 'male' ? '♂ 男' : '♀ 女'}</div>
            <div><span style="color:var(--text-secondary);">风格</span> ${data.style || '—'}</div>
            <div><span style="color:var(--text-secondary);">描述</span> ${data.description || '—'}</div>
            <div><span style="color:var(--text-secondary);">创建</span> ${data.created_at ? data.created_at.substring(0, 10) : '—'}</div>
        `;

        // References
        const refs = data.references || [];
        $('#detailRefCount').textContent = `(${refs.length} 张)`;
        const refGrid = $('#detailRefGrid');

        if (refs.length === 0) {
            refGrid.innerHTML = '<div class="empty-state" style="padding:24px;grid-column:1/-1;"><p style="font-size:13px;">暂无参考图，在左侧切换到"追加参考"模式</p></div>';
        } else {
            const allUrls = refs.filter(r => r.image_path).map(r => resolveImageUrl(r.image_path));
            let rhtml = '';
            refs.forEach((ref, idx) => {
                const refUrl = resolveImageUrl(ref.image_path);
                const label = viewLabels[ref.name] || ref.name;
                const typeClass = ref.type === 'pose' ? 'ref-type-pose' : 'ref-type-view';
                const typeLabel = ref.type === 'pose' ? '姿势' : '视角';
                rhtml += `
                    <div class="ref-card">
                        ${refUrl
                            ? `<img src="${refUrl}" alt="${label}" onclick="window.__lightbox(${JSON.stringify(allUrls)},${idx})">`
                            : '<div style="width:100%;aspect-ratio:1;background:#131320;display:flex;align-items:center;justify-content:center;font-size:32px;opacity:0.3;">🖼️</div>'
                        }
                        <div class="ref-info">
                            <h5>${label}</h5>
                            <span class="ref-type ${typeClass}">${typeLabel}</span>
                        </div>
                    </div>`;
            });
            refGrid.innerHTML = rhtml;
        }

        // Update enrich panel
        const enrichInfo = $('#enrichCurrentModel');
        if (enrichInfo) {
            enrichInfo.innerHTML = `<strong>📌 ${data.name}</strong> — ${refs.length} 张参考图`;
            enrichInfo.style.borderColor = 'var(--accent)';
            enrichInfo.style.color = 'var(--text-primary)';
        }
        const btnEnrich = $('#btnEnrich');
        if (btnEnrich) btnEnrich.disabled = false;

        mlog('success', `加载模特详情完成: ${data.name}`);
    } catch (e) {
        mlog('error', '加载模特详情失败: ' + e.message);
        toast('加载模特详情失败', 'error');
    }
}

function backToModelList() {
    currentModelId = null;
    currentModelName = '';
    $('#modelDetailCard').style.display = 'none';
    const enrichInfo = $('#enrichCurrentModel');
    if (enrichInfo) {
        enrichInfo.innerHTML = '← 请先在右侧点击选择一个模特';
        enrichInfo.style.borderColor = 'var(--border)';
        enrichInfo.style.color = 'var(--text-secondary)';
    }
    const btnEnrich = $('#btnEnrich');
    if (btnEnrich) btnEnrich.disabled = true;
    loadModelList();
}

// ===== Create Model =====
async function createModel() {
    const btn = $('#btnCreateModel');
    btn.disabled = true;
    btn.innerHTML = '<div class="spinner"></div> 生成中...';
    mlog('info', `开始创建模特 (${createMode === 'text' ? '文生图' : '图片上传'})...`);

    try {
        let data;
        if (createMode === 'text') {
            const name = $('#cmName').value.trim();
            if (!name) { toast('请输入模特名称', 'error'); mlog('error', '缺少模特名称'); return; }

            const fd = new FormData();
            fd.append('name', name);
            fd.append('description', $('#cmDescription').value.trim());
            fd.append('gender', $('#cmGender').value);
            fd.append('style', $('#cmStyle').value.trim() || '时尚写真');
            const tags = $('#cmTags').value.trim();
            if (tags) fd.append('tags', JSON.stringify(tags.split(',').map(t => t.trim()).filter(Boolean)));

            mlog('info', `参数: 名称="${name}", 性别=${$('#cmGender').value}, 风格=${$('#cmStyle').value.trim()}`);
            data = await API.generateModel(fd);
        } else {
            if (!cmSelectedFile) { toast('请选择图片', 'error'); mlog('error', '未选择图片'); return; }

            const fd = new FormData();
            fd.append('image', cmSelectedFile);
            fd.append('name', $('#cmImgName').value.trim() || cmSelectedFile.name);
            fd.append('description', $('#cmImgDesc').value.trim());
            fd.append('gender', $('#cmImgGender').value);
            const tags = $('#cmImgTags').value.trim();
            if (tags) fd.append('tags', JSON.stringify(tags.split(',').map(t => t.trim()).filter(Boolean)));

            mlog('info', `上传图片: ${cmSelectedFile.name}`);
            data = await API.generateModelFromImg(fd);
        }

        if (data.model_id) {
            mlog('success', `模特创建成功: ${data.name || data.model_id}`);
            toast('模特创建成功！', 'success');
            loadModelList();
            viewModelDetail(data.model_id);
        } else {
            mlog('error', '创建失败: ' + (data.error || '未知错误'));
            toast('创建失败: ' + (data.error || '未知错误'), 'error');
        }
    } catch (e) {
        mlog('error', '请求失败: ' + e.message);
        toast('请求失败: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '🚀 开始生成模特';
    }
}

// ===== Enrich =====
async function enrichModel() {
    if (!currentModelId) { toast('请先选择一个模特', 'error'); return; }
    const selected = $$('#enrichOptions .enrich-option.active');
    if (selected.length === 0) { toast('请至少选择一个参考图类型', 'error'); return; }

    const refs = [];
    selected.forEach(el => refs.push({ name: el.dataset.name, type: el.dataset.type }));

    const btn = $('#btnEnrich');
    btn.disabled = true;
    btn.innerHTML = '<div class="spinner"></div> 生成中...';
    mlog('info', `开始追加 ${refs.length} 张参考图给模特 "${currentModelName}"...`);
    refs.forEach(r => mlog('info', `  → ${viewLabels[r.name] || r.name} (${r.type})`));

    try {
        const fd = new FormData();
        fd.append('references', JSON.stringify(refs));
        const data = await API.enrichModel(currentModelId, fd);

        if (data.error) {
            mlog('error', '生成失败: ' + data.error);
            toast('生成失败: ' + data.error, 'error');
        } else {
            const cnt = (data.references || []).length;
            mlog('success', `参考图生成完成！共 ${cnt} 张`);
            toast(`参考图生成完成！共 ${cnt} 张`, 'success');
            // Clear selections
            $$('#enrichOptions .enrich-option').forEach(o => o.classList.remove('active'));
            viewModelDetail(currentModelId);
        }
    } catch (e) {
        mlog('error', '请求失败: ' + e.message);
        toast('请求失败: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '🎯 开始追加';
    }
}

// ===== Delete =====
async function deleteModel(modelId, name) {
    if (!confirm(`确定要删除模特 "${name}" 吗？\n此操作不可恢复。`)) return;
    mlog('info', `正在删除模特: ${name}...`);
    try {
        await API.deleteModel(modelId);
        mlog('success', `模特 "${name}" 已删除`);
        toast(`模特 "${name}" 已删除`, 'success');
        if (currentModelId === modelId) backToModelList();
        else loadModelList();
    } catch (e) {
        mlog('error', '删除失败: ' + e.message);
        toast('请求失败: ' + e.message, 'error');
    }
}

function deleteCurrentModel() {
    if (currentModelId && currentModelName) {
        deleteModel(currentModelId, currentModelName);
    }
}

// ===== Expose to window =====
window.__switchModelMode = switchModelMode;
window.__switchCreateMode = switchCreateMode;
window.__createModel = createModel;
window.__viewModel = viewModelDetail;
window.__backToModelList = backToModelList;
window.__toggleEnrichOption = function(el) { el.classList.toggle('active'); };
window.__enrichModel = enrichModel;
window.__deleteModel = deleteModel;
window.__deleteCurrentModel = deleteCurrentModel;
