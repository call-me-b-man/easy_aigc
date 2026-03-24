// ===== Easy AIGC — 剧本分镜逻辑 =====
import { API, resolveImageUrl } from './api.js';
import { $, $$, toast, log, openLightbox } from './components.js';

let selectedImages = []; // Array of { type: 'file'/'path', data: File|string, id: number }
let imageCounter = 0;

export function initStoryboard() {
    const uploadArea = $('#sbUploadArea');
    const fileInput = $('#sbFileInput');
    const btnGen = $('#btnGenStoryboard');
    const providerSel = $('#sbProvider');
    const modelSel = $('#sbModel');

    if (!uploadArea) return;

    // --- Upload ---
    uploadArea.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', (e) => handleFiles(e.target.files));
    uploadArea.addEventListener('dragover', (e) => { e.preventDefault(); uploadArea.classList.add('dragover'); });
    uploadArea.addEventListener('dragleave', () => uploadArea.classList.remove('dragover'));
    uploadArea.addEventListener('drop', (e) => { 
        e.preventDefault(); 
        uploadArea.classList.remove('dragover'); 
        handleFiles(e.dataTransfer.files); 
    });

    function handleFiles(files) {
        if (!files || files.length === 0) return;
        let added = 0;
        for (const file of files) {
            if (file.type.startsWith('image/')) {
                selectedImages.push({ type: 'file', data: file, id: imageCounter++ });
                added++;
            }
        }
        if (added > 0) {
            toast(`已添加 ${added} 张图`, 'success');
            renderSelectedImages();
        }
    }

    // --- Provide / Model ---
    providerSel.addEventListener('change', loadStoryboardModels);
    
    // --- Actions ---
    btnGen.addEventListener('click', generateStoryboard);

    loadStoryboardModels();
}

// ==== UI Update ====
function renderSelectedImages() {
    const container = $('#sbSelectedImages');
    const btnGen = $('#btnGenStoryboard');

    if (selectedImages.length === 0) {
        container.innerHTML = '<div class="empty-state" style="width:100%;padding:16px;">尚未添加任何图片</div>';
        btnGen.disabled = true;
        return;
    }

    btnGen.disabled = false;
    let html = '';
    selectedImages.forEach((item, index) => {
        const urlId = `sb_img_${item.id}`;
        html += `
            <div class="sb-img-thumb" style="position:relative; width:64px; height:64px; border-radius:4px; overflow:hidden; border:1px solid var(--border);">
                <img id="${urlId}" src="" style="width:100%; height:100%; object-fit:cover;">
                <div style="position:absolute; top:2px; right:2px; background:rgba(0,0,0,0.5); color:#fff; border-radius:50%; width:16px; height:16px; display:flex; align-items:center; justify-content:center; font-size:10px; cursor:pointer;" onclick="window.__removeSbImage(${item.id})">✕</div>
                <div style="position:absolute; bottom:0; left:0; right:0; background:rgba(0,0,0,0.6); color:white; font-size:10px; text-align:center; padding:1px;">图 ${index + 1}</div>
            </div>
        `;
    });
    container.innerHTML = html;

    // Load actual images
    selectedImages.forEach(item => {
        const imgEl = document.getElementById(`sb_img_${item.id}`);
        if (!imgEl) return;
        if (item.type === 'file') {
            const reader = new FileReader();
            reader.onload = (e) => imgEl.src = e.target.result;
            reader.readAsDataURL(item.data);
        } else if (item.type === 'path') {
            imgEl.src = resolveImageUrl(item.data);
        }
    });
}

window.__removeSbImage = function(id) {
    selectedImages = selectedImages.filter(item => item.id !== id);
    renderSelectedImages();
};

window.__addSbImageFromPath = function(path) {
    // Check if duplicate
    const exists = selectedImages.find(i => i.type === 'path' && i.data === path);
    if (!exists) {
        selectedImages.push({ type: 'path', data: path, id: imageCounter++ });
        renderSelectedImages();
        toast('已添加到分镜', 'success');
    } else {
        toast('图片已在分镜列表中', 'warning');
    }
};

window.__addMultipleSbImagesFromPath = function(paths) {
    let added = 0;
    paths.forEach(path => {
        const exists = selectedImages.find(i => i.type === 'path' && i.data === path);
        if (!exists) {
            selectedImages.push({ type: 'path', data: path, id: imageCounter++ });
            added++;
        }
    });
    if (added > 0) {
        renderSelectedImages();
        toast(`已添加 ${added} 张图到分镜`, 'success');
    }
};

// ==== Models ====
async function loadStoryboardModels() {
    const providerSel = $('#sbProvider');
    const modelSel = $('#sbModel');
    try {
        const providers = await API.getProviders();
        modelSel.innerHTML = '<option value="">默认 (Qwen2.5-VL-72B)</option>';
        const selected = providerSel.value;
        for (const p of providers) {
            if (!selected || p.name === selected) {
                for (const m of p.models) {
                    if (m.capabilities.includes('vlm') || m.capabilities.includes('chat')) { // Note: config might not have 'vlm' explicit, but we add all chat models or vlm models
                        const opt = document.createElement('option');
                        opt.value = m.id;
                        opt.textContent = `${m.name} (${p.name})`;
                        modelSel.appendChild(opt);
                    }
                }
            }
        }
    } catch (e) {
        console.error('获取模型列表失败', e);
    }
}

