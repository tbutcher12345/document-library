/* ============================================================
   BHQ INTEGRATION — BankruptcyHQ Case Import for Document Engine
   Fetches cases from n8n webhook cache and imports to Case Context
   
   To re-sync cases, run in BankruptcyHQ browser console (F12):
   (function(){fetch('https://cases.thebankruptcyhq.com/api/cases?status=OPEN&limit=200',{credentials:'include'}).then(r=>r.json()).then(d=>{const c=d?.data?.data||[];fetch('https://178.105.247.138.nip.io/webhook/bankruptcyhq-cases',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'push',cases:c.map(x=>({caseNumber:x.case_number,debtorName:x.case_name,chapter:(x.type||'CH7').replace('CH',''),joint:'single'}))})}).then(r=>r.json()).then(j=>alert('Synced: '+j.stored+' cases'));});})()
   ============================================================ */

async function bhqImportCases() {
  var btn = document.getElementById('bhq-import-btn');
  if (btn) { btn.textContent = 'Syncing...'; btn.disabled = true; }
  try {
    var resp = await fetch('https://178.105.247.138.nip.io/webhook/bhq-cases');
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    var data = await resp.json();
    var cases = data.cases || [];
    if (!cases.length) throw new Error('No cases returned');
    importCasesToDocEngine(cases);
    if (btn) {
      btn.textContent = cases.length + ' cases imported';
      setTimeout(function() { btn.textContent = 'Import from BankruptcyHQ'; btn.disabled = false; }, 3000);
    }
  } catch(e) {
    console.error('BHQ import error:', e);
    if (btn) { btn.textContent = 'Error - check console'; btn.disabled = false; }
  }
}

function importCasesToDocEngine(cases) {
  var existing = [];
  try { existing = JSON.parse(localStorage.getItem('bl_case_contexts') || '[]'); } catch(x) {}
  var existingMap = {};
  existing.forEach(function(c) { if (c.case_number) existingMap[c.case_number] = c; });
  var added = 0, updated = 0;
  cases.forEach(function(bhqCase) {
    var chapter = String(bhqCase.chapter || '7').replace(/^ch/i, '').trim();
    var rec = {
      case_number: bhqCase.caseNumber || bhqCase.case_number || '',
      debtor_name: bhqCase.debtorName || bhqCase.debtor_name || '',
      joint_filing: bhqCase.joint || 'single',
      chapter: chapter,
      trustee_name: bhqCase.trustee || '',
      client_address1: bhqCase.address1 || '',
      client_address2: bhqCase.address2 || '',
      client_email: bhqCase.email || '',
      client_phone: bhqCase.phone || '',
      filing_date: bhqCase.filingDate || bhqCase.filing_date || ''
    };
    if (!rec.case_number) return;
    if (existingMap[rec.case_number]) { Object.assign(existingMap[rec.case_number], rec); updated++; }
    else { existingMap[rec.case_number] = rec; added++; }
  });
  var merged = Object.values(existingMap);
  localStorage.setItem('bl_case_contexts', JSON.stringify(merged));
  if (typeof ccRenderList === 'function') ccRenderList();
  console.log('BHQ import: added=' + added + ', updated=' + updated + ', total=' + merged.length);
}

/* Auto-inject Import button into cc-panel-header when panel opens */
(function() {
  function injectBtn() {
    var header = document.getElementById('cc-panel-header');
    if (header && !document.getElementById('bhq-import-btn')) {
      var btn = document.createElement('button');
      btn.id = 'bhq-import-btn';
      btn.onclick = bhqImportCases;
      btn.style.cssText = 'font-size:11px;padding:4px 10px;background:#8b1c1c;color:#fff;border:none;border-radius:3px;cursor:pointer;margin-right:8px;font-family:inherit';
      btn.textContent = 'Import from BankruptcyHQ';
      var closeBtn = header.querySelector('.cc-close');
      if (closeBtn) { header.insertBefore(btn, closeBtn); }
      else { header.appendChild(btn); }
    }
  }
  var attempts = 0;
  var iv = setInterval(function() {
    if (typeof window.ccOpenPanel === 'function' && !window.ccOpenPanel._bhqWrapped) {
      var orig = window.ccOpenPanel;
      window.ccOpenPanel = function() { orig.apply(this, arguments); setTimeout(injectBtn, 50); };
      window.ccOpenPanel._bhqWrapped = true;
    }
    injectBtn();
    if (++attempts > 40) clearInterval(iv);
  }, 500);
})();
