"use strict";
const $ = id => document.getElementById(id);
let selectedFile = null;
let polling = null;
let activeJob = null;
let localPreview = null;
let maxBytes = 100 * 1024 * 1024;
let running = false;
let engineHealth = null;
const engineLabels = {auto: "Automatico", xiaomi: "Xiaomi OCR 0", minicpm: "MiniCPM OCR 1.0", vision: "Apple Vision", tesseract: "Tesseract"};

function showEngineStatus() {
  const name = $("engine").value;
  const status = $("engine-status");
  status.classList.remove("unavailable");
  if (!engineHealth) return;
  if (name === "auto") {
    const available = Object.keys(engineLabels).filter(key => engineHealth[key]?.available);
    status.textContent = available.length ? "OCR locali disponibili: " + available.map(key => engineLabels[key]).join(", ") + ". Il testo nativo non richiede OCR." : "Nessun OCR disponibile. I PDF nativi restano convertibili; per le scansioni serve un motore locale.";
    return;
  }
  const health = engineHealth[name];
  if (!health) { status.textContent = "Stato del motore non disponibile."; return; }
  if (health.available) {
    status.textContent = engineLabels[name] + " disponibile" + (health.endpoint ? " su " + health.endpoint : " sul dispositivo") + ".";
  } else {
    status.classList.add("unavailable");
    status.textContent = engineLabels[name] + " non disponibile. " + (health.reason || "Controlla il runtime locale.") + " Non verrà sostituito automaticamente se lo selezioni esplicitamente.";
  }
}
async function refreshEngines() {
  $("refresh-engines").disabled = true;
  $("engine-status").textContent = "Verifica dei motori locali in corso…";
  try {
    const response = await jsonResponse(await fetch("/api/engines"));
    engineHealth = response.engines;
    for (const option of $("engine").options) {
      option.textContent = engineLabels[option.value] + (engineHealth[option.value]?.available === false ? " · non disponibile" : "");
    }
    showEngineStatus();
  } catch {
    engineHealth = null;
    $("engine-status").textContent = "Impossibile verificare i motori locali. Ricontrolla prima di usare OCR su scansioni.";
  } finally { $("refresh-engines").disabled = false; }
}

function announce(text) { $("announcements").textContent = text; }
function showError(text) { $("error").textContent = text; $("error").hidden = false; announce(text); }
function busy(value) {
  running = value;
  for (const name of ["file", "mode", "engine", "language", "validate_visual", "searchable_pdf", "optimize_layout", "submit"]) $(name).disabled = value;
  $("submit").firstChild.textContent = value ? "Conversione in corso " : "Converti documento ";
}
function selectTab(name) {
  for (const key of ["source", "report"]) {
    $("tab-" + key).setAttribute("aria-selected", String(name === key));
    $("panel-" + key).hidden = name !== key;
  }
}
function useFile(file) {
  if (!file || running) return;
  selectedFile = null;
  $("error").hidden = true;
  if (!file.name.toLowerCase().endsWith(".pdf")) { showError("Seleziona un file PDF."); return; }
  if (file.size > maxBytes) { showError("Il PDF supera il limite di dimensione indicato."); return; }
  selectedFile = file;
  $("file-label").textContent = file.name;
  $("file-description").textContent = (file.size / 1024 / 1024).toFixed(2) + " MB · seleziona per cambiare";
  if (localPreview) URL.revokeObjectURL(localPreview);
  localPreview = URL.createObjectURL(file);
  $("source-preview").src = localPreview;
  $("source-preview").hidden = false;
  $("empty-state").hidden = true;
  $("downloads").hidden = true;
  $("tab-report").disabled = true;
  selectTab("source");
}
$("file").addEventListener("change", event => useFile(event.target.files[0]));
for (const name of ["dragenter", "dragover"]) $("dropzone").addEventListener(name, event => { event.preventDefault(); $("dropzone").classList.add("dragover"); });
for (const name of ["dragleave", "drop"]) $("dropzone").addEventListener(name, event => { event.preventDefault(); $("dropzone").classList.remove("dragover"); });
$("dropzone").addEventListener("drop", event => { const file = event.dataTransfer.files[0]; if (file) { const data = new DataTransfer(); data.items.add(file); $("file").files = data.files; useFile(file); } });
$("mode").addEventListener("change", () => { $("mode-note").textContent = $("mode").value === "visual" ? "Le pagine diventano immagini: il testo nel Word non è modificabile." : "La struttura resta modificabile; Word può ricalcolare l'impaginazione."; });
$("engine").addEventListener("change", showEngineStatus);
$("refresh-engines").addEventListener("click", refreshEngines);
$("tab-source").addEventListener("click", () => selectTab("source"));
$("tab-report").addEventListener("click", () => selectTab("report"));

