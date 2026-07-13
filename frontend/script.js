"use strict";

const API_BASE =
    window.location.hostname === "localhost"
        ? "http://127.0.0.1:5000"
        : "https://ai-latex-diagram-generator.onrender.com";
const EMPTY_TIKZ_TEXT = "% Generated TikZ code will appear here.";
const MAX_UPLOAD_SIZE = 10 * 1024 * 1024;
const ALLOWED_UPLOAD_TYPES = new Set(["png", "jpg", "jpeg"]);
const WORKFLOW_STEPS = [
  "Understanding prompt",
  "Generating TikZ",
  "Validating",
  "Compiling PDF",
  "Creating PNG",
  "Complete",
];

class RequestError extends Error {
  constructor(message, payload = null) {
    super(message);
    this.name = "RequestError";
    this.payload = payload;
  }
}

const state = {
  uploadedFile: null,
  uploadPreviewUrl: "",
  generation: null,
  refinement: null,
  tikzCode: "",
  currentPrompt: "",
  lastAction: null,
  zoom: 1,
  history: [],
  timers: [],
  downloads: {
    pdf: "",
    png: "",
    tex: "",
    zip: "",
  },
};

document.addEventListener("DOMContentLoaded", initialize);

function initialize() {
  bindActions();
  bindTabs();
  bindPreviewControls();
  bindUploadZone();
  bindCodeControls();
  bindDownloadControls();

  updateTikzOutput("");
  updatePreview(null);
  updatePdfPreview(null);
  updateDownloads(null);
  renderHistory();
  setWorkflowIdle();
  setStatus("Ready for input.", "ready", "Ready");
}

function bindActions() {
  const form = document.getElementById("diagram-form");
  if (form) {
    form.addEventListener("submit", (event) => event.preventDefault());
  }

  getRequiredElement("generate-btn").addEventListener("click", Generate);
  getRequiredElement("upload-btn").addEventListener("click", Upload);
  getRequiredElement("refine-btn").addEventListener("click", Refine);
  getRequiredElement("clear-btn").addEventListener("click", ClearWorkspace);
  getRequiredElement("retry-btn").addEventListener("click", retryLastAction);
}

function bindTabs() {
  document.querySelectorAll("[data-tab]").forEach((button) => {
    button.addEventListener("click", () => activateTab(button.dataset.tab));
    button.addEventListener("keydown", handleTabKeyboard);
  });

  document.querySelectorAll("[data-preview-tab]").forEach((button) => {
    button.addEventListener("click", () => activatePreviewTab(button.dataset.previewTab));
    button.addEventListener("keydown", handlePreviewTabKeyboard);
  });
}

function bindPreviewControls() {
  getRequiredElement("zoom-in-btn").addEventListener("click", () => setZoom(state.zoom + 0.15));
  getRequiredElement("zoom-out-btn").addEventListener("click", () => setZoom(state.zoom - 0.15));
  getRequiredElement("fit-btn").addEventListener("click", fitPreviewToScreen);
  getRequiredElement("fullscreen-btn").addEventListener("click", openFullscreenPreview);
}

function bindUploadZone() {
  const zone = getRequiredElement("upload-zone");
  const input = getRequiredElement("reference-image");
  const removeButton = getRequiredElement("remove-upload-btn");

  input.addEventListener("change", () => {
    const file = input.files && input.files[0] ? input.files[0] : null;
    if (file) {
      selectUploadFile(file);
    }
  });

  removeButton.addEventListener("click", clearSelectedUpload);

  ["dragenter", "dragover"].forEach((eventName) => {
    zone.addEventListener(eventName, (event) => {
      event.preventDefault();
      zone.classList.add("is-dragging");
    });
  });

  ["dragleave", "drop"].forEach((eventName) => {
    zone.addEventListener(eventName, (event) => {
      event.preventDefault();
      if (eventName === "dragleave" && zone.contains(event.relatedTarget)) {
        return;
      }
      zone.classList.remove("is-dragging");
    });
  });

  zone.addEventListener("drop", (event) => {
    const file = event.dataTransfer && event.dataTransfer.files[0] ? event.dataTransfer.files[0] : null;
    if (file) {
      selectUploadFile(file);
    }
  });
}

