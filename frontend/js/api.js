// ===== Easy AIGC — API Layer =====

const API_BASE = window.location.origin;

/**
 * Unified fetch wrapper with error handling.
 */
async function request(method, path, body = null, isForm = false) {
    const opts = { method };
    if (body) {
        if (isForm) {
            opts.body = body; // FormData — browser sets Content-Type
        } else {
            opts.headers = { 'Content-Type': 'application/json' };
            opts.body = JSON.stringify(body);
        }
    }
    const res = await fetch(`${API_BASE}${path}`, opts);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || data.error || `HTTP ${res.status}`);
    return data;
}

// ===== Public API Methods =====

export const API = {
    // --- Health ---
    async health() {
        const res = await fetch(`${API_BASE}/health`);
        return res.ok;
    },

    // --- Config / Settings ---
    getConfig:     ()       => request('GET', '/api/v1/config'),
    updateConfig:  (data)   => request('PUT', '/api/v1/config', data),
    getProviders:  ()       => request('GET', '/api/v1/config/providers'),

    // --- Generation ---
    extractSubject: (fd) => request('POST', '/api/v1/generation/extract-subject', fd, true),
    pipeline:       (fd) => request('POST', '/api/v1/generation/pipeline', fd, true),
    history:        (limit = 20) => request('GET', `/api/v1/generation/history?limit=${limit}`),

    // --- Models ---
    listModels:          (limit = 50, offset = 0) => request('GET', `/api/v1/models?limit=${limit}&offset=${offset}`),
    getModel:            (id) => request('GET', `/api/v1/models/${id}`),
    generateModel:       (fd) => request('POST', '/api/v1/models/generate', fd, true),
    generateModelFromImg:(fd) => request('POST', '/api/v1/models/generate-from-image', fd, true),
    enrichModel:         (id, fd) => request('POST', `/api/v1/models/${id}/enrich`, fd, true),
    deleteModel:         (id) => request('DELETE', `/api/v1/models/${id}`),
};

/**
 * Convert local file paths returned by backend to accessible URLs.
 * Handles paths like "./output/xxx", "C:\\...\\output\\xxx", etc.
 */
export function resolveImageUrl(localPath) {
    if (!localPath) return '';
    const normalized = localPath.replace(/\\\\/g, '/').replace(/\\/g, '/');

    // Model paths mounted at /models/
    const modelsIdx = normalized.indexOf('/output/models/');
    if (modelsIdx !== -1) return '/models/' + normalized.substring(modelsIdx + 15);

    // General output paths mounted at /output/
    const outputIdx = normalized.indexOf('/output/');
    if (outputIdx !== -1) return '/output/' + normalized.substring(outputIdx + 8);

    // Relative paths
    if (normalized.startsWith('./output/models/')) return '/models/' + normalized.substring(16);
    if (normalized.startsWith('output/models/'))  return '/models/' + normalized.substring(14);
    if (normalized.startsWith('./output/'))        return '/output/' + normalized.substring(9);
    if (normalized.startsWith('output/'))          return '/output/' + normalized.substring(7);

    return normalized;
}