// ==== Generate ====
async function generateStoryboard() {
    if (selectedImages.length === 0) return;
    
    const btn = $('#btnGenStoryboard');
    btn.disabled = true;
    btn.innerHTML = '<div class="spinner"></div> 生成中...';
    log('info', '开始生成剧本与分镜...');

    const container = $('#sbResultContent');
    container.innerHTML = `
        <div style="padding:40px; text-align:center; color:var(--text-secondary);">
            <div class="spinner" style="width:32px; height:32px; border-width:4px; margin:0 auto 16px;"></div>
            <div>AI 正在分析画面并编写剧本，这可能需要 30 秒到 1 分钟...</div>
        </div>
    `;

    try {
        const fd = new FormData();
        const paths = [];

        selectedImages.forEach(item => {
            if (item.type === 'file') {
                fd.append('images', item.data);
            } else {
                paths.push(item.data);
            }
        });

        if (paths.length > 0) {
            fd.append('image_paths', JSON.stringify(paths));
        }

        const customPrompt = $('#sbCustomPrompt').value.trim();
        const provider = $('#sbProvider').value;
        const model = $('#sbModel').value;

        if (customPrompt) fd.append('custom_prompt', customPrompt);
        if (provider) fd.append('provider', provider);
        if (model) fd.append('model', model);

        const data = await API.generateStoryboard(fd);
        
        if (data && data.scenes) {
            renderStoryboardResult(data);
            log('success', '剧本分镜生成完成');
            toast('分镜生成成功！', 'success');
            // Check generation records
            import('./generation.js').then(m => m.loadHistory && m.loadHistory());
        } else {
            throw new Error(data.error || "生成失败，未返回结构化分镜");
        }

    } catch (e) {
        log('error', `生成失败: ${e.message}`);
        toast('生成失败: ' + e.message, 'error');
        container.innerHTML = `
            <div class="empty-state" style="padding:60px 20px;">
                <div class="icon-huge">❌</div>
                <p style="color:var(--error);">生成失败：${e.message}</p>
            </div>
        `;
    }

    btn.disabled = false;
    btn.innerHTML = '🎬 开始生成剧本分镜';
}

function renderStoryboardResult(data) {
    const container = $('#sbResultContent');
    
    // Resolve all image URLs to pass to lightbox
    const allUrls = [];
    selectedImages.forEach(item => {
        if (item.type === 'file') {
            allUrls.push(URL.createObjectURL(item.data));
        } else {
            allUrls.push(resolveImageUrl(item.data));
        }
    });

    let html = `
        <div style="margin-bottom:24px; padding-bottom:16px; border-bottom:1px solid var(--border);">
            <h2 style="font-size:20px; font-weight:700; margin-bottom:8px;">${data.script_title || '未命名剧本'}</h2>
            <p style="font-size:14px; color:var(--text-secondary); line-height:1.6;">${data.script_content || '暂无概要'}</p>
            <div style="display:flex; gap:12px; margin-top:12px; font-size:12px; color:var(--text-muted);">
                <span>用时: ${data.duration ? data.duration.toFixed(1) : '?'}s</span>
                <span>提供商: ${data.provider_used}</span>
                <span>模型: ${data.model_used}</span>
            </div>
        </div>
        <div style="display:flex; flex-direction:column; gap:16px;">
    `;

    data.scenes.forEach((scene, i) => {
        const imgIdx = scene.image_index - 1;
        const imgUrl = (imgIdx >= 0 && imgIdx < allUrls.length) ? allUrls[imgIdx] : '';

        html += `
            <div style="display:flex; gap:16px; background:var(--bg-secondary); border-radius:var(--radius-md); padding:16px; border:1px solid var(--border);">
                <!-- Left: Thumbnail -->
                <div style="width:120px; min-width:120px; height:120px; border-radius:var(--radius-sm); overflow:hidden; background:var(--bg-input); display:flex; align-items:center; justify-content:center;">
                    ${imgUrl 
                        ? `<img src="${imgUrl}" style="width:100%; height:100%; object-fit:cover; cursor:pointer;" onclick="window.__lightbox(${JSON.stringify(allUrls)}, ${imgIdx})">` 
                        : `<span style="font-size:24px; color:var(--text-muted);">🎞️</span>`
                    }
                </div>
                <!-- Right: Content -->
                <div style="flex:1; display:flex; flex-direction:column; justify-content:space-between; font-size:13px; gap:8px;">
                    <div>
                        <h4 style="font-size:15px; font-weight:600; margin-bottom:6px; display:flex; align-items:center; gap:8px;">
                            <span style="background:var(--accent); color:white; padding:2px 8px; border-radius:12px; font-size:11px;">镜头 ${scene.image_index}</span>
                            ${scene.duration ? `<span style="color:var(--text-secondary); font-size:12px; font-weight:400;">⏱️ ${scene.duration}</span>` : ''}
                        </h4>
                        <div style="margin-bottom:6px;"><strong>画面描述:</strong> <span style="color:var(--text-secondary);">${scene.scene_description || '-'}</span></div>
                        <div style="margin-bottom:6px;"><strong>运镜设计:</strong> <span style="color:var(--text-secondary);">${scene.camera_movement || '-'}</span></div>
                        ${scene.dialogue ? `<div style="margin-bottom:6px; padding:6px; background:rgba(0,0,0,0.1); border-left:2px solid var(--accent);"><strong>对话/旁白:</strong> <span>${scene.dialogue}</span></div>` : ''}
                        ${scene.notes ? `<div><strong>备注:</strong> <span style="color:var(--text-secondary);">${scene.notes}</span></div>` : ''}
                    </div>
                </div>
            </div>
        `;
    });

    html += `</div>`;
    container.innerHTML = html;
}