function bindCodeControls() {
  getRequiredElement("copy-code-btn").addEventListener("click", (event) => {
    event.stopPropagation();
    copyTikzCode();
  });
  getRequiredElement("download-tex-btn").addEventListener("click", (event) => {
    event.stopPropagation();
    Download("tex");
  });
}

function bindDownloadControls() {
  document.querySelectorAll(".download-item").forEach((button) => {
    button.addEventListener("click", () => Download(button.dataset.asset));
  });
}

async function Generate(event) {
  if (event) {
    event.preventDefault();
  }

  const promptInput = getRequiredElement("diagram-prompt");
  const prompt = promptInput.value.trim();
  if (!prompt) {
    notify("Prompt required", "Describe the diagram before generating.", "error");
    promptInput.focus();
    return null;
  }

  state.currentPrompt = prompt;
  state.lastAction = { type: "generate", prompt };
  hideErrorPanel();
  setButtonLoading("generate-btn", true, "Generating");
  startWorkflow();

  try {
    const payload = await postJson("/generate", { prompt });
    applyGenerationPayload(payload, "generation", prompt);
    completeWorkflow();
    notify("Diagram generated", "PNG, PDF, and TikZ are ready.", "success");
    activateTab("preview");
    return payload;
  } catch (error) {
    failWorkflow(error);
    return null;
  } finally {
    setButtonLoading("generate-btn", false, "Generate Diagram");
  }
}

async function Upload(event) {
  if (event) {
    event.preventDefault();
  }

  const file = state.uploadedFile || getRequiredElement("reference-image").files[0];
  if (!file) {
    notify("No image selected", "Choose or drop a PNG or JPG before uploading.", "error");
    return null;
  }

  const validation = validateUploadFile(file);
  if (!validation.ok) {
    notify("Invalid image", validation.message, "error");
    return null;
  }

  setButtonLoading("upload-btn", true, "Uploading");
  setStatus("Uploading reference image...", "working", "Uploading");

  const formData = new FormData();
  formData.append("file", file);

  try {
    const payload = await request("/upload", {
      method: "POST",
      body: formData,
    });
    notify("Image uploaded", payload.message || payload.filename || "Reference image uploaded.", "success");
    setStatus("Reference image uploaded.", "complete", "Complete");
    return payload;
  } catch (error) {
    showRequestError(error, "Unable to upload the selected image.");
    return null;
  } finally {
    setButtonLoading("upload-btn", false, "Upload");
  }
}

async function Refine(event) {
  if (event) {
    event.preventDefault();
  }

  const instructionInput = getRequiredElement("refine-instruction");
  const instruction = instructionInput.value.trim();
  const currentTikz = getCurrentTikzCode();
  const prompt = state.currentPrompt || getRequiredElement("diagram-prompt").value.trim();

  if (!instruction) {
    notify("Instruction required", "Enter refinement instructions first.", "error");
    instructionInput.focus();
    return null;
  }

  if (!currentTikz) {
    notify("No TikZ yet", "Generate a diagram before refining.", "error");
    activateTab("code");
    return null;
  }

  state.lastAction = { type: "refine", prompt, instruction, tikz: currentTikz };
  hideErrorPanel();
  setButtonLoading("refine-btn", true, "Refining");
  startWorkflow();

  try {
    const payload = await postJson("/refine", {
      prompt,
      tikz: currentTikz,
      instruction,
    });
    applyGenerationPayload(payload, "refinement", prompt || instruction);
    completeWorkflow();
    notify("Diagram refined", "Updated preview and source are ready.", "success");
    activateTab("preview");
    return payload;
  } catch (error) {
    failWorkflow(error);
    return null;
  } finally {
    setButtonLoading("refine-btn", false, "Refine");
  }
}

