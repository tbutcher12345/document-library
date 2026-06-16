/* ============================================================
   CASE AUTOCOMPLETE — Typeahead search for Document Engine
   Adds live search to cc-debtor1 (New Case tab) and a
   search bar to the Saved Cases tab.
   Version: 1.0 — 2026-06-16
============================================================ */
(function () {
  var DROPDOWN_ID = 'bhq-autocomplete-dropdown';

  function escHtml(str) {
    return str.replace(/[&<>"']/g, function (m) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m];
    });
  }

  function installTypeahead() {
    var debtor1 = document.getElementById('cc-debtor1');
    if (!debtor1 || document.getElementById(DROPDOWN_ID)) return;

    var wrapper = debtor1.parentElement;
    wrapper.style.position = 'relative';

    var dropdown = document.createElement('div');
    dropdown.id = DROPDOWN_ID;
    dropdown.style.cssText = [
      'position:absolute', 'top:100%', 'left:0', 'right:0', 'z-index:9999',
      'background:#fff', 'border:1px solid #c9a84c', 'border-top:none',
      'border-radius:0 0 6px 6px', 'box-shadow:0 8px 24px rgba(0,0,0,.18)',
      'max-height:240px', 'overflow-y:auto', 'display:none',
      'font-family:inherit', 'font-size:13px'
    ].join(';');
    wrapper.appendChild(dropdown);

    function buildDropdown(query) {
      var q = query.toLowerCase().trim();
      if (!q) { dropdown.style.display = 'none'; return; }
      var cases = window.ccGetAll ? window.ccGetAll() : [];
      var matches = cases.filter(function (c) {
        return (c.debtor_name || '').toLowerCase().includes(q) ||
               (c.debtor2_name || '').toLowerCase().includes(q) ||
               (c.case_number || '').toLowerCase().includes(q);
      }).slice(0, 12);
      if (!matches.length) { dropdown.style.display = 'none'; return; }
      dropdown.innerHTML = '';
      matches.forEach(function (c) {
        var item = document.createElement('div');
        item.style.cssText = 'padding:9px 14px;cursor:pointer;border-bottom:1px solid #f0e8d8;display:flex;justify-content:space-between;align-items:center;';
        item.innerHTML =
          '<span style="font-weight:600;color:#2a1f0f;">' + escHtml(c.debtor_name || '') +
          (c.debtor2_name ? '<span style="color:#7a6a4f;font-weight:400;"> & ' + escHtml(c.debtor2_name) + '</span>' : '') +
          '</span>' +
          '<span style="color:#8b6914;font-size:11px;margin-left:12px;white-space:nowrap;">' +
          escHtml(c.case_number || '') + '  ·  Ch. ' + escHtml(c.chapter || '7') +
          '</span>';
        item.addEventListener('mousedown', function (e) { e.preventDefault(); fillCase(c); });
        item.addEventListener('mouseenter', function () { item.style.background = '#fdf6e3'; });
        item.addEventListener('mouseleave', function () { item.style.background = ''; });
        dropdown.appendChild(item);
      });
      dropdown.style.display = 'block';
    }

    function fillCase(c) {
      var fields = {
        'cc-joint': c.joint_filing || 'single',
        'cc-debtor1': c.debtor_name || '',
        'cc-debtor2': c.debtor2_name || '',
        'cc-casenum': c.case_number || '',
        'cc-chapter': c.chapter || '7',
        'cc-trustee': c.trustee_name || '',
        'cc-addr1': c.client_address1 || '',
        'cc-addr2': c.client_address2 || '',
        'cc-email': c.client_email || '',
        'cc-phone': c.client_phone || ''
      };
      Object.keys(fields).forEach(function (id) {
        var el = document.getElementById(id);
        if (el) el.value = fields[id];
      });
      if (typeof ccToggleJoint === 'function') ccToggleJoint(c.joint_filing || 'single');
      dropdown.style.display = 'none';
      debtor1.focus();
      var cn = document.getElementById('cc-casenum');
      if (cn) {
        cn.style.transition = 'background .15s';
        cn.style.background = '#fffbe6';
        setTimeout(function () { cn.style.background = ''; }, 900);
      }
    }

    debtor1.addEventListener('input', function () { buildDropdown(this.value); });
    debtor1.addEventListener('focus', function () { if (this.value.trim()) buildDropdown(this.value); });
    debtor1.addEventListener('blur', function () { setTimeout(function () { dropdown.style.display = 'none'; }, 150); });
    debtor1.addEventListener('keydown', function (e) {
      var items = Array.from(dropdown.querySelectorAll('div'));
      var idx = items.findIndex(function (i) { return i.hasAttribute('data-sel'); });
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (idx >= 0) { items[idx].removeAttribute('data-sel'); items[idx].style.background = ''; }
        var next = items[(idx + 1) % items.length];
        if (next) { next.setAttribute('data-sel', '1'); next.style.background = '#fdf6e3'; next.scrollIntoView({ block: 'nearest' }); }
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (idx >= 0) { items[idx].removeAttribute('data-sel'); items[idx].style.background = ''; }
        var prev = items[(idx - 1 + items.length) % items.length];
        if (prev) { prev.setAttribute('data-sel', '1'); prev.style.background = '#fdf6e3'; prev.scrollIntoView({ block: 'nearest' }); }
      } else if (e.key === 'Enter' && idx >= 0) {
        e.preventDefault();
        items[idx].dispatchEvent(new MouseEvent('mousedown'));
      } else if (e.key === 'Escape') {
        dropdown.style.display = 'none';
      }
    });
  }

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

  // Poll until the panel DOM is ready
  var attempts = 0;
  var iv = setInterval(function () {
    installTypeahead();
    installSavedCasesSearch();
    if (++attempts > 60) clearInterval(iv);
  }, 500);

  // Re-install when the panel opens (in case DOM is rebuilt)
  var _wrap = setInterval(function () {
    if (typeof window.ccOpenPanel === 'function' && !window.ccOpenPanel._autocompleteWrapped) {
      var orig = window.ccOpenPanel;
      window.ccOpenPanel = function () {
        orig.apply(this, arguments);
        setTimeout(function () { installTypeahead(); installSavedCasesSearch(); }, 80);
      };
      window.ccOpenPanel._autocompleteWrapped = true;
      clearInterval(_wrap);
    }
  }, 300);

})();
