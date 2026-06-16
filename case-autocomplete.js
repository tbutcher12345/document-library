/* ============================================================
   CASE AUTOCOMPLETE v2.0 — Butcher Law Document Engine
   1. Typeahead on cc-debtor1 (Case Context panel)
   2. Search bar on Saved Cases tab
   3. Typeahead on client_name in document forms → auto-fills
      case_number, debtor2_name, address fields from saved cases
   2026-06-16
============================================================ */
(function () {

  /* ── Shared helpers ─────────────────────────────────────── */

  function escHtml(str) {
    return String(str || '').replace(/[&<>"']/g, function (m) {
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m];
    });
  }

  function getCases() {
    return (typeof window.ccGetAll === 'function') ? window.ccGetAll() : [];
  }

  function makeDropdown(anchorEl, onSelect) {
    var existing = anchorEl.parentElement.querySelector('.bhq-ac-drop');
    if (existing) existing.remove();

    var drop = document.createElement('div');
    drop.className = 'bhq-ac-drop';
    drop.style.cssText = [
      'position:absolute','top:100%','left:0','right:0','z-index:99999',
      'background:#fff','border:1px solid #c9a84c','border-top:none',
      'border-radius:0 0 6px 6px','box-shadow:0 8px 24px rgba(0,0,0,.2)',
      'max-height:260px','overflow-y:auto','display:none',
      'font-family:inherit','font-size:13px'
    ].join(';');

    anchorEl.parentElement.style.position = 'relative';
    anchorEl.parentElement.appendChild(drop);

    function render(query) {
      var q = query.toLowerCase().trim();
      if (!q) { drop.style.display = 'none'; return; }
      var matches = getCases().filter(function (c) {
        return (c.debtor_name||'').toLowerCase().includes(q) ||
               (c.debtor2_name||'').toLowerCase().includes(q) ||
               (c.case_number||'').toLowerCase().includes(q);
      }).slice(0, 12);
      if (!matches.length) { drop.style.display = 'none'; return; }

      drop.innerHTML = '';
      matches.forEach(function (c) {
        var item = document.createElement('div');
        item.style.cssText = 'padding:9px 14px;cursor:pointer;border-bottom:1px solid #f0e8d8;display:flex;justify-content:space-between;align-items:center;line-height:1.3;';
        item.innerHTML =
          '<span style="font-weight:600;color:#2a1f0f;">' + escHtml(c.debtor_name) +
          (c.debtor2_name ? '<span style="color:#7a6a4f;font-weight:400;"> & ' + escHtml(c.debtor2_name) + '</span>' : '') +
          '</span>' +
          '<span style="color:#8b6914;font-size:11px;margin-left:12px;white-space:nowrap;flex-shrink:0;">' +
          escHtml(c.case_number) + ' · Ch. ' + escHtml(c.chapter||'7') + '</span>';
        item.addEventListener('mousedown', function (e) { e.preventDefault(); onSelect(c); drop.style.display = 'none'; });
        item.addEventListener('mouseenter', function () { item.style.background = '#fdf6e3'; });
        item.addEventListener('mouseleave', function () { item.style.background = ''; });
        drop.appendChild(item);
      });
      drop.style.display = 'block';
    }

    anchorEl.addEventListener('input', function () { render(this.value); });
    anchorEl.addEventListener('focus', function () { if (this.value.trim()) render(this.value); });
    anchorEl.addEventListener('blur',  function () { setTimeout(function () { drop.style.display = 'none'; }, 160); });
    anchorEl.addEventListener('keydown', function (e) {
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

    return drop;
  }

  /* ── 1. Case Context panel: cc-debtor1 typeahead ───────── */

  function installCCTypeahead() {
    var debtor1 = document.getElementById('cc-debtor1');
    if (!debtor1 || debtor1._bhqAC) return;
    debtor1._bhqAC = true;

    makeDropdown(debtor1, function (c) {
      var set = function (id, val) { var el = document.getElementById(id); if (el) el.value = val; };
      set('cc-debtor1',  c.debtor_name    || '');
      set('cc-debtor2',  c.debtor2_name   || '');
      set('cc-casenum',  c.case_number    || '');
      set('cc-chapter',  c.chapter        || '7');
      set('cc-trustee',  c.trustee_name   || '');
      set('cc-addr1',    c.client_address1|| '');
      set('cc-addr2',    c.client_address2|| '');
      set('cc-email',    c.client_email   || '');
      set('cc-phone',    c.client_phone   || '');
      var joint = document.getElementById('cc-joint');
      if (joint) { joint.value = c.joint_filing || 'single'; if (typeof ccToggleJoint === 'function') ccToggleJoint(joint.value); }
      debtor1.focus();
      var cn = document.getElementById('cc-casenum');
      if (cn) { cn.style.transition = 'background .15s'; cn.style.background = '#fffbe6'; setTimeout(function () { cn.style.background = ''; }, 900); }
    });
  }

  /* ── 2. Saved Cases tab: search bar ────────────────────── */

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

  /* ── 3. Document form: client_name typeahead ────────────── */

  function installDocFormTypeahead() {
    var clientName = document.getElementById('client_name');
    if (!clientName || clientName._bhqAC) return;
    clientName._bhqAC = true;

    makeDropdown(clientName, function (c) {
      // Fill the document form fields
      var set = function (id, val) { var el = document.getElementById(id); if (el && val) el.value = val; };
      clientName.value = c.debtor_name || '';
      set('debtor2_name', c.debtor2_name   || '');
      set('case_number',  c.case_number    || '');

      // Fill address if field exists
      set('client_address', (c.client_address1 || '') + (c.client_address2 ? ', ' + c.client_address2 : ''));

      // Joint filing dropdown
      var joint = document.getElementById('joint_filing');
      if (joint) joint.value = (c.joint_filing === 'joint') ? 'joint' : 'single';

      // Flash the case number field to confirm
      var cn = document.getElementById('case_number');
      if (cn) {
        cn.style.transition = 'background .15s';
        cn.style.background = '#fffbe6';
        setTimeout(function () { cn.style.background = ''; }, 900);
      }

      clientName.focus();
    });
  }

  /* ── Observe document form opens (modal is reused) ──────── */

  var modalObserver = new MutationObserver(function () {
    installDocFormTypeahead();
  });

  var overlay = document.querySelector('.modal-overlay');
  if (overlay) {
    modalObserver.observe(overlay, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });
  }

  /* ── Boot: poll for CC panel + run doc form check ───────── */

  var attempts = 0;
  var iv = setInterval(function () {
    installCCTypeahead();
    installSavedCasesSearch();
    installDocFormTypeahead();
    if (++attempts > 60) clearInterval(iv);
  }, 500);

  // Re-hook when CC panel opens (may rebuild DOM)
  var _wrap = setInterval(function () {
    if (typeof window.ccOpenPanel === 'function' && !window.ccOpenPanel._bhqACWrapped) {
      var orig = window.ccOpenPanel;
      window.ccOpenPanel = function () {
        orig.apply(this, arguments);
        setTimeout(function () { installCCTypeahead(); installSavedCasesSearch(); }, 80);
      };
      window.ccOpenPanel._bhqACWrapped = true;
      clearInterval(_wrap);
    }
  }, 300);

  // Re-hook when a doc modal opens (openModal is called each time)
  var _mwrap = setInterval(function () {
    if (typeof window.openModal === 'function' && !window.openModal._bhqACWrapped) {
      var origM = window.openModal;
      window.openModal = function () {
        origM.apply(this, arguments);
        setTimeout(installDocFormTypeahead, 120);
      };
      window.openModal._bhqACWrapped = true;
      clearInterval(_mwrap);
    }
  }, 300);

})();