async function jsonResponse(response) {
  let data;
  try { data = await response.json(); } catch { throw new Error("Il server ha restituito una risposta non valida."); }
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Richiesta non riuscita.");
  return data;
}
function finish(job) {
  busy(false);
  if (job.status === "failed") { showError(job.error || "Conversione non riuscita."); return; }
  $("downloads").hidden = false;
  for (const kind of ["docx", "report", "json", "model", "searchable"]) {
    const link = $("download-" + kind);
    link.hidden = !job.files[kind];
    if (job.files[kind]) link.href = job.files[kind] + "?download=true";
  }
  if (job.files.report) {
    $("report-preview").src = job.files.report;
    $("report-preview").hidden = false;
    $("tab-report").disabled = false;
    selectTab("report");
  }
  $("progress-detail").textContent = "Scarica i file prima di chiudere il server: la cartella temporanea viene eliminata allo spegnimento.";
  announce("Conversione completata. Puoi scaricare il documento Word e il rapporto qualità.");
}
async function poll() {
  try {
    const job = await jsonResponse(await fetch("/api/jobs/" + activeJob));
    $("progress").value = job.progress;
    $("progress-value").textContent = Math.round(job.progress * 100) + "%";
    $("progress-message").textContent = job.message;
    if (["complete", "failed"].includes(job.status)) { finish(job); return; }
    polling = setTimeout(poll, 800);
  } catch (error) {
    busy(false);
    showError("Connessione interrotta. " + error.message);
  }
}
$("convert-form").addEventListener("submit", async event => {
  event.preventDefault();
  if (!selectedFile) { showError("Seleziona prima un PDF."); return; }
  if (polling) clearTimeout(polling);
  $("error").hidden = true;
  $("downloads").hidden = true;
  $("progress-section").hidden = false;
  $("progress").value = 0;
  $("progress-value").textContent = "0%";
  $("progress-message").textContent = "Caricamento locale del PDF";
  $("progress-detail").textContent = "Puoi mantenere aperta questa pagina durante l'elaborazione.";
  busy(true);
  const body = new FormData();
  body.append("file", selectedFile);
  for (const name of ["engine", "mode", "language"]) body.append(name, $(name).value);
  for (const name of ["validate_visual", "searchable_pdf", "optimize_layout"]) body.append(name, String($(name).checked));
  try {
    const job = await jsonResponse(await fetch("/api/jobs", { method: "POST", body }));
    activeJob = job.id;
    $("source-preview").src = job.files.input;
    $("source-preview").hidden = false;
    $("empty-state").hidden = true;
    $("preview-caption").textContent = job.filename;
    selectTab("source");
    announce("Conversione avviata.");
    poll();
  } catch (error) { busy(false); showError(error.message); }
});
fetch("/api/settings").then(jsonResponse).then(settings => {
  maxBytes = settings.max_file_mb * 1024 * 1024;
  $("limits").textContent = "Fino a " + settings.max_file_mb + " MB · " + settings.max_pages + " pagine";
  for (const name of ["engine", "mode", "language"]) if ([...$(name).options].some(option => option.value === settings[name])) $(name).value = settings[name];
  $("mode").dispatchEvent(new Event("change"));
  showEngineStatus();
}).catch(() => { $("limits").textContent = "Impossibile leggere i limiti del server."; });
refreshEngines();
