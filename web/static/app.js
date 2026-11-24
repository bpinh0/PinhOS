(() => {
  const $ = (id) => document.getElementById(id);
  const state = { cwd: "", selected: null, openFile: null, dirty: false, busy: 0 };
  const logs = ["[SYSTEM] PinhOS WebPortal Studio ready."];

  function log(msg, tag = "INFO") {
    const line = `[${tag}] ${new Date().toLocaleTimeString()} ${msg}`;
    logs.push(line);
    if (logs.length > 80) logs.shift();
    const txt = logs.join("\n") + "\nPinhOS> _";
    $("term-log").textContent = txt;
    $("term-log").scrollTop = $("term-log").scrollHeight;
    $("full-log").textContent = txt;
    $("full-log").scrollTop = $("full-log").scrollHeight;
  }

  function fmtSize(n) { return n < 1024 ? n + "B" : (n / 1024).toFixed(1) + "K"; }
  function setDirty(v) { state.dirty = !!v; $("dirty-dot").classList.toggle("hidden", !state.dirty); }
  function updateLines() {
    const n = $("code-area").value.split("\n").length;
    let s = "";
    for (let i = 1; i <= n; i++) s += i + "\n";
    $("line-nums").textContent = s;
  }

  function showTab(name) {
    document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("hidden", p.id !== "tab-" + name));
  }
  document.querySelectorAll(".tab").forEach((b) => (b.onclick = () => showTab(b.dataset.tab)));

  function getToken(forcePrompt = false) {
    let t = forcePrompt ? "" : (sessionStorage.getItem("pinhos_token") || "");
    if (!t) {
      t = (prompt("Enter PinhOS WebPortal Token (shown on PicoCalc):") || "").trim();
      if (t) sessionStorage.setItem("pinhos_token", t);
    }
    return t;
  }

  async function apiFetch(url, opts = {}) {
    const needsTok = url.startsWith("/api/") || ((opts.method || "GET").toUpperCase() !== "GET");
    const runFetch = async (forcePrompt) => {
      const hdrs = Object.assign({}, opts.headers || {});
      if (needsTok) {
        const tok = getToken(forcePrompt);
        if (tok) hdrs["X-PinhOS-Token"] = tok;
      }
      return await fetch(url, Object.assign({}, opts, { headers: hdrs }));
    };
    let res = await runFetch(false);
    if (res.status === 401 && needsTok) {
      sessionStorage.removeItem("pinhos_token");
      res = await runFetch(true);
    }
    return res;
  }

  async function apiJson(url, opts = {}) {
    state.busy++;
    try {
      const res = await apiFetch(url, opts);
      const data = await res.json();
      if (!res.ok) throw new Error((data && data.error) || `HTTP ${res.status}`);
      return data;
    } finally {
      state.busy = Math.max(0, state.busy - 1);
    }
  }

  async function pollStatus(force = false) {
    if (!force && state.busy > 0) return;
    try {
      const d = await apiJson("/api/status");
      $("ver-badge").textContent = "v" + (d.version || "1.0.0-alpha.4.1");
      const fk = Math.round((d.sram_free || 0) / 1024);
      const tk = Math.round((d.sram_total || 532480) / 1024);
      const usedPct = Math.max(0, Math.min(100, Math.round(((tk - fk) / tk) * 100)));
      $("st-ram").textContent = `${fk}KB free / ${tk}KB (${100 - usedPct}%)`;
      $("sram-fill").style.width = `${100 - usedPct}%`;
      const bat = d.battery || {};
      const wf = d.wifi || {};
      $("st-ip").textContent = (wf.connected ? wf.ip : "127.0.0.1") + ":" + (d.port || 8080);
      $("st-hw").textContent = `CPU ${d.cpu_mhz || 150}MHz ${Number(d.temp_c || 0).toFixed(1)}C | BAT ${bat.percent ?? "--"}%${bat.charging ? " CHG" : ""} | RSSI ${wf.rssi || 0}dBm`;
      $("conn-pill").classList.remove("off");
      $("conn-txt").textContent = "CONNECTED";
      $("sys-json").textContent = JSON.stringify(d, null, 2);
    } catch (_) {
      $("conn-pill").classList.add("off");
      $("conn-txt").textContent = "OFFLINE";
    }
  }

  async function loadDir(path = "") {
    try {
      const d = await apiJson("/api/files?path=" + encodeURIComponent(path));
      state.cwd = d.path || "";
      $("cwd-label").textContent = (d.root || "/sd/pinhos") + (state.cwd ? "/" + state.cwd : "");
      const ul = $("file-list");
      ul.innerHTML = "";
      for (const e of d.entries || []) {
        const li = document.createElement("li");
        li.className = "file-item" + (state.selected && state.selected.path === e.path ? " selected" : "");
        const ic = e.type === "dir" ? "[DIR]" : (e.name.endsWith(".bmp") ? "[BMP]" : "[FILE]");
        li.innerHTML = `<span>${ic} ${e.name}</span><span class="fsize">${e.type === "dir" ? "" : fmtSize(e.size)}</span>`;
        li.onclick = () => {
          state.selected = e;
          document.querySelectorAll(".file-item").forEach((x) => x.classList.remove("selected"));
          li.classList.add("selected");
          if (e.type === "dir") loadDir(e.path);
          else openFile(e.path, e.size);
        };
        ul.appendChild(li);
      }
    } catch (err) {
      log("List error: " + err.message, "ERR");
    }
  }

  async function fetchBlobUrl(url) {
    const res = await apiFetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blob = await res.blob();
    return URL.createObjectURL(blob);
  }

  async function openFile(path, size = null) {
    if (path.toLowerCase().endsWith(".bmp")) {
      try {
        const blobUrl = await fetchBlobUrl("/api/file?path=" + encodeURIComponent(path) + "&t=" + Date.now());
        $("bmp-img").src = blobUrl;
        $("bmp-img").classList.remove("hidden");
        $("bmp-empty").classList.add("hidden");
        $("bmp-name").textContent = path;
        $("bmp-dl").href = blobUrl;
        $("bmp-dl").download = path.split("/").pop() || "screen.bmp";
        $("bmp-dl").classList.remove("hidden");
        $("live-img").src = blobUrl;
        $("live-empty").classList.add("hidden");
        log("Loaded BMP: " + path, "SCREEN");
      } catch (err) {
        log("BMP load error: " + err.message, "ERR");
      }
      return;
    }
    if (state.dirty && !confirm("Discard unsaved changes?")) return;
    try {
      state.busy++;
      const res = await apiFetch("/api/file?path=" + encodeURIComponent(path));
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const txt = await res.text();
      state.openFile = path;
      $("active-file").textContent = path;
      $("file-size").textContent = fmtSize(size !== null ? size : txt.length);
      $("code-area").value = txt;
      updateLines();
      setDirty(false);
      $("btn-save").disabled = false;
      const isPy = path.toLowerCase().endsWith(".py");
      $("btn-syntax").disabled = !isPy;
      $("btn-run").disabled = !isPy;
      showTab("studio");
      log("Opened " + path + " (" + fmtSize(txt.length) + ")", "STUDIO");
    } catch (err) {
      log("Open failed: " + err.message, "ERR");
    } finally {
      state.busy = Math.max(0, state.busy - 1);
    }
  }

  async function saveFile() {
    if (!state.openFile) return;
    try {
      const body = $("code-area").value;
      const r = await apiJson("/api/file?path=" + encodeURIComponent(state.openFile), {
        method: "POST", headers: { "Content-Type": "text/plain; charset=utf-8" }, body,
      });
      setDirty(false);
      $("file-size").textContent = fmtSize(r.bytes || body.length);
      log(`Saved ${r.path} (${r.bytes} B) to SD`, "OK");
    } catch (err) {
      log("Save failed: " + err.message, "ERR");
    }
  }

  async function checkSyntax() {
    if (!state.openFile) return;
    if (state.dirty) await saveFile();
    try {
      const d = await apiJson("/api/syntax?path=" + encodeURIComponent(state.openFile), { method: "POST" });
      if (d.ok) log("Syntax OK: " + state.openFile, "OK");
      else log(`SyntaxError${d.line ? " L" + d.line : ""}: ${d.error}`, "ERR");
    } catch (err) {
      log("Syntax check error: " + err.message, "ERR");
    }
  }

  async function runOnDevice() {
    if (!state.openFile) return;
    if (state.dirty) await saveFile();
    try {
      const d = await apiJson("/api/run?path=" + encodeURIComponent(state.openFile), { method: "POST" });
      log(`Launched '${d.name}' on PicoCalc display!`, "RUN");
    } catch (err) {
      log("Run failed: " + err.message, "ERR");
    }
  }

  async function captureScreen() {
    try {
      log("Capturing 320x320 PicoCalc screen...", "SCREEN");
      const d = await apiJson("/api/screenshot", { method: "POST" });
      const blobUrl = await fetchBlobUrl(d.url + "&t=" + Date.now());
      $("live-img").src = blobUrl;
      $("live-empty").classList.add("hidden");
      log("Captured " + d.filename, "OK");
    } catch (err) {
      log("Screenshot error: " + err.message, "ERR");
    }
  }

  document.querySelectorAll(".vkey").forEach((b) => {
    b.onclick = async () => {
      const k = b.dataset.key;
      try {
        await apiJson("/api/key?k=" + encodeURIComponent(k), { method: "POST" });
        log("Sent key [" + k + "] to PicoCalc", "KEY");
      } catch (err) {
        log("Key err: " + err.message, "ERR");
      }
    };
  });

  $("btn-shot").onclick = captureScreen;
  $("btn-shot2").onclick = captureScreen;
  $("btn-save").onclick = saveFile;
  $("btn-syntax").onclick = checkSyntax;
  $("btn-run").onclick = runOnDevice;
  $("btn-clr-log").onclick = () => { logs.length = 0; log("Console cleared.", "SYSTEM"); };
  $("btn-poll-now").onclick = () => pollStatus(true);
  $("btn-weblog").onclick = async () => {
    try {
      const d = await apiJson("/api/weblog");
      $("full-log").textContent = (d.lines || []).join("\n") + "\nPinhOS> _";
    } catch (err) {
      log("web.log err: " + err.message, "ERR");
    }
  };
  $("btn-up").onclick = () => { if (!state.cwd) return; const p = state.cwd.split("/"); p.pop(); loadDir(p.join("/")); };
  $("btn-refresh").onclick = () => loadDir(state.cwd);
  $("btn-reboot").onclick = async () => {
    if (!confirm("Reboot PicoCalc now?")) return;
    try { await apiJson("/api/reboot", { method: "POST" }); log("Reboot sent.", "WARN"); }
    catch (err) { log("Reboot err: " + err.message, "ERR"); }
  };
  $("btn-new-file").onclick = async () => {
    const nm = prompt("New file name:"); if (!nm) return;
    const rel = state.cwd ? `${state.cwd}/${nm}` : nm;
    try { await apiJson("/api/file?path=" + encodeURIComponent(rel), { method: "POST", body: "" }); await loadDir(state.cwd); await openFile(rel, 0); }
    catch (err) { log("Create err: " + err.message, "ERR"); }
  };
  $("btn-new-dir").onclick = async () => {
    const nm = prompt("New folder name:"); if (!nm) return;
    const rel = state.cwd ? `${state.cwd}/${nm}` : nm;
    try { await apiJson("/api/mkdir?path=" + encodeURIComponent(rel), { method: "POST" }); log("Created " + rel, "OK"); await loadDir(state.cwd); }
    catch (err) { log("Mkdir err: " + err.message, "ERR"); }
  };
  $("btn-del").onclick = async () => {
    const tgt = (state.selected && state.selected.path) || state.openFile;
    if (!tgt || !confirm("Delete " + tgt + "?")) return;
    try { await apiJson("/api/file?path=" + encodeURIComponent(tgt), { method: "DELETE" }); log("Deleted " + tgt, "WARN"); state.selected = null; await loadDir(state.cwd); }
    catch (err) { log("Delete err: " + err.message, "ERR"); }
  };
  $("btn-dl").onclick = async () => {
    const tgt = (state.selected && state.selected.type === "file" && state.selected.path) || state.openFile;
    if (!tgt) return log("Select a file to download.", "WARN");
    try {
      const blobUrl = await fetchBlobUrl("/api/file?path=" + encodeURIComponent(tgt) + "&download=1");
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = tgt.split("/").pop() || "file.bin";
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(blobUrl), 5000);
    } catch (err) {
      log("Download err: " + err.message, "ERR");
    }
  };
  document.querySelectorAll(".pill").forEach((b) => {
    b.onclick = () => { if (b.dataset.nav !== undefined) loadDir(b.dataset.nav); else if (b.dataset.open) openFile(b.dataset.open); };
  });

  const ta = $("code-area");
  ta.addEventListener("input", () => { setDirty(true); updateLines(); });
  ta.addEventListener("scroll", () => { $("line-nums").scrollTop = ta.scrollTop; });
  ta.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); saveFile(); }
    else if (e.key === "F5") { e.preventDefault(); runOnDevice(); }
    else if (e.key === "Tab") {
      e.preventDefault();
      const s = ta.selectionStart, end = ta.selectionEnd;
      ta.value = ta.value.substring(0, s) + "    " + ta.value.substring(end);
      ta.selectionStart = ta.selectionEnd = s + 4;
      setDirty(true); updateLines();
    }
  });

  (async () => {
    await pollStatus(true);
    await loadDir("");
    await openFile("apps/hello_world.py");
    setInterval(() => pollStatus(false), 8000);
  })();
})();
