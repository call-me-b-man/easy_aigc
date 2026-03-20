// ===== Easy AIGC — Shared UI Components =====

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// ===== Toast =====
export function toast(msg, type = 'success') {
    const el = document.createElement('div');
    el.className = `toast toast-${type}`;
    el.textContent = msg;
    $('#toasts').appendChild(el);
    setTimeout(() => el.remove(), 4000);
}

// ===== Log =====
export function log(type, msg) {
    const logArea = $('#logArea');
    if (!logArea) return;
    const cls = type === 'error' ? 'log-error' : type === 'success' ? 'log-success' : 'log-info';
    const time = new Date().toLocaleTimeString('zh-CN', { hour12: false });
    const line = document.createElement('div');
    line.className = 'log-line';
    line.innerHTML = `<span class="log-time">${time}</span><span class="${cls}">${msg}</span>`;
    logArea.appendChild(line);
    logArea.scrollTop = logArea.scrollHeight;
}

// ===== Lightbox =====
let lightboxImages = [];
let lightboxIndex = 0;

export function openLightbox(images, startIndex = 0) {
    lightboxImages = images;
    lightboxIndex = startIndex;
    const overlay = $('#lightboxOverlay');
    const img = $('#lightboxImg');
    img.src = images[startIndex];
    overlay.classList.add('active');

    // Show/hide nav buttons
    const prev = $('#lightboxPrev');
    const next = $('#lightboxNext');
    if (prev) prev.style.display = images.length > 1 ? 'flex' : 'none';
    if (next) next.style.display = images.length > 1 ? 'flex' : 'none';
}

export function closeLightbox() {
    $('#lightboxOverlay').classList.remove('active');
}

function navigateLightbox(dir) {
    lightboxIndex = (lightboxIndex + dir + lightboxImages.length) % lightboxImages.length;
    $('#lightboxImg').src = lightboxImages[lightboxIndex];
}

export function initLightbox() {
    const overlay = $('#lightboxOverlay');
    if (!overlay) return;

    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closeLightbox();
    });
    const closeBtn = $('#lightboxClose');
    if (closeBtn) closeBtn.addEventListener('click', closeLightbox);
    const prev = $('#lightboxPrev');
    if (prev) prev.addEventListener('click', () => navigateLightbox(-1));
    const next = $('#lightboxNext');
    if (next) next.addEventListener('click', () => navigateLightbox(1));

    // Keyboard navigation
    document.addEventListener('keydown', (e) => {
        if (!overlay.classList.contains('active')) return;
        if (e.key === 'Escape') closeLightbox();
        if (e.key === 'ArrowLeft') navigateLightbox(-1);
        if (e.key === 'ArrowRight') navigateLightbox(1);
    });
}

// Re-export $ for convenience
export { $, $$ };
