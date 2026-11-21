// ==UserScript==
// @name         InternFlow autofill + tracker
// @namespace    internflow
// @version      1.0
// @description  Fills your details on job application forms, leaves the rest and the submit button to you, and logs each application you submit.
// @match        *://boards.greenhouse.io/*
// @match        *://job-boards.greenhouse.io/*
// @match        *://jobs.lever.co/*
// @match        *://jobs.ashbyhq.com/*
// @match        *://*.myworkdayjobs.com/*
// @match        *://jobs.smartrecruiters.com/*
// @match        *://*.icims.com/*
// @match        *://*.taleo.net/*
// @match        *://*.oraclecloud.com/*
// @match        *://*.successfactors.com/*
// @match        *://*.successfactors.eu/*
// @match        *://apply.workable.com/*
// @match        *://*.jobvite.com/*
// @match        *://*.bamboohr.com/*
// @match        *://*.breezy.hr/*
// @match        *://*.recruitee.com/*
// @match        *://*.paylocity.com/*
// @match        *://*.dayforcehcm.com/*
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_xmlhttpRequest
// @connect      api.github.com
// @connect      *
// @run-at       document-idle
// ==/UserScript==
(function () {
  "use strict";
  if (window.top !== window.self && !/greenhouse|lever|ashby|workday|smartrecruiters/i.test(location.host)) return;

  // ---------- storage (works with Tampermonkey, Violentmonkey, iOS Userscripts) ----------
  const store = {
    get: (k, d) => { try { const v = GM_getValue(k); return v === undefined ? d : v; } catch (e) { try { const v = localStorage.getItem("if_" + k); return v == null ? d : JSON.parse(v); } catch (x) { return d; } } },
    set: (k, v) => { try { GM_setValue(k, v); } catch (e) { try { localStorage.setItem("if_" + k, JSON.stringify(v)); } catch (x) {} } },
  };
  const FIELDS = [
    ["first", "First name"], ["last", "Last name"], ["email", "Email"], ["phone", "Phone"],
    ["address", "Street address"], ["city", "City"], ["state", "State (e.g. Michigan)"], ["zip", "ZIP"],
    ["linkedin", "LinkedIn URL"], ["github", "GitHub URL"], ["website", "Portfolio URL"],
    ["school", "School"], ["degree", "Degree (e.g. Bachelor of Business Administration)"], ["major", "Major"], ["gpa", "GPA"],
    ["grad", "Graduation (e.g. May 2028)"], ["company", "Current company"], ["jobtitle", "Current job title"],
    ["howHeard", "How did you hear about us"],
    ["authorized", "Legally authorized to work in the US? (yes / no / blank = I answer)"],
    ["sponsor", "Will you need sponsorship? (yes / no / blank = I answer)"],
  ];
  const DEFAULTS = { school: "Western Michigan University", major: "Business Analytics", grad: "May 2028", gpa: "3.56",
    linkedin: "https://linkedin.com/in/hossainsowrob/", github: "https://github.com/hossainsowrob", website: "https://hossainsowrob.github.io",
    company: "Flowserve Corporation", jobtitle: "Supply Chain Intern", howHeard: "Company website" };
  const manual = () => { const m = store.get("profile", {}), o = {}; for (const k in m) if (m[k]) o[k] = m[k]; return o; };
  const P = () => Object.assign({}, DEFAULTS, store.get("pf", {}), manual());   // your ⚙ entries > portfolio > built-in defaults
  const PORTFOLIO = () => store.get("portfolio_url", "https://hossainsowrob.github.io");

  // ---------- helpers ----------
  const txt = (el) => (el && (el.innerText || el.textContent) || "").replace(/\s+/g, " ").trim();
  const visible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length) && getComputedStyle(el).visibility !== "hidden";
  function labelOf(el) {
    const parts = [el.getAttribute("aria-label"), el.placeholder, el.name, el.id, el.getAttribute("data-qa"), el.getAttribute("autocomplete")];
    const lb = el.getAttribute("aria-labelledby"); if (lb) lb.split(/\s+/).forEach((i) => parts.push(txt(document.getElementById(i))));
    if (el.id) { try { document.querySelectorAll('label[for="' + CSS.escape(el.id) + '"]').forEach((l) => parts.push(txt(l))); } catch (e) {} }
    const wl = el.closest("label"); if (wl) parts.push(txt(wl));
    const grp = el.closest("fieldset"); if (grp) parts.push(txt(grp.querySelector("legend")));
    const box = el.closest('[class*="field"],[class*="question"],[class*="form-group"],[data-automation-id],[class*="application-question"]'); if (box && box.innerText && box.innerText.length < 300) parts.push(txt(box));
    return parts.filter(Boolean).join(" ").toLowerCase();
  }
  const NEVER = /gender|race|ethnic|hispanic|latino|veteran|disabilit|lgbt|sexual|pronoun|religio|password|captcha|search|date of birth|birth|ssn|social security|salary|compensation|signature/;
  const RULES = [
    [/first.?name|given.?name|fname|preferred.?first/, "first"], [/last.?name|family.?name|surname|lname/, "last"],
    [/full.?name|your name|^name\b|legal name/, "full"], [/e-?mail/, "email"], [/phone|mobile|cell|telephone/, "phone"],
    [/linkedin/, "linkedin"], [/github/, "github"], [/website|portfolio|personal (site|url)|other url|url/, "website"],
    [/zip|postal/, "zip"], [/\bcity\b|town/, "city"], [/state|province|region/, "state"], [/address|street/, "address"],
    [/school|university|college|institution/, "school"], [/degree|education level/, "degree"], [/major|field of study|discipline|concentration/, "major"],
    [/gpa|grade point/, "gpa"], [/graduat|grad date|expected/, "grad"], [/current (company|employer)|employer|company name/, "company"],
    [/current (job )?(title|position)|job title/, "jobtitle"], [/hear about|how did you|source/, "howHeard"],
  ];
  const AUTH = /(legally )?(authori[sz]ed|eligible|permitted|right) to work|work authori[sz]ation|work in the (u\.?s|united states)/;
  const SPON = /(require|need|will you).{0,40}(sponsor|visa)|sponsorship/;
  function valueFor(lbl, p) {
    if (NEVER.test(lbl)) return null;
    if (AUTH.test(lbl)) return p.authorized ? { yn: p.authorized.toLowerCase().startsWith("y") } : null;
    if (SPON.test(lbl)) return p.sponsor ? { yn: p.sponsor.toLowerCase().startsWith("y") } : null;
    for (const [re, k] of RULES) if (re.test(lbl)) {
      if (k === "full") return p.first && p.last ? { v: p.first + " " + p.last } : null;
      return p[k] ? { v: String(p[k]) } : null;
    }
    return null;
  }
  function setVal(el, v) {
    const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const d = Object.getOwnPropertyDescriptor(proto, "value"); d && d.set ? d.set.call(el, v) : (el.value = v);
    ["input", "change", "blur"].forEach((e) => el.dispatchEvent(new Event(e, { bubbles: true })));
  }
  function pickOption(sel, want) {
    const w = want.toLowerCase(); const opts = [...sel.options].filter((o) => o.value !== "" && !/^select|^choose|^--/i.test(o.text));
    return opts.find((o) => o.text.trim().toLowerCase() === w) || opts.find((o) => o.text.toLowerCase().includes(w)) || opts.find((o) => w.includes(o.text.trim().toLowerCase()) && o.text.trim().length > 2);
  }

  // ---------- fill ----------
  function fill() {
    const p = P(); let n = 0; const done = new Set();
    document.querySelectorAll("input, textarea, select").forEach((el) => {
      if (el.dataset.ifFilled || el.disabled || el.readOnly || !visible(el)) return;
      const type = (el.type || "").toLowerCase();
      if (["hidden", "submit", "button", "checkbox", "password", "file", "image", "reset"].includes(type)) return;
      const lbl = labelOf(el); const want = valueFor(lbl, p); if (!want) return;
      if (type === "radio") {
        if (want.yn === undefined || done.has(el.name)) return; done.add(el.name);
        const group = [...document.querySelectorAll('input[type=radio]')].filter((r) => r.name === el.name);
        const hit = group.find((r) => { const t = (labelOf(r).split(" ").pop() + " " + txt(r.closest("label")) + " " + (r.value || "")).toLowerCase(); return want.yn ? /\byes\b/.test(t) : /\bno\b/.test(t); });
        if (hit && !group.some((r) => r.checked)) { hit.click(); group.forEach((r) => (r.dataset.ifFilled = 1)); n++; }
        return;
      }
      if (el.tagName === "SELECT") {
        if (el.value) return; const w = want.v || (want.yn ? "yes" : "no"); const o = pickOption(el, w);
        if (o) { el.value = o.value; el.dispatchEvent(new Event("change", { bubbles: true })); el.dataset.ifFilled = 1; n++; } return;
      }
      if (want.v === undefined || el.value) return;
      setVal(el, want.v); el.dataset.ifFilled = 1; n++;
    });
    // resume
    const r = store.get("resume", null);
    if (r) document.querySelectorAll('input[type=file]').forEach((el) => {
      if (el.dataset.ifFilled || el.files.length) return; const l = labelOf(el);
      if (/cover/.test(l) || !/resume|cv|attach|upload|file/.test(l)) return;
      try { const bin = atob(r.b64), u8 = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
        const dt = new DataTransfer(); dt.items.add(new File([u8], r.name, { type: r.type })); el.files = dt.files;
        el.dispatchEvent(new Event("change", { bubbles: true })); el.dataset.ifFilled = 1; n++; } catch (e) {}
    });
    // required fields still empty
    let left = 0;
    document.querySelectorAll("input[required], textarea[required], select[required], [aria-required=true]").forEach((el) => {
      if (!visible(el) || ["hidden", "checkbox", "radio", "submit"].includes(el.type)) return;
      if (!el.value) { el.style.outline = "2px solid #e5484d"; left++; } else if (el.style.outline.includes("e5484d")) el.style.outline = "";
    });
    return { n, left };
  }

  // ---------- tracking ----------
  const nkey = () => location.host + location.pathname.replace(/\/(apply|application)(\/.*)?$/i, "").replace(/\/$/, "");
  function guessMeta() {
    const og = (document.querySelector('meta[property="og:site_name"]') || {}).content;
    const h1 = txt(document.querySelector("h1")) || document.title;
    const gh = location.pathname.split("/")[1];
    return { company: og || (/greenhouse|lever|ashby/.test(location.host) ? gh : location.host.split(".").slice(-3, -2)[0]) || "", title: h1.slice(0, 140) };
  }
  function dispatch(payload, cb) {
    const s = store.get("gh", {}); if (!s.owner || !s.repo || !s.token) return cb(false, "Set your GitHub repo and token in ⚙ first");
    const body = JSON.stringify({ event_type: "applied", client_payload: payload });
    const hdr = { Authorization: "Bearer " + s.token, Accept: "application/vnd.github+json", "Content-Type": "application/json" };
    const url = `https://api.github.com/repos/${s.owner}/${s.repo}/dispatches`;
    const done = (ok, st) => cb(ok, ok ? "" : "GitHub said " + st);
    try { GM_xmlhttpRequest({ method: "POST", url, headers: hdr, data: body, onload: (r) => done(r.status === 204, r.status), onerror: () => done(false, "network") }); }
    catch (e) { fetch(url, { method: "POST", headers: hdr, body }).then((r) => done(r.status === 204, r.status)).catch(() => done(false, "network")); }
  }
  function markApplied(manual) {
    const k = nkey(), seen = store.get("applied", {}); if (seen[k] && !manual) return;
    const m = guessMeta(); const payload = { url: location.href.split("#")[0], company: m.company, title: m.title, device: /Mobi|Android|iPhone|iPad/.test(navigator.userAgent) ? "phone" : "laptop" };
    dispatch(payload, (ok, why) => {
      if (ok) { seen[k] = Date.now(); store.set("applied", seen); toast("✅ Logged as applied. Check Telegram for your count."); }
      else { const q = store.get("pending", []); q.push(payload); store.set("pending", q.slice(-50)); toast("Couldn't log it yet (" + why + "). It will retry next time."); }
    });
  }
  function retryPending() { const q = store.get("pending", []); if (!q.length) return; store.set("pending", []); q.forEach((pl) => dispatch(pl, (ok) => { if (!ok) { const r = store.get("pending", []); r.push(pl); store.set("pending", r); } })); }
  const CONFIRM = /(thank you for (applying|your (application|interest))|application (has been )?(submitted|received|sent)|successfully (submitted|applied)|we(['’]ve| have) received your application|your application (was|has been) (submitted|received))/i;
  let watching = false;
  function watch() {
    if (watching) return; watching = true; const t0 = Date.now();
    const iv = setInterval(() => {
      if (CONFIRM.test(document.body ? document.body.innerText.slice(0, 20000) : "")) { clearInterval(iv); watching = false; sessionStorage.removeItem("if_submit"); markApplied(false); }
      else if (Date.now() - t0 > 90000) { clearInterval(iv); watching = false; }
    }, 1000);
  }
  document.addEventListener("click", (e) => {
    const b = e.target.closest && e.target.closest("button, input[type=submit], [role=button]"); if (!b) return;
    if (/^\s*(submit( application)?|send application|finish|complete application)\s*$/i.test(txt(b) || b.value || "")) { try { sessionStorage.setItem("if_submit", Date.now()); } catch (x) {} watch(); }
  }, true);
  try { if (Date.now() - Number(sessionStorage.getItem("if_submit") || 0) < 300000) watch(); } catch (e) {}


  // ---------- read contact + resume from your portfolio (so you only edit the portfolio) ----------
  function parsePortfolio(html, base) {
    const doc = new DOMParser().parseFromString(html, "text/html"), out = {};
    const J = doc.querySelector('script#internflow-profile'); if (J) { try { Object.assign(out, JSON.parse(J.textContent)); } catch (e) {} }
    doc.querySelectorAll('script[type="application/ld+json"]').forEach((s) => { try { const d = JSON.parse(s.textContent), p = [].concat(d["@graph"] || d).find((x) => /Person/.test(x["@type"] || ""));
      if (p) { if (!out.email && p.email) out.email = String(p.email).replace(/^mailto:/, ""); if (!out.phone && p.telephone) out.phone = p.telephone; if (!out._name && p.name) out._name = p.name; } } catch (e) {} });
    const mail = doc.querySelector('a[href^="mailto:"]'); if (!out.email && mail) out.email = mail.getAttribute("href").slice(7).split("?")[0];
    const tel = doc.querySelector('a[href^="tel:"]'); if (!out.phone && tel) out.phone = decodeURIComponent(tel.getAttribute("href").slice(4));
    const body = doc.body ? doc.body.textContent : "";
    if (!out.email) { const m = body.match(/[\w.+-]+@[\w-]+\.[\w.]+/); if (m) out.email = m[0]; }
    if (!out.phone) { const m = body.match(/\(?\b\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b/); if (m) out.phone = m[0]; }
    doc.querySelectorAll("a[href]").forEach((a) => { const h = a.getAttribute("href") || "", l = (a.textContent || "") + " " + h;
      if (!out.linkedin && /linkedin\.com\/in\//i.test(h)) out.linkedin = h.split("?")[0];
      if (!out.github && /github\.com\/[^\/]+\/?$/i.test(h)) out.github = h;
      if (!out._resume && /resum|\bcv\b/i.test(l) && /\.(pdf|docx?)(\?|$)/i.test(h)) { try { out._resume = new URL(h, base).href; } catch (e) {} } });
    if (!out.first) {
      let n = out._name || (doc.querySelector("h1") || {}).textContent || (doc.querySelector('meta[property="og:title"]') || {}).content || doc.title || "";
      const im = n.match(/I['’]m\s+([A-Z][\w.'’-]+(?:\s+[A-Z][\w.'’-]+){0,2})/); n = (im ? im[1] : n.split(/[|\-–—•·,]/)[0]).replace(/portfolio|resume|hi\b|hello/gi, "").replace(/\s+/g, " ").trim();
      const w = n.split(" ").filter(Boolean); if (w.length >= 2 && w.length <= 4) { out.first = w[0]; out.last = w[w.length - 1]; out._name = n; }
    }
    return out;
  }
  function b64(buf) { let s = "", u = new Uint8Array(buf); for (let i = 0; i < u.length; i += 8192) s += String.fromCharCode.apply(null, u.subarray(i, i + 8192)); return btoa(s); }
  function xhr(url, type, cb) { try { GM_xmlhttpRequest({ method: "GET", url, responseType: type, onload: (r) => cb(r.status < 400 ? r : null), onerror: () => cb(null) }); }
    catch (e) { fetch(url).then((r) => (type === "arraybuffer" ? r.arrayBuffer() : r.text()).then((x) => cb({ response: x, responseText: x, finalUrl: r.url }))).catch(() => cb(null)); } }
  function syncPortfolio(force, done) {
    const url = PORTFOLIO(); if (!url || (!force && Date.now() - store.get("pf_at", 0) < 6 * 36e5)) return done && done(null);
    xhr(url, "text", (r) => { if (!r) return done && done("Couldn't reach your portfolio"); const pf = parsePortfolio(r.responseText || r.response, url);
      const keep = {}; ["first", "last", "email", "phone", "city", "state", "zip", "address", "linkedin", "github", "website", "school", "degree", "major", "gpa", "grad", "company", "jobtitle"].forEach((k) => { if (pf[k]) keep[k] = pf[k]; });
      if (!keep.website) keep.website = url; store.set("pf", keep); store.set("pf_at", Date.now());
      if (pf._resume && !store.get("resume_manual", false)) xhr(pf._resume, "arraybuffer", (rr) => { if (rr && rr.response) { const nm = decodeURIComponent(pf._resume.split("?")[0].split("/").pop()) || "resume.pdf";
        store.set("resume", { name: nm, type: /docx?$/i.test(nm) ? "application/vnd.openxmlformats-officedocument.wordprocessingml.document" : "application/pdf", b64: b64(rr.response) }); } done && done(null, pf); });
      else done && done(null, pf); }); }

  // ---------- UI (shadow DOM so site CSS can't break it) ----------
  const host = document.createElement("div"); host.style.cssText = "position:fixed;right:12px;bottom:12px;z-index:2147483647;font:14px system-ui,sans-serif";
  const root = host.attachShadow({ mode: "open" });
  root.innerHTML = `<style>
    .bar{display:flex;gap:8px;align-items:center;justify-content:flex-end} button{border:0;border-radius:999px;padding:12px 16px;font:600 14px system-ui;box-shadow:0 2px 8px #0005;cursor:pointer;min-height:44px}
    .fill{background:#2457d6;color:#fff}.ap{background:#1a7f37;color:#fff}.set{background:#fff;color:#111}
    .toast{background:#111;color:#fff;padding:10px 14px;border-radius:12px;margin-bottom:8px;max-width:78vw;display:none}
    .modal{position:fixed;inset:0;background:#0008;display:none;align-items:center;justify-content:center}.modal.on{display:flex}
    .box{background:#fff;color:#111;border-radius:14px;padding:16px;width:min(92vw,460px);max-height:86vh;overflow:auto}
    .box label{display:block;font-size:12px;margin-top:8px;color:#555}.box input{width:100%;box-sizing:border-box;padding:9px;border:1px solid #bbb;border-radius:8px;font-size:15px}
    .row{display:flex;gap:8px;margin-top:14px}.row button{flex:1}</style>
    <div class="toast" id="t"></div><div class="bar"><button class="set" id="s" title="Settings">⚙</button><button class="ap" id="a">✅ Applied</button><button class="fill" id="f">⚡ Fill</button></div>
    <div class="modal" id="m"><div class="box"><b>InternFlow settings</b> <span style="color:#777;font-size:12px">(saved only on this device)</span><div id="fs"></div>
    <label>Portfolio URL (details and resume are read from here)</label><input id="pu"><div class="row"><button class="set" id="sy" style="border:1px solid #bbb">Sync from portfolio now</button></div><div id="pn" style="font-size:12px;color:#555;margin-top:4px"></div>
    <label>Or upload a resume yourself (overrides the one on your portfolio)</label><input type="file" id="rf" accept=".pdf,.doc,.docx"><div id="rn" style="font-size:12px;color:#555"></div>
    <b style="display:block;margin-top:14px">Application tracking</b>
    <label>GitHub username</label><input id="go"><label>Repository name</label><input id="gr" placeholder="internflow"><label>GitHub token (fine-grained, this repo only, Contents: read &amp; write)</label><input id="gt" type="password">
    <div class="row"><button class="set" id="x" style="border:1px solid #bbb">Cancel</button><button class="fill" id="sv">Save</button></div></div></div>`;
  const $ = (i) => root.getElementById(i);
  function toast(m) { const t = $("t"); t.textContent = m; t.style.display = "block"; clearTimeout(toast.h); toast.h = setTimeout(() => (t.style.display = "none"), 6000); }
  $("fs").innerHTML = '<div style="font-size:12px;color:#555;margin-top:6px">Leave a box empty to use what your portfolio says. Type something only to override it.</div>' + FIELDS.map(([k, l]) => `<label>${l}</label><input data-k="${k}">`).join("");
  function openSettings() {
    const p = P(), mo = manual(), g = store.get("gh", {}); root.querySelectorAll("[data-k]").forEach((i) => { i.value = mo[i.dataset.k] || ""; i.placeholder = p[i.dataset.k] || ""; });
    $("pu").value = PORTFOLIO(); const pf = store.get("pf", {}); $("pn").textContent = pf.email || pf.first ? `Read from portfolio: ${[pf.first, pf.last].filter(Boolean).join(" ")} · ${pf.email || "no email found"} · ${pf.phone || "no phone found"}` : "Nothing read from the portfolio yet";
    $("go").value = g.owner || ""; $("gr").value = g.repo || ""; $("gt").value = g.token || ""; const r = store.get("resume", null); $("rn").textContent = r ? (store.get("resume_manual", false) ? "Your upload: " : "From portfolio: ") + r.name : "No resume found yet"; $("m").classList.add("on");
  }
  $("s").onclick = openSettings; $("x").onclick = () => $("m").classList.remove("on");
  $("rf").onchange = (e) => { const f = e.target.files[0]; if (!f) return; if (f.size > 4e6) return alert("Resume must be under 4 MB"); const fr = new FileReader();
    fr.onload = () => { store.set("resume", { name: f.name, type: f.type || "application/pdf", b64: String(fr.result).split(",")[1] }); store.set("resume_manual", true); $("rn").textContent = "Your upload: " + f.name; }; fr.readAsDataURL(f); };
  $("sv").onclick = () => { const p = {}; root.querySelectorAll("[data-k]").forEach((i) => (p[i.dataset.k] = i.value.trim())); store.set("profile", p);
    store.set("portfolio_url", $("pu").value.trim()); store.set("gh", { owner: $("go").value.trim(), repo: $("gr").value.trim(), token: $("gt").value.trim() }); $("m").classList.remove("on"); toast("Saved"); retryPending(); };
  $("f").onclick = () => { const r = fill(); toast(`Filled ${r.n} field${r.n === 1 ? "" : "s"}` + (r.left ? ` · ${r.left} required left for you (outlined red)` : "") + ". Check everything, then submit."); };
  $("a").onclick = () => markApplied(true);
  $("sy").onclick = () => { $("pn").textContent = "Reading…"; store.set("portfolio_url", $("pu").value.trim()); syncPortfolio(true, (err, pf) => { $("pn").textContent = err || `Read: ${[pf.first, pf.last].filter(Boolean).join(" ") || "no name"} · ${pf.email || "no email"} · ${pf.phone || "no phone"}${pf._resume ? " · resume found" : " · no resume link found"}`; }); };
  document.documentElement.appendChild(host);

  // auto-fill when a form shows up (also each new step of multi-page forms), once per field
  let timer; const auto = () => { clearTimeout(timer); timer = setTimeout(() => { if (document.querySelectorAll("input:not([type=hidden]),textarea,select").length >= 3 && P().email) { const r = fill(); if (r.n) toast(`Filled ${r.n} field${r.n === 1 ? "" : "s"}. Check them, finish the rest, then submit.`); } }, 1500); };
  new MutationObserver(auto).observe(document.body, { childList: true, subtree: true }); auto();
  syncPortfolio(false, (err, pf) => { if (pf) { setTimeout(fill, 300); toast(`Details read from your portfolio: ${[pf.first, pf.last].filter(Boolean).join(" ") || "name not found"}. Tap ⚙ to check.`); } });
  retryPending();
})();