async function Download(assetType = "tex") {
  const type = String(assetType || "tex").toLowerCase();
  if (type === "zip" && !state.downloads.zip) {
    notify("ZIP unavailable", "The backend has not provided a ZIP export for this result.", "error");
    return;
  }

  if (type === "tikz" || type === "tex") {
    if (!state.tikzCode) {
      notify("Nothing to download", "Generate a diagram before downloading source.", "error");
      return;
    }
  }

  if (type === "tikz") {
    downloadBlob(new Blob([`${state.tikzCode}\n`], { type: "text/plain;charset=utf-8" }), buildDownloadName("tikz"));
    notify("Downloaded TikZ", "Raw TikZ source saved.", "success");
    return;
  }

  const url = state.downloads[type];
  if (!url) {
    notify("Nothing to download", `Generate a diagram before downloading ${type.toUpperCase()}.`, "error");
    return;
  }

  try {
    const response = await fetch(toAbsoluteApiUrl(url));
    if (!response.ok) {
      throw new Error(`Download failed with status ${response.status}.`);
    }
    const blob = await response.blob();
    downloadBlob(blob, buildDownloadName(type));
    notify(`Downloaded ${type.toUpperCase()}`, "Export saved successfully.", "success");
  } catch (error) {
    showRequestError(error, `Unable to download ${type.toUpperCase()}.`);
  }
}

function ClearWorkspace(event) {
  if (event) {
    event.preventDefault();
  }

  getRequiredElement("diagram-prompt").value = "";
  getRequiredElement("refine-instruction").value = "";
  clearSelectedUpload();
  clearTimers();

  state.generation = null;
  state.refinement = null;
  state.tikzCode = "";
  state.currentPrompt = "";
  state.lastAction = null;
  state.zoom = 1;
  state.downloads = { pdf: "", png: "", tex: "", zip: "" };

  hideErrorPanel();
  updateTikzOutput("");
  updatePreview(null);
  updatePdfPreview(null);
  updateDownloads(null);
  setWorkflowIdle();
  setStatus("Ready for input.", "ready", "Ready");
  notify("Workspace cleared", "Prompt, preview, and source were reset.", "success");
}

async function retryLastAction() {
  if (!state.lastAction) {
    notify("Nothing to retry", "Generate or refine a diagram first.", "error");
    return;
  }

  if (state.lastAction.type === "refine") {
    getRequiredElement("refine-instruction").value = state.lastAction.instruction || "";
    return Refine();
  }

  if (state.lastAction.prompt) {
    getRequiredElement("diagram-prompt").value = state.lastAction.prompt;
  }
  return Generate();
}

async function postJson(path, payload) {
  return request(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(payload),
  });
}

async function request(path, options = {}) {
  const response = await fetch(toAbsoluteApiUrl(path), options);
  const payload = await parseJsonResponse(response);
  if (payload.success === false) {
    const message = [getBackendMessage(payload), payload.details]
      .filter((part) => typeof part === "string" && part.trim())
      .join(" ");
    throw new RequestError(message || "The backend could not complete the request.", payload);
  }
  return payload;
}

async function parseJsonResponse(response) {
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : { message: await response.text() };

  if (!response.ok) {
    const message = getBackendMessage(payload) || `Request failed with status ${response.status}.`;
    throw new RequestError(message, payload);
  }

  return payload;
}

function applyGenerationPayload(payload, targetKey, prompt) {
  if (!payload || typeof payload !== "object") {
    throw new RequestError("Backend response was empty.", payload);
  }

  if (typeof payload.tikz !== "string" || !payload.tikz.trim()) {
    throw new RequestError("Backend response did not include TikZ code.", payload);
  }

  state[targetKey] = payload;
  state.tikzCode = payload.tikz.trim();
  state.downloads = {
    pdf: payload.pdf || "",
    png: payload.png || "",
    tex: payload.tex || "",
    zip: payload.zip || "",
  };

  updateTikzOutput(state.tikzCode);
  updatePreview(payload);
  updatePdfPreview(payload);
  updateDownloads(payload);
  addHistoryItem(prompt, payload);
}

