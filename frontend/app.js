const $ = (id) => document.getElementById(id);
const api = async (path, opts={}) => { const r = await fetch(path, opts); if (!r.ok) throw new Error(await r.text()); return r.json(); };
document.querySelectorAll("nav button").forEach(b => {
  b.onclick = () => {
    document.querySelectorAll("nav button").forEach(x=>x.classList.remove("active"));
    document.querySelectorAll(".tab").forEach(x=>x.classList.remove("active"));
    b.classList.add("active");
    document.getElementById("tab-"+b.dataset.tab).classList.add("active");
    loadTab(b.dataset.tab);
  };
});
async function loadTab(t) {
  if (t==="memory") loadMemory();
  if (t==="library") loadDocs();
  if (t==="learn") loadLearn();
  if (t==="about") loadAbout();
}
async function refreshStatus() {
  try {
    const s = await api("/api/status");
    $("status").textContent = `v${s.version} · ${s.nn.intent_labels[s.nn.intents[0]]?"" :""} intents:${s.nn.intents.length} facts:${s.facts} docs:${s.docs}`;
  } catch (e) { $("status").textContent = "offline"; }
}
refreshStatus();

// Chat
$("send").onclick = async () => {
  const msg = $("msg").value.trim(); if (!msg) return;
  $("msg").value = "";
  appendMsg("user", msg);
  const div = appendMsg("assistant", "");
  try {
    const r = await fetch("/api/chat", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({message:msg})});
    const reader = r.body.getReader(); const dec = new TextDecoder(); let buf="";
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      buf += dec.decode(value, {stream:true});
      const lines = buf.split("\n"); buf = lines.pop();
      for (const line of lines) {
        if (!line.startsWith("data:")) continue;
        try { const j = JSON.parse(line.slice(5)); if (j.token) div.textContent += j.token; } catch {}
      }
    }
  } catch (e) { div.textContent = "Fehler: " + e.message; }
  if (ttsOn) {
    const text = div.textContent;
    fetch("/api/voice/tts", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({text})})
      .then(r => r.blob()).then(b => { const a = new Audio(URL.createObjectURL(b)); a.play(); })
      .catch(e => console.error(e));
  }
  refreshStatus && refreshStatus();
};
function appendMsg(role, text) {
  const d = document.createElement("div"); d.className = "msg "+role;
  d.innerHTML = `<div class="role">${role}</div><div class="content">${escapeHtml(text)}</div>`;
  $("chatlog").appendChild(d); $("chatlog").scrollTop = $("chatlog").scrollHeight;
  return d.querySelector(".content");
}
function escapeHtml(s){ return s.replace(/[&<>"']/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c])); }

// Memory
async function loadMemory() {
  const d = await api("/api/memory");
  $("factList").innerHTML = d.facts.map(f => `<div class="card">#${f.id} ${escapeHtml(f.text)} <button class="secondary" onclick="delFact(${f.id})">Löschen</button></div>`).join("");
}
$("factAdd").onclick = async () => {
  await api("/api/memory", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({text:$("factText").value})});
  $("factText").value=""; loadMemory();
};
window.delFact = async (id) => { await api(`/api/memory/${id}`, {method:"DELETE"}); loadMemory(); };

// Library
async function loadDocs() {
  const d = await api("/api/docs");
  $("docList").innerHTML = d.documents.map(x => `<div class="card">#${x.id} ${escapeHtml(x.name)} <span class="meta">${x.chunks} chunks</span> <button class="secondary" onclick="delDoc(${x.id})">Löschen</button></div>`).join("");
}
$("uploadBtn").onclick = async () => {
  const f = $("fileInput").files[0]; if (!f) return;
  const fd = new FormData(); fd.append("file", f);
  const r = await fetch("/api/docs/upload", {method:"POST", body: fd});
  const j = await r.json();
  alert("Importiert: " + j.chunks + " Abschnitte");
  loadDocs();
};
$("docSearch").onclick = async () => {
  const d = await api("/api/docs/search?q="+encodeURIComponent($("docQuery").value));
  $("docResults").innerHTML = d.results.map(r=>`<div class="card"><b>${escapeHtml(r.name)}</b><br>${escapeHtml(r.content.slice(0,300))}</div>`).join("");
};
window.delDoc = async (id) => { await api(`/api/docs/${id}`, {method:"DELETE"}); loadDocs(); };

// Learn
async function loadLearn() {
  const d = await api("/api/training/examples");
  $("exList").innerHTML = d.examples.map(e => `<div class="card">${escapeHtml(e.text)} <span class="meta">→ ${e.label}</span></div>`).join("");
  const info = await api("/api/training/info");
  $("trainInfo").textContent = JSON.stringify(info, null, 2);
}
$("exAdd").onclick = async () => {
  await api("/api/training/examples", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({text:$("exText").value, label:$("exLabel").value})});
  $("exText").value=""; loadLearn();
};
$("trainBtn").onclick = async () => {
  $("trainStatus").textContent = "Training…";
  const r = await api("/api/training/run?epochs=20", {method:"POST"});
  $("trainStatus").textContent = `Fertig: acc=${(r.accuracy*100).toFixed(1)}% loss=${r.final_loss.toFixed(4)}`;
  loadLearn();
};

// Voice
let voiceOn = false;
let ttsOn = false;
let recognition = null;
$("voiceToggle").onclick = () => {
  voiceOn = !voiceOn;
  $("voiceToggle").textContent = voiceOn ? "🎤 Voice an" : "🎤 Voice aus";
  if (voiceOn) startVoice();
  else stopVoice();
};
$("speakToggle").onclick = () => {
  ttsOn = !ttsOn;
  $("speakToggle").textContent = ttsOn ? "🔊 TTS an" : "🔊 TTS aus";
};
function startVoice() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { $("voiceStatus").textContent = "Browser unterstützt keine Spracherkennung. Nutze Upload."; return; }
  recognition = new SR();
  recognition.lang = "de-DE";
  recognition.continuous = false;
  recognition.onresult = (e) => {
    const t = e.results[0][0].transcript;
    $("msg").value = t;
    $("send").click();
  };
  recognition.onend = () => { if (voiceOn) try { recognition.start(); } catch {} };
  try { recognition.start(); $("voiceStatus").textContent = "Höre zu…"; } catch (e) { $("voiceStatus").textContent = "Fehler: " + e.message; }
}
function stopVoice() {
  if (recognition) try { recognition.stop(); } catch {}
  recognition = null;
  $("voiceStatus").textContent = "";
}
// TTS after assistant reply: hook into send flow by overriding appendMsg? Simpler: poll last assistant msg.
const origAppend = appendMsg;
// We'll speak in send handler after stream done: add below by monkeypatching send click already; instead add speak call in a wrapper.
// (handled in send onclick via post-processing)

