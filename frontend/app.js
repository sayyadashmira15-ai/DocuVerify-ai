const API = "/api";

const state = { documents: [] };

const $ = (id) => document.getElementById(id);

const ui = {
    fileInput: $("fileInput"),
    dropzone: $("dropzone"),
    documentCount: $("documentCount"),
    documentList: $("documentList"),
    documentSearch: $("documentSearch"),
    selectAllButton: $("selectAllButton"),
    clearWorkspaceButton: $("clearWorkspaceButton"),
    questionInput: $("questionInput"),
    investigateButton: $("investigateButton"),
    selectionLabel: $("selectionLabel"),
    loadingState: $("loadingState"),
    resultSection: $("resultSection"),
    resultTitle: $("resultTitle"),
    verdictBadge: $("verdictBadge"),
    answerText: $("answerText"),
    findingsList: $("findingsList"),
    confidenceValue: $("confidenceValue"),
    confidenceLabel: $("confidenceLabel"),
    confidenceBar: $("confidenceBar"),
    conflictPanel: $("conflictPanel"),
    conflictList: $("conflictList"),
    sourcesList: $("sourcesList"),
    historyList: $("historyList"),
    toast: $("toast"),
    toastMessage: $("toastMessage"),
    engineStatus: $("engineStatus"),
};

let toastTimer;

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function showToast(message) {
    ui.toastMessage.textContent = message;
    ui.toast.classList.remove("hidden");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => ui.toast.classList.add("hidden"), 3600);
}

async function apiRequest(path, options = {}) {
    const response = await fetch(`${API}${path}`, options);
    const contentType = response.headers.get("content-type") || "";
    let data;

    if (contentType.includes("application/json")) {
        data = await response.json();
    } else {
        const text = await response.text();
        throw new Error(`Server returned an unexpected response (${response.status}).` + (text ? ` ${text.slice(0, 140)}` : ""));
    }

    if (!response.ok) {
        throw new Error(data.detail || "Request failed.");
    }

    return data;
}

async function checkHealth() {
    try {
        await apiRequest("/health");
        ui.engineStatus.className = "engine-status online";
        ui.engineStatus.innerHTML = '<span class="status-dot"></span> Local AI engine ready';
    } catch (error) {
        ui.engineStatus.className = "engine-status offline";
        ui.engineStatus.innerHTML = '<span class="status-dot"></span> API unavailable';
    }
}

async function loadDocuments() {
    try {
        state.documents = await apiRequest("/documents");
        renderDocuments();
        updateSelectionLabel();
    } catch (error) {
        showToast(`Unable to load evidence: ${error.message}`);
    }
}

function selectedDocumentIds() {
    return [...ui.documentList.querySelectorAll(".document-item")]
        .filter((item) => item.querySelector(".document-checkbox")?.checked)
        .map((item) => item.dataset.documentId);
}

function updateSelectionLabel() {
    const selected = selectedDocumentIds();
    if (selected.length === 0 || selected.length === state.documents.length) {
        ui.selectionLabel.textContent = "All documents";
    } else {
        ui.selectionLabel.textContent = `${selected.length} selected`;
    }
}

function renderDocuments() {
    const search = ui.documentSearch.value.trim().toLowerCase();
    const filtered = state.documents.filter((doc) => doc.name.toLowerCase().includes(search));
    ui.documentCount.textContent = state.documents.length;

    if (!filtered.length) {
        ui.documentList.innerHTML = `
            <div class="empty-library">
                <span>⌁</span>
                <strong>${state.documents.length ? "No matching evidence" : "No evidence loaded"}</strong>
                <small>${state.documents.length ? "Try a different search term." : "Upload two documents with different claims to test conflict detection."}</small>
            </div>`;
        return;
    }

    ui.documentList.innerHTML = filtered.map((doc) => `
        <div class="document-item" data-document-id="${escapeHtml(doc.id)}">
            <input class="document-checkbox" type="checkbox" aria-label="Select ${escapeHtml(doc.name)}">
            <div class="doc-type">${escapeHtml(doc.format)}</div>
            <div class="document-meta">
                <div class="document-name" title="${escapeHtml(doc.name)}">${escapeHtml(doc.name)}</div>
                <div class="document-details">${doc.chunks} chunks · ${formatCharacters(doc.characters)}</div>
            </div>
            <button class="remove-document" type="button" aria-label="Remove document" title="Remove">×</button>
        </div>
    `).join("");

    ui.documentList.querySelectorAll(".document-item").forEach((item) => {
        const checkbox = item.querySelector(".document-checkbox");
        checkbox.addEventListener("change", () => {
            item.classList.toggle("selected", checkbox.checked);
            updateSelectionLabel();
        });
        item.querySelector(".remove-document").addEventListener("click", (event) => {
            event.preventDefault();
            removeDocument(item.dataset.documentId);
        });
    });
}