function selectUploadFile(file) {
  const validation = validateUploadFile(file);
  if (!validation.ok) {
    notify("Invalid image", validation.message, "error");
    return;
  }

  clearUploadPreviewUrl();
  state.uploadedFile = file;
  state.uploadPreviewUrl = URL.createObjectURL(file);

  const preview = getRequiredElement("upload-preview");
  const image = getRequiredElement("upload-thumb");
  image.src = state.uploadPreviewUrl;
  getRequiredElement("upload-file-name").textContent = file.name;
  getRequiredElement("upload-file-meta").textContent = formatBytes(file.size);
  preview.hidden = false;
  setStatus(`Ready to upload ${file.name}.`, "ready", "Ready");
}

function validateUploadFile(file) {
  const extension = file.name.split(".").pop().toLowerCase();
  if (!ALLOWED_UPLOAD_TYPES.has(extension)) {
    return { ok: false, message: "Only PNG, JPG, and JPEG files are supported." };
  }
  if (file.size <= 0) {
    return { ok: false, message: "The selected file is empty." };
  }
  if (file.size > MAX_UPLOAD_SIZE) {
    return { ok: false, message: "The selected file is larger than 10 MB." };
  }
  return { ok: true, message: "" };
}

function clearSelectedUpload() {
  getRequiredElement("reference-image").value = "";
  state.uploadedFile = null;
  clearUploadPreviewUrl();
  getRequiredElement("upload-preview").hidden = true;
  getRequiredElement("upload-thumb").removeAttribute("src");
}

function clearUploadPreviewUrl() {
  if (state.uploadPreviewUrl) {
    URL.revokeObjectURL(state.uploadPreviewUrl);
    state.uploadPreviewUrl = "";
  }
}

function updateTikzOutput(tikzCode) {
  const output = getRequiredElement("tikz-output");
  const source = tikzCode || EMPTY_TIKZ_TEXT;
  output.innerHTML = source.split("\n").map((line, index) => {
    return `<span class="code-line"><span class="line-number">${index + 1}</span><span class="line-code">${highlightTikz(line) || " "}</span></span>`;
  }).join("");
}

function updatePreview(payload) {
  const preview = getRequiredElement("diagram-preview");
  preview.replaceChildren();
  state.zoom = 1;
  updateZoomLabel();

  const imageUrl = payload && typeof payload.png === "string" ? payload.png.trim() : "";
  if (!imageUrl) {
    const message = document.createElement("p");
    message.textContent = "Generated PNG preview will appear here.";
    preview.appendChild(message);
    return;
  }

  const image = document.createElement("img");
  image.id = "preview-image";
  image.src = toAbsoluteApiUrl(imageUrl);
  image.alt = "Generated diagram preview";
  image.loading = "lazy";
  image.decoding = "async";
  preview.appendChild(image);
  applyZoom();
}

function updatePdfPreview(payload) {
  const pdfPreview = getRequiredElement("pdf-preview");
  pdfPreview.replaceChildren();
  const pdfUrl = payload && typeof payload.pdf === "string" ? payload.pdf.trim() : "";

  if (!pdfUrl) {
    const message = document.createElement("p");
    message.textContent = "Compiled PDF will appear here.";
    pdfPreview.appendChild(message);
    return;
  }

  const frame = document.createElement("iframe");
  frame.src = toAbsoluteApiUrl(pdfUrl);
  frame.title = "Compiled PDF preview";
  pdfPreview.appendChild(frame);
}

function updateDownloads(payload) {
  document.querySelectorAll(".download-item").forEach((button) => {
    const type = button.dataset.asset;
    const hasAsset = Boolean(payload && (payload[type] || (type === "tex" && state.tikzCode)));
    if (type === "zip" && !state.downloads.zip) {
      button.disabled = true;
      button.setAttribute("aria-disabled", "true");
      return;
    }
    button.disabled = !hasAsset;
    button.setAttribute("aria-disabled", String(!hasAsset));
  });
}