// Sleep
$("sleepBtn").onclick = async () => {
  $("sleepStatus").textContent = "Schlaeft…";
  try {
    const r = await api("/api/sleep?epochs=20&replay=2", {method:"POST"});
    $("sleepStatus").textContent = "Fertig: acc=" + (r.result.accuracy*100).toFixed(1) + "%";
    $("trainInfo").textContent = JSON.stringify(r, null, 2);
  } catch (e) { $("sleepStatus").textContent = "Fehler: " + e.message; }
};

// Memory export/import/reset
$("memExport").onclick = async () => {
  const d = await api("/api/memory/export");
  const blob = new Blob([JSON.stringify(d, null, 2)], {type:"application/json"});
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "baybe_memory.json"; a.click();
};
$("memImport").onclick = async () => {
  const f = $("memImportFile").files[0]; if (!f) return;
  const text = await f.text();
  const d = JSON.parse(text);
  const r = await api("/api/memory/import", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(d)});
  alert("Importiert: " + r.imported);
  loadMemory();
};
$("memReset").onclick = async () => {
  if (!confirm("Alles löschen (Gedächtnis, Dokumente, Modell)?")) return;
  await api("/api/memory/reset", {method:"POST"});
  alert("Reset done");
  loadMemory(); loadDocs(); loadLearn(); loadAbout();
};

// Identity export/import
$("idExport").onclick = async () => {
  window.open("/api/identity/export", "_blank");
};
$("idImport").onclick = async () => {
  const f = $("idImportFile").files[0]; if (!f) return;
  const fd = new FormData(); fd.append("file", f);
  const r = await fetch("/api/identity/restore", {method:"POST", body: fd});
  const j = await r.json();
  alert("Wiederhergestellt: " + j.name);
  loadAbout();
};

// About
async function loadAbout() {
  const s = await api("/api/status");
  $("aboutBox").innerHTML = `<b>${s.app}</b> v${s.version}<br>${s.tagline}<br><br>
    <b>Neuronales Netz:</b> ${s.nn.vocab_size} Wörter, ${s.nn.examples} Beispiele<br>
    Trainiert: ${s.nn.trained_at || "noch nie"}<br>
    Fakten im Gedächtnis: ${s.facts}<br>
    Dokumente: ${s.docs}<br><br>
    <b>Schutz:</b> Gewaltanleitungen, Missbrauch, Drohungen werden abgelehnt.<br>
    <b>Offline:</b> Läuft vollständig lokal. Kein LLM, keine Cloud.`;
  // brain status
  try {
    const b = await api("/api/brain/status");
    $("brainToggle").checked = b.enabled;
    $("brainStatus").textContent = b.available ? ("verfügbar: " + b.models.join(", ")) : "Ollama nicht erreichbar";
    $("brainModel").innerHTML = b.models.map(m => `<option ${m===b.model?"selected":""}>${m}</option>`).join("");
    if (b.model) $("brainModel").value = b.model;
  } catch (e) { $("brainStatus").textContent = "Fehler"; }
}
$("brainSave").onclick = async () => {
  await api("/api/brain/toggle?enabled=" + $("brainToggle").checked, {method:"POST"});
  if ($("brainModel").value) await api("/api/brain/model?model=" + encodeURIComponent($("brainModel").value), {method:"POST"});
  $("brainStatus").textContent = "gespeichert";
};
PY
echo done