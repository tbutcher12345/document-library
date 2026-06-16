/* ============================================================
   CASE AUTOCOMPLETE v3.0 — Butcher Law Document Engine
   Covers ALL 20 document types. Attaches typeahead to every
   name field (client_name, debtor_name) across the entire
   engine and auto-fills all case fields on selection.
   2026-06-16
============================================================ */
(function () {

  /* ── Helpers ─────────────────────────────────────────────── */

  function esc(str) {
    return String(str || '').replace(/[&<>"']/g, function (m) {
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m];
    });
  }

  function getCases() {
    return (typeof window.ccGetAll === 'function') ? window.ccGetAll() : [];
  }

  function setVal(id, val) {
    var el = document.getElementById(id);
    if (el && val !== undefined && val !== null) el.value = val;
  }

  /* ── Build a dropdown on any name input ──────────────────── */

  function attachDropdown(inputEl) {
    if (!inputEl || inputEl._bhqAC) return;
    inputEl._bhqAC = true;
    inputEl.parentElement.style.position = 'relative';

    var drop = document.createElement('div');
    drop.className = 'bhq-ac-drop';
    drop.style.cssText = [
      'position:absolute','top:100%','left:0','right:0','z-index:99999',
      'background:#fff','border:1px solid #c9a84c','border-top:none',
      'border-radius:0 0 6px 6px','box-shadow:0 8px 24px rgba(0,0,0,.2)',
      'max-height:260px','overflow-y:auto','display:none',
      'font-family:inherit','font-size:13px'
    ].join(';');
    inputEl.parentElement.appendChild(drop);

    function render(query) {
      var q = query.toLowerCase().trim();
      if (!q) { drop.style.display = 'none'; return; }
      var matches = getCases().filter(function (c) {
        return (c.debtor_name  || '').toLowerCase().includes(q) ||
               (c.debtor2_name || '').toLowerCase().includes(q) ||
               (c.case_number  || '').toLowerCase().includes(q);
      }).slice(0, 12);
      if (!matches.length) { drop.style.display = 'none'; return; }
      drop.innerHTML = '';
      matches.forEach(function (c) {
        var item = document.createElement('div');
        item.style.cssText = 'padding:9px 14px;cursor:pointer;border-bottom:1px solid #f0e8d8;display:flex;justify-content:space-between;align-items:center;line-height:1.35;';
        item.innerHTML =
          '<span style="font-weight:600;color:#2a1f0f;">' + esc(c.debtor_name) +
          (c.debtor2_name ? '<span style="color:#7a6a4f;font-weight:400;"> &amp; ' + esc(c.debtor2_name) + '</span>' : '') +
          '</span>' +
          '<span style="color:#8b6914;font-size:11px;margin-left:12px;white-space:nowrap;flex-shrink:0;">' +
          esc(c.case_number) + ' · Ch. ' + esc(c.chapter || '7') + '</span>';
        item.addEventListener('mousedown', function (e) {
          e.preventDefault();
          fillFromCase(c);
          drop.style.display = 'none';
        });
        item.addEventListener('mouseenter', function () { item.style.background = '#fdf6e3'; });
        item.addEventListener('mouseleave', function () { item.style.background = ''; });
        drop.appendChild(item);
      });
      drop.style.display = 'block';
    }

    inputEl.addEventListener('input',  function () { render(this.value); });
    inputEl.addEventListener('focus',  function () { if (this.value.trim()) render(this.value); });
    inputEl.addEventListener('blur',   function () { setTimeout(function () { drop.style.display = 'none'; }, 160); });
    inputEl.addEventListener('keydown', function (e) {
      var items = Array.from(drop.querySelectorAll('div'));
      var idx   = items.findIndex(function (i) { return i.hasAttribute('data-sel'); });
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (idx >= 0) { items[idx].removeAttribute('data-sel'); items[idx].style.background = ''; }
        var nxt = items[(idx + 1) % items.length];
        if (nxt) { nxt.setAttribute('data-sel','1'); nxt.style.background = '#fdf6e3'; nxt.scrollIntoView({block:'nearest'}); }
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (idx >= 0) { items[idx].removeAttribute('data-sel'); items[idx].style.background = ''; }
        var prv = items[(idx - 1 + items.length) % items.length];
        if (prv) { prv.setAttribute('data-sel','1'); prv.style.background = '#fdf6e3'; prv.scrollIntoView({block:'nearest'}); }
      } else if (e.key === 'Enter' && idx >= 0) {
        e.preventDefault(); items[idx].dispatchEvent(new MouseEvent('mousedown'));
      } else if (e.key === 'Escape') { drop.style.display = 'none'; }
    });
  }

  /* ── Fill ALL case fields found in the current form ─────── */

  function fillFromCase(c) {
    // Primary name fields (two variants used across docs)
    setVal('client_name',    c.debtor_name    || '');
    setVal('debtor_name',    c.debtor_name    || '');

    // Joint/co-debtor name fields
    setVal('debtor2_name',   c.debtor2_name   || '');
    setVal('client2_name',   c.debtor2_name   || '');

    // Case identifiers
    setVal('case_number',    c.case_number    || '');
    setVal('case_name',      c.debtor_name    || '');  // used in motion forms

    // Chapter/filing details
    setVal('chapter',        c.chapter        || '7');
    setVal('filing_date',    c.filing_date    || '');

    // Client address
    setVal('client_address1', c.client_address1 || '');
    setVal('client_address2', c.client_address2 || '');

    // Trustee
    setVal('trustee_name',   c.trustee_name   || '');

    // Joint filing dropdown
    var jf = document.getElementById('joint_filing');
    if (jf) jf.value = (c.joint_filing === 'joint') ? 'Joint debtors' : 'Single debtor';

    // Flash case number to confirm fill
    var cn = document.getElementById('case_number') || document.getElementById('case_name');
    if (cn) {
      cn.style.transition = 'background .15s';
      cn.style.background = '#fffbe6';
      setTimeout(function () { cn.style.background = ''; }, 900);
    }

    // Re-focus the name field we typed in
    var active = document.activeElement;
    if (active && active._bhqAC) active.focus();
  }

  /* ── Scan the open form and attach dropdowns ─────────────── */

  function installOnForm() {
    // All possible name trigger fields across all 20 doc types
    ['client_name', 'debtor_name'].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) attachDropdown(el);
    });
  }

  /* ── Case Context panel: cc-debtor1 typeahead ────────────── */

  function installCCTypeahead() {
    var d1 = document.getElementById('cc-debtor1');
    if (!d1 || d1._bhqAC) return;
    attachDropdown(d1);
    // Override fillFromCase for CC panel (fills different field IDs)
    var drop = d1.parentElement.querySelector('.bhq-ac-drop');
    if (drop) {
      Array.from(drop.querySelectorAll('div')).forEach(function (item) {
        item.replaceWith(item.cloneNode(true)); // remove old listener
      });
    }
    // Re-bind with CC-specific fill
    d1._bhqAC = false; // reset so we can re-attach
    attachDropdownCC(d1);
  }

  function attachDropdownCC(inputEl) {
    if (!inputEl || inputEl._bhqAC) return;
    inputEl._bhqAC = true;
    inputEl.parentElement.style.position = 'relative';
    var drop = document.createElement('div');
    drop.className = 'bhq-ac-drop';
    drop.style.cssText = [
      'position:absolute','top:100%','left:0','right:0','z-index:99999',
      'background:#fff','border:1px solid #c9a84c','border-top:none',
      'border-radius:0 0 6px 6px','box-shadow:0 8px 24px rgba(0,0,0,.2)',
      'max-height:240px','overflow-y:auto','display:none',
      'font-family:inherit','font-size:13px'
    ].join(';');
    inputEl.parentElement.appendChild(drop);

    function render(query) {
      var q = query.toLowerCase().trim();
      if (!q) { drop.style.display = 'none'; return; }
      var matches = getCases().filter(function (c) {
        return (c.debtor_name||'').toLowerCase().includes(q)||
               (c.debtor2_name||'').toLowerCase().includes(q)||
               (c.case_number||'').toLowerCase().includes(q);
      }).slice(0,12);
      if (!matches.length) { drop.style.display='none'; return; }
      drop.innerHTML='';
      matches.forEach(function(c){
        var item=document.createElement('div');
        item.style.cssText='padding:9px 14px;cursor:pointer;border-bottom:1px solid #f0e8d8;display:flex;justify-content:space-between;align-items:center;';
        item.innerHTML='<span style="font-weight:600;color:#2a1f0f;">'+esc(c.debtor_name)+(c.debtor2_name?'<span style="color:#7a6a4f;font-weight:400;"> &amp; '+esc(c.debtor2_name)+'</span>':'')+'</span><span style="color:#8b6914;font-size:11px;margin-left:12px;white-space:nowrap;">'+esc(c.case_number)+' · Ch. '+esc(c.chapter||'7')+'</span>';
        item.addEventListener('mousedown',function(e){
          e.preventDefault();
          inputEl.value=c.debtor_name||'';
          setVal('cc-debtor2',c.debtor2_name||'');
          setVal('cc-casenum',c.case_number||'');
          setVal('cc-chapter',c.chapter||'7');
          setVal('cc-trustee',c.trustee_name||'');
          setVal('cc-addr1',c.client_address1||'');
          setVal('cc-addr2',c.client_address2||'');
          setVal('cc-email',c.client_email||'');
          setVal('cc-phone',c.client_phone||'');
          var jt=document.getElementById('cc-joint');
          if(jt){jt.value=c.joint_filing||'single';if(typeof ccToggleJoint==='function')ccToggleJoint(jt.value);}
          drop.style.display='none';
          var cn=document.getElementById('cc-casenum');
          if(cn){cn.style.transition='background .15s';cn.style.background='#fffbe6';setTimeout(function(){cn.style.background='';},900);}
        });
        item.addEventListener('mouseenter',function(){item.style.background='#fdf6e3';});
        item.addEventListener('mouseleave',function(){item.style.background='';});
        drop.appendChild(item);
      });
      drop.style.display='block';
    }
    inputEl.addEventListener('input',function(){render(this.value);});
    inputEl.addEventListener('focus',function(){if(this.value.trim())render(this.value);});
    inputEl.addEventListener('blur',function(){setTimeout(function(){drop.style.display='none';},160);});
    inputEl.addEventListener('keydown',function(e){
      var items=Array.from(drop.querySelectorAll('div'));
      var idx=items.findIndex(function(i){return i.hasAttribute('data-sel');});
      if(e.key==='ArrowDown'){e.preventDefault();if(idx>=0){items[idx].removeAttribute('data-sel');items[idx].style.background='';}var nxt=items[(idx+1)%items.length];if(nxt){nxt.setAttribute('data-sel','1');nxt.style.background='#fdf6e3';nxt.scrollIntoView({block:'nearest'});}}
      else if(e.key==='ArrowUp'){e.preventDefault();if(idx>=0){items[idx].removeAttribute('data-sel');items[idx].style.background='';}var prv=items[(idx-1+items.length)%items.length];if(prv){prv.setAttribute('data-sel','1');prv.style.background='#fdf6e3';prv.scrollIntoView({block:'nearest'});}}
      else if(e.key==='Enter'&&idx>=0){e.preventDefault();items[idx].dispatchEvent(new MouseEvent('mousedown'));}
      else if(e.key==='Escape'){drop.style.display='none';}
    });
  }

  /* ── Saved Cases search bar ──────────────────────────────── */

  function installSavedCasesSearch() {
    var savedPanel = document.getElementById('cc-tab-list');
    if (!savedPanel || document.getElementById('bhq-case-search')) return;
    var wrap = document.createElement('div');
    wrap.style.cssText = 'padding:12px 24px 8px;border-bottom:1px solid #e8dfc8;';
    wrap.innerHTML = '<input id="bhq-case-search" type="text" placeholder="🔍  Search cases by name or number…" style="width:100%;box-sizing:border-box;padding:8px 12px;border:1px solid #c9a84c;border-radius:5px;font-size:13px;font-family:inherit;outline:none;background:#fffef8;">';
    savedPanel.insertBefore(wrap, savedPanel.firstChild);
    document.getElementById('bhq-case-search').addEventListener('input', function () {
      var q = this.value.toLowerCase().trim();
      var list = document.getElementById('cc-cases-list');
      if (!list) return;
      Array.from(list.children).forEach(function (row) {
        row.style.display = (!q || row.textContent.toLowerCase().includes(q)) ? '' : 'none';
      });
    });
  }

  /* ── Boot ────────────────────────────────────────────────── */

  // Poll for CC panel elements
  var attempts = 0;
  var iv = setInterval(function () {
    installCCTypeahead();
    installSavedCasesSearch();
    installOnForm();
    if (++attempts > 60) clearInterval(iv);
  }, 500);

  // Hook openModal so every doc form gets the typeahead on open
  var _mwrap = setInterval(function () {
    if (typeof window.openModal === 'function' && !window.openModal._bhqACWrapped) {
      var origM = window.openModal;
      window.openModal = function () {
        origM.apply(this, arguments);
        setTimeout(installOnForm, 120);
      };
      window.openModal._bhqACWrapped = true;
      clearInterval(_mwrap);
    }
  }, 100);

  // Hook CC panel open
  var _cwrap = setInterval(function () {
    if (typeof window.ccOpenPanel === 'function' && !window.ccOpenPanel._bhqACWrapped) {
      var orig = window.ccOpenPanel;
      window.ccOpenPanel = function () {
        orig.apply(this, arguments);
        setTimeout(function () { installCCTypeahead(); installSavedCasesSearch(); }, 80);
      };
      window.ccOpenPanel._bhqACWrapped = true;
      clearInterval(_cwrap);
    }
  }, 100);

  // MutationObserver on modal for extra reliability
  var overlay = document.querySelector('.modal-overlay');
  if (overlay) {
    new MutationObserver(function () { setTimeout(installOnForm, 80); })
      .observe(overlay, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });
  }

})();