function activateTab(tabName) {
  if (!tabName) {
    return;
  }

  document.querySelectorAll("[data-tab]").forEach((button) => {
    const active = button.dataset.tab === tabName;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-selected", String(active));
  });

  document.querySelectorAll(".results > .tab-panel").forEach((panel) => {
    const active = panel.id === `tab-${tabName}`;
    panel.classList.toggle("is-active", active);
    panel.hidden = !active;
  });
}

function activatePreviewTab(tabName) {
  const shell = getRequiredElement("preview-shell");
  shell.classList.toggle("is-split", tabName === "split");

  document.querySelectorAll("[data-preview-tab]").forEach((button) => {
    const active = button.dataset.previewTab === tabName;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-selected", String(active));
  });

  document.querySelectorAll(".preview-pane").forEach((pane) => {
    pane.classList.remove("is-active");
  });

  if (tabName === "png") {
    getRequiredElement("png-pane").classList.add("is-active");
  } else if (tabName === "pdf") {
    getRequiredElement("pdf-pane").classList.add("is-active");
  }
}

function handleTabKeyboard(event) {
  if (!["ArrowLeft", "ArrowRight"].includes(event.key)) {
    return;
  }

  const tabs = Array.from(document.querySelectorAll("[data-tab]"));
  const index = tabs.indexOf(event.currentTarget);
  const nextIndex = event.key === "ArrowRight"
    ? (index + 1) % tabs.length
    : (index - 1 + tabs.length) % tabs.length;
  tabs[nextIndex].focus();
  activateTab(tabs[nextIndex].dataset.tab);
}

function handlePreviewTabKeyboard(event) {
  if (!["ArrowLeft", "ArrowRight"].includes(event.key)) {
    return;
  }

  const tabs = Array.from(document.querySelectorAll("[data-preview-tab]"));
  const index = tabs.indexOf(event.currentTarget);
  const nextIndex = event.key === "ArrowRight"
    ? (index + 1) % tabs.length
    : (index - 1 + tabs.length) % tabs.length;
  tabs[nextIndex].focus();
  activatePreviewTab(tabs[nextIndex].dataset.previewTab);
}

function setZoom(nextZoom) {
  state.zoom = Math.min(2.5, Math.max(0.35, Number(nextZoom.toFixed(2))));
  applyZoom();
}

function applyZoom() {
  const image = document.getElementById("preview-image");
  if (image) {
    image.style.transform = `scale(${state.zoom})`;
  }
  updateZoomLabel();
}

function fitPreviewToScreen() {
  const frame = getRequiredElement("diagram-preview");
  const image = document.getElementById("preview-image");
  if (!image || !image.naturalWidth || !image.naturalHeight) {
    setZoom(1);
    return;
  }

  const widthRatio = Math.max(0.35, (frame.clientWidth - 48) / image.naturalWidth);
  const heightRatio = Math.max(0.35, (frame.clientHeight - 48) / image.naturalHeight);
  setZoom(Math.min(1, widthRatio, heightRatio));
}

function openFullscreenPreview() {
  const shell = getRequiredElement("preview-shell");
  if (shell.requestFullscreen) {
    shell.requestFullscreen();
  } else {
    notify("Fullscreen unavailable", "Your browser does not support fullscreen preview.", "error");
  }
}

function updateZoomLabel() {
  getRequiredElement("zoom-level").textContent = `${Math.round(state.zoom * 100)}%`;
}

function startWorkflow() {
  clearTimers();
  setStatus("Understanding prompt...", "working", "Working");
  setWorkflowStep(0);

  WORKFLOW_STEPS.slice(1, -1).forEach((_, index) => {
    const timer = window.setTimeout(() => setWorkflowStep(index + 1), 650 + index * 700);
    state.timers.push(timer);
  });
}