function formatCharacters(value) {
    const n = Number(value) || 0;
    if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M chars`;
    if (n >= 1000) return `${(n / 1000).toFixed(1)}K chars`;
    return `${n} chars`;
}

async function uploadFiles(files) {
    const fileArray = [...files];
    if (!fileArray.length) return;

    for (const file of fileArray) {
        try {
            const extension = `.${file.name.split(".").pop().toLowerCase()}`;
            if (![".pdf", ".docx", ".txt"].includes(extension)) {
                showToast(`${file.name}: use PDF, DOCX or TXT.`);
                continue;
            }

            const data = new FormData();
            data.append("file", file);
            showToast(`Indexing ${file.name}…`);
            const result = await apiRequest("/upload", { method: "POST", body: data });
            showToast(`${result.name} indexed successfully.`);
        } catch (error) {
            showToast(`${file.name}: ${error.message}`);
        }
    }

    ui.fileInput.value = "";
    await loadDocuments();
}

async function removeDocument(id) {
    const doc = state.documents.find((item) => item.id === id);
    if (!doc) return;
    if (!window.confirm(`Remove “${doc.name}” from the evidence set?`)) return;

    try {
        await apiRequest(`/documents/${encodeURIComponent(id)}`, { method: "DELETE" });
        await loadDocuments();
        showToast("Evidence removed.");
    } catch (error) {
        showToast(`Unable to remove evidence: ${error.message}`);
    }
}

async function clearWorkspace() {
    if (!state.documents.length) {
        showToast("Workspace is already empty.");
        return;
    }
    if (!window.confirm("Clear all evidence and investigation history?")) return;

    try {
        await apiRequest("/documents", { method: "DELETE" });
        state.documents = [];
        renderDocuments();
        resetResult();
        await loadHistory();
        updateSelectionLabel();
        showToast("Workspace cleared.");
    } catch (error) {
        showToast(`Unable to clear workspace: ${error.message}`);
    }
}

function setLoading(loading) {
    ui.loadingState.classList.toggle("hidden", !loading);
    ui.investigateButton.disabled = loading;
    ui.investigateButton.innerHTML = loading ? "<span>Investigating…</span><b>↻</b>" : "<span>Investigate</span><b>↗</b>";
}

async function investigate() {
    const question = ui.questionInput.value.trim();
    if (!question) {
        showToast("Enter a question before starting the investigation.");
        ui.questionInput.focus();
        return;
    }
    if (!state.documents.length) {
        showToast("Upload at least one document first.");
        return;
    }

    const selected = selectedDocumentIds();
    const payload = { question };
    if (selected.length > 0 && selected.length < state.documents.length) payload.document_ids = selected;

    setLoading(true);
    try {
        const result = await apiRequest("/ask", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        renderResult(result);
        await loadHistory();
        ui.resultSection.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
        showToast(`Investigation failed: ${error.message}`);
    } finally {
        setLoading(false);
    }
}

function renderResult(result) {
    ui.resultSection.classList.remove("hidden");

    const verdict = String(result.verdict || "INSUFFICIENT").toLowerCase();
    const titleMap = {
        supported: "Evidence supports the conclusion",
        conflict: "Conflicting evidence requires review",
        insufficient: "The evidence is not sufficient",
    };
    const labelMap = { supported: "SUPPORTED", conflict: "CONFLICT", insufficient: "INSUFFICIENT" };

    ui.resultTitle.textContent = titleMap[verdict] || titleMap.insufficient;
    ui.verdictBadge.textContent = labelMap[verdict] || "INSUFFICIENT";
    ui.verdictBadge.className = `verdict-badge ${verdict}`;
    ui.answerText.textContent = result.answer || "No reliable conclusion was produced.";

    renderFindings(result.key_findings || []);
    renderConfidence(result.confidence, result.confidence_label);
    renderConflicts(result.conflicts?.length ? result.conflicts : (result.possible_conflicts || []), result.conflicts?.length > 0);
    renderSources(result.sources || []);
}

function renderFindings(findings) {
    if (!findings.length) {
        ui.findingsList.innerHTML = `<div class="finding"><span class="finding-mark">i</span><span>No separate findings were returned. Review the source evidence below.</span></div>`;
        return;
    }
    ui.findingsList.innerHTML = findings.map((finding) => `<div class="finding"><span class="finding-mark">✓</span><span>${escapeHtml(finding)}</span></div>`).join("");
}

function renderConfidence(value, label) {
    const confidence = Math.max(0, Math.min(100, Number(value) || 0));
    ui.confidenceValue.textContent = `${Math.round(confidence)}%`;
    ui.confidenceLabel.textContent = label || (confidence >= 75 ? "High" : confidence >= 50 ? "Medium" : "Low");
    ui.confidenceBar.style.width = `${confidence}%`;
}

function renderConflicts(conflicts, confirmed) {
    if (!conflicts.length) {
        ui.conflictPanel.classList.add("hidden");
        ui.conflictList.innerHTML = "";
        return;
    }

    ui.conflictPanel.classList.remove("hidden");
    ui.conflictPanel.querySelector(".conflict-title h3").textContent = confirmed ? "These claims need review" : "Possible inconsistency detected";
    ui.conflictList.innerHTML = conflicts.map((conflict) => `
        <div class="conflict-entry">
            <div class="conflict-docs">
                ${(conflict.documents || []).map((doc) => `<span class="conflict-doc">${escapeHtml(doc)}</span>`).join("")}
            </div>
            <p class="conflict-reason">${escapeHtml(conflict.reason || "The retrieved sources may disagree and should be compared directly.")}</p>
        </div>
    `).join("");
}

function renderSources(sources) {
    if (!sources.length) {
        ui.sourcesList.innerHTML = `<div class="source-entry"><p class="source-snippet">No source evidence was retrieved.</p></div>`;
        return;
    }

    ui.sourcesList.innerHTML = sources.map((source) => {
        const location = [source.page ? `Page ${source.page}` : null, source.section || null].filter(Boolean).join(" · ") || "Location unavailable";
        const score = Number(source.score);
        const matchLabel = Number.isFinite(score) ? `${Math.round(score * 100)}% match` : "Evidence";
        return `
            <article class="source-entry">
                <div class="source-top">
                    <div>
                        <div class="source-name" title="${escapeHtml(source.document)}">${escapeHtml(source.document)}</div>
                        <div class="source-location">${escapeHtml(location)}</div>
                    </div>
                    <span class="source-score">${escapeHtml(matchLabel)}</span>
                </div>
                <p class="source-snippet">${escapeHtml(source.snippet || "No preview available.")}</p>
            </article>`;
    }).join("");
}

function resetResult() {
    ui.resultSection.classList.add("hidden");
    ui.conflictPanel.classList.add("hidden");
    ui.sourcesList.innerHTML = "";
    ui.findingsList.innerHTML = "";
    ui.conflictList.innerHTML = "";
    ui.confidenceBar.style.width = "0%";
}

async function loadHistory() {
    try {
        const history = await apiRequest("/history");
        renderHistory(history);
    } catch (error) {
        ui.historyList.innerHTML = `<div class="history-empty">History unavailable.</div>`;
    }
}

function renderHistory(history) {
    if (!history.length) {
        ui.historyList.innerHTML = `<div class="history-empty">Your recent investigations will appear here.</div>`;
        return;
    }

    ui.historyList.innerHTML = history.map((item) => {
        const verdict = String(item.verdict || "INSUFFICIENT").toLowerCase();
        return `
            <div class="history-row">
                <div>
                    <div class="history-question">${escapeHtml(item.question)}</div>
                    <div class="history-docs">${escapeHtml((item.documents || []).join(", "))}</div>
                </div>
                <span class="history-verdict ${verdict}">${escapeHtml(verdict.toUpperCase())}</span>
            </div>`;
    }).join("");
}

function setupInteractions() {
    ui.fileInput.addEventListener("change", () => uploadFiles(ui.fileInput.files));
    ui.documentSearch.addEventListener("input", renderDocuments);
    ui.investigateButton.addEventListener("click", investigate);
    ui.clearWorkspaceButton.addEventListener("click", clearWorkspace);

    ui.selectAllButton.addEventListener("click", () => {
        const all = selectedDocumentIds().length === state.documents.length && state.documents.length > 0;
        ui.documentList.querySelectorAll(".document-checkbox").forEach((checkbox) => {
            checkbox.checked = !all;
            checkbox.closest(".document-item").classList.toggle("selected", !all);
        });
        updateSelectionLabel();
    });

    document.querySelectorAll(".suggestion").forEach((button) => {
        button.addEventListener("click", () => {
            ui.questionInput.value = button.textContent.trim();
            ui.questionInput.focus();
        });
    });

    ui.questionInput.addEventListener("keydown", (event) => {
        if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
            event.preventDefault();
            investigate();
        }
    });

    ["dragenter", "dragover"].forEach((eventName) => {
        ui.dropzone.addEventListener(eventName, (event) => {
            event.preventDefault();
            ui.dropzone.classList.add("dragover");
        });
    });
    ["dragleave", "drop"].forEach((eventName) => {
        ui.dropzone.addEventListener(eventName, (event) => {
            event.preventDefault();
            ui.dropzone.classList.remove("dragover");
        });
    });
    ui.dropzone.addEventListener("drop", (event) => uploadFiles(event.dataTransfer.files));
}

(async function boot() {
    setupInteractions();
    await checkHealth();
    await loadDocuments();
    await loadHistory();
})();