function completeWorkflow() {
  clearTimers();
  setWorkflowStep(WORKFLOW_STEPS.length - 1);
  setStatus("Complete.", "complete", "Complete");
}

function failWorkflow(error) {
  clearTimers();
  setStatus("Generation failed.", "failed", "Failed");
  showRequestError(error, "Unable to complete the request.");
}

function setWorkflowIdle() {
  document.querySelectorAll("#progress-steps li").forEach((item) => {
    item.classList.remove("is-active", "is-complete");
  });
}

function setWorkflowStep(activeIndex) {
  document.querySelectorAll("#progress-steps li").forEach((item, index) => {
    item.classList.toggle("is-complete", index < activeIndex);
    item.classList.toggle("is-active", index === activeIndex);
  });
}

function clearTimers() {
  state.timers.forEach((timer) => window.clearTimeout(timer));
  state.timers = [];
}

function setStatus(message, status = "ready", badge = "Ready") {
  getRequiredElement("status-line").textContent = message;
  const statusBadge = getRequiredElement("status-badge");
  statusBadge.textContent = badge;
  statusBadge.dataset.status = status;
}

function setButtonLoading(buttonId, loading, label) {
  const button = getRequiredElement(buttonId);
  const iconClass = {
    "generate-btn": "bi-lightning-charge-fill",
    "upload-btn": "bi-upload",
    "refine-btn": "bi-magic",
  }[buttonId] || "bi-circle";
  button.disabled = loading;
  button.setAttribute("aria-busy", String(loading));
  button.innerHTML = `<i class="bi ${iconClass}" aria-hidden="true"></i>${escapeHtml(label)}`;
}

function showRequestError(error, fallbackMessage) {
  const payload = error instanceof RequestError ? error.payload : null;
  const message = friendlyError(error instanceof Error && error.message ? error.message : fallbackMessage);
  notify("Request failed", message, "error");
  setStatus(message, "failed", "Failed");
  showErrorPanel(message, payload);
}

function showErrorPanel(message, payload = null) {
  getRequiredElement("error-panel").hidden = false;
  getRequiredElement("compiler-message").textContent = payload && payload.details ? payload.details : message;
  getRequiredElement("error-tikz-source").textContent = payload && payload.tikz ? payload.tikz : state.tikzCode || EMPTY_TIKZ_TEXT;
}

function hideErrorPanel() {
  getRequiredElement("error-panel").hidden = true;
  getRequiredElement("compiler-message").textContent = "";
  getRequiredElement("error-tikz-source").textContent = "";
}

async function copyTikzCode() {
  if (!state.tikzCode) {
    notify("Nothing to copy", "Generate a diagram before copying TikZ.", "error");
    return;
  }

  try {
    await navigator.clipboard.writeText(state.tikzCode);
    notify("Copied", "TikZ source copied to clipboard.", "success");
  } catch (_error) {
    notify("Copy failed", "Clipboard access is unavailable in this browser.", "error");
  }
}

function addHistoryItem(prompt, payload) {
  const item = {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    prompt: prompt || state.currentPrompt || "Untitled diagram",
    timestamp: new Date().toLocaleString([], { dateStyle: "medium", timeStyle: "short" }),
    payload,
    tikz: payload.tikz,
    thumbnail: payload.png ? toAbsoluteApiUrl(payload.png) : "",
  };
  state.history.unshift(item);
  state.history = state.history.slice(0, 10);
  renderHistory();
}

function renderHistory() {
  const list = getRequiredElement("history-list");
  list.replaceChildren();

  if (!state.history.length) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "Generated diagrams will appear here.";
    list.appendChild(empty);
    return;
  }

  state.history.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "history-card";
    button.setAttribute("aria-label", `Reopen result from ${item.timestamp}`);
    button.addEventListener("click", () => reopenHistoryItem(item));

    const thumb = item.thumbnail
      ? `<img src="${escapeHtml(item.thumbnail)}" alt="">`
      : '<span class="history-thumb"><i class="bi bi-diagram-3" aria-hidden="true"></i></span>';

    button.innerHTML = `${thumb}<span><strong>${escapeHtml(item.prompt)}</strong><small>${escapeHtml(item.timestamp)}</small></span>`;
    list.appendChild(button);
  });
}

function reopenHistoryItem(item) {
  state.generation = item.payload;
  state.tikzCode = item.tikz;
  state.currentPrompt = item.prompt;
  getRequiredElement("diagram-prompt").value = item.prompt;
  updateTikzOutput(item.tikz);
  updatePreview(item.payload);
  updatePdfPreview(item.payload);
  updateDownloads(item.payload);
  activateTab("preview");
  notify("Result reopened", "Session history result restored.", "success");
}

function getCurrentTikzCode() {
  return state.tikzCode || "";
}

function getBackendMessage(payload) {
  if (!payload || typeof payload !== "object") {
    return "";
  }
  if (typeof payload.error === "string" && payload.error.trim()) {
    return payload.error.trim();
  }
  if (typeof payload.message === "string" && payload.message.trim()) {
    return payload.message.trim();
  }
  return "";
}

function friendlyError(message) {
  return String(message || "Something went wrong. Please try again.").replace(/\s+/g, " ").trim();
}

function highlightTikz(line) {
  return escapeHtml(line)
    .replace(/(%.*)$/g, '<span class="tok-comment">$1</span>')
    .replace(/(\\(?:begin|end)\{[^}]+\})/g, '<span class="tok-env">$1</span>')
    .replace(/(\\[a-zA-Z]+)/g, '<span class="tok-command">$1</span>')
    .replace(/(\[[^\]]+\])/g, '<span class="tok-option">$1</span>');
}

function notify(title, message, type = "success") {
  const region = getRequiredElement("toast-region");
  const toast = document.createElement("article");
  toast.className = "toast";
  toast.dataset.type = type;
  toast.setAttribute("role", type === "error" ? "alert" : "status");
  const icon = type === "error" ? "bi-exclamation-circle" : "bi-check-circle";
  toast.innerHTML = `
    <i class="bi ${icon}" aria-hidden="true"></i>
    <div><strong>${escapeHtml(title)}</strong><p>${escapeHtml(message)}</p></div>
    <button type="button" class="icon-button" aria-label="Dismiss notification"><i class="bi bi-x" aria-hidden="true"></i></button>
  `;
  toast.querySelector("button").addEventListener("click", () => removeToast(toast));
  region.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add("is-visible"));
  window.setTimeout(() => removeToast(toast), 5200);
}

function removeToast(toast) {
  toast.classList.remove("is-visible");
  window.setTimeout(() => toast.remove(), 240);
}

function downloadBlob(blob, filename) {
  const objectUrl = URL.createObjectURL(blob);
  const temporaryLink = document.createElement("a");
  temporaryLink.href = objectUrl;
  temporaryLink.download = filename;
  temporaryLink.style.display = "none";
  document.body.appendChild(temporaryLink);
  temporaryLink.click();
  temporaryLink.remove();
  URL.revokeObjectURL(objectUrl);
}

function buildDownloadName(assetType) {
  const activePayload = state.refinement || state.generation || {};
  const jobId = activePayload.job_id || "diagram";
  if (assetType === "tikz") {
    return `${jobId}.tikz`;
  }
  return `${jobId}.${assetType}`;
}

function formatBytes(bytes) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function toAbsoluteApiUrl(pathOrUrl) {
  if (!pathOrUrl) {
    return "";
  }
  if (/^https?:\/\//i.test(pathOrUrl)) {
    return pathOrUrl;
  }
  const path = pathOrUrl.startsWith("/") ? pathOrUrl : `/${pathOrUrl}`;
  return `${API_BASE}${path}`;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function getRequiredElement(id) {
  const element = document.getElementById(id);
  if (!element) {
    throw new Error(`Missing required element: #${id}`);
  }
  return element;
}

window.Generate = Generate;
window.Upload = Upload;
window.Refine = Refine;
window.Download = Download;
