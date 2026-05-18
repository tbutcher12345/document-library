// ============================================================
// ECF / CM-ECF INTEGRATION — Butcher Law Office DEE
// Oregon Bankruptcy Court: ecf.orb.uscourts.gov
// ============================================================

(function () {
    'use strict';

   var ECF_BASE     = 'https://ecf.orb.uscourts.gov';
    var ECF_FILE_URL = ECF_BASE + '/cgi-bin/login.pl';

   // ----------------------------------------------------------
   // STYLES
   // ----------------------------------------------------------
   var style = document.createElement('style');
    style.textContent = [
          '.btn-ecf{font-family:"Instrument Sans",sans-serif;font-size:13px;font-weight:600;color:#fff;background:#1a3a5c;border:none;padding:10px 22px;border-radius:2px;cursor:pointer;display:inline-flex;align-items:center;gap:7px;text-decoration:none;transition:background .15s}',
          '.btn-ecf:hover{background:#24527e}',
          '.ecf-checklist-wrap{position:relative;display:inline-block}',
          '.ecf-checklist{display:none;position:absolute;bottom:calc(100% + 8px);left:50%;transform:translateX(-50%);background:#1a3a5c;color:#e8f0f8;border-radius:4px;padding:12px 16px;min-width:260px;font-size:12px;line-height:1.7;box-shadow:0 6px 24px rgba(0,0,0,.25);z-index:9999;pointer-events:none;white-space:nowrap}',
          '.ecf-checklist::after{content:"";position:absolute;top:100%;left:50%;transform:translateX(-50%);border:6px solid transparent;border-top-color:#1a3a5c}',
          '.ecf-checklist-wrap:hover .ecf-checklist,.ecf-checklist-wrap:focus-within .ecf-checklist{display:block}',
          '.ecf-checklist strong{display:block;color:#fff;margin-bottom:4px;font-size:11px;text-transform:uppercase;letter-spacing:.05em}',
          '.ecf-checklist li{list-style:none;padding-left:0}',
          '.ecf-checklist li::before{content:"\u2610 "}',
          '.ecf-card-pill{display:inline-flex;align-items:center;gap:4px;font-family:"Instrument Sans",sans-serif;font-size:10px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#1a3a5c;background:#dce8f4;border:1px solid #a8c4e0;border-radius:2px;padding:2px 7px;cursor:pointer;text-decoration:none;transition:background .12s,color .12s;white-space:nowrap;vertical-align:middle;margin-left:6px}',
          '.ecf-card-pill:hover{background:#1a3a5c;color:#fff;border-color:#1a3a5c}',
          '.ecf-divider{width:100%;border:none;border-top:1px solid var(--rule,#c8bfaa);margin:14px 0 10px}',
          '.ecf-label{font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted,#6b6355);margin-bottom:8px;text-align:center}'
        ].join('\n');
    document.head.appendChild(style);

   // ----------------------------------------------------------
   // ECF URL BUILDER
   // ----------------------------------------------------------
   function buildECFUrl(caseNum) {
         if (!caseNum || !caseNum.trim()) return ECF_FILE_URL;
         return ECF_BASE + '/cgi-bin/login.pl?next_page=' +
                 encodeURIComponent('/cgi-bin/DktRpt.pl?search_term1=' + caseNum.trim());
   }

   // ----------------------------------------------------------
   // SUCCESS PANEL — inject "File in ECF" button
   // ----------------------------------------------------------
   function injectECFSuccessButton() {
         var successPanel = document.getElementById('successPanel');
         var okActions    = successPanel && successPanel.querySelector('.ok-actions');
         if (!successPanel || !okActions) return;

      successPanel.querySelectorAll('.ecf-injected').forEach(function (el) { el.remove(); });

      var caseInput = document.getElementById('case_number');
         var caseNum   = caseInput ? caseInput.value.trim() : '';
         var ecfUrl    = buildECFUrl(caseNum);

      var divider       = document.createElement('hr');
         divider.className = 'ecf-divider ecf-injected';

      var label         = document.createElement('div');
         label.className   = 'ecf-label ecf-injected';
         label.textContent = 'Next step \u2014 file in CM/ECF';

      var wrap           = document.createElement('div');
         wrap.className     = 'ecf-checklist-wrap ecf-injected';
         wrap.style.cssText = 'display:inline-flex;flex-direction:column;align-items:center;';

      var checklist       = document.createElement('div');
         checklist.className = 'ecf-checklist';
         checklist.innerHTML = '<strong>Before you file:</strong><ul style="margin:0;padding:0;"><li>PDF is downloaded &amp; ready</li><li>Correct event type selected</li><li>Certificate of Service attached</li><li>Filing fee paid (if required)</li></ul>';

      var btn       = document.createElement('a');
         btn.className = 'btn-ecf';
         btn.href      = ecfUrl;
         btn.target    = '_blank';
         btn.rel       = 'noopener noreferrer';
         btn.title     = 'Open CM/ECF filing portal (D. Or.)';
         btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M7 2H3a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V9" stroke="white" stroke-width="1.5" stroke-linecap="round"/><path d="M10 2h4v4" stroke="white" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/><path d="M14 2L8 8" stroke="white" stroke-width="1.5" stroke-linecap="round"/></svg>File in ECF' + (caseNum ? ' \u00b7 ' + caseNum : ' (D. Or.)');

      var hint           = document.createElement('div');
         hint.style.cssText = 'font-size:10px;color:var(--muted);margin-top:5px;text-align:center;';
         hint.textContent   = 'Hover for pre-filing checklist';

      wrap.appendChild(checklist);
         wrap.appendChild(btn);
         wrap.appendChild(hint);
         okActions.after(divider, label, wrap);
   }

   // Watch for success panel becoming visible
   function watchSuccessPanel() {
         var successPanel = document.getElementById('successPanel');
         if (!successPanel) return;
         new MutationObserver(function () {
                 if (successPanel.offsetParent !== null) setTimeout(injectECFSuccessButton, 50);
         }).observe(successPanel, { attributes: true, attributeFilter: ['style', 'class', 'hidden'] });
   }

   // ----------------------------------------------------------
   // CARD PILLS — add ECF link to every court-filing card
   // ----------------------------------------------------------
   var SKIP_PREFIXES = ['letter_', 'agree_', 'lbf_'];
    var SKIP_IDS      = ['cos_address_builder'];

   function shouldShowPill(id) {
         if (!id) return false;
         if (SKIP_IDS.indexOf(id) !== -1) return false;
         for (var i = 0; i < SKIP_PREFIXES.length; i++) {
                 if (id.indexOf(SKIP_PREFIXES[i]) === 0) return false;
         }
         return true;
   }

   function addPill(card) {
         if (card.querySelector('.ecf-card-pill')) return;
         var meta = card.querySelector('.doc-meta');
         if (!meta) return;
         var pill    = document.createElement('a');
         pill.className = 'ecf-card-pill';
         pill.href      = ECF_FILE_URL;
         pill.target    = '_blank';
         pill.rel       = 'noopener noreferrer';
         pill.title     = 'Open CM/ECF \u2014 D. Or. filing portal';
         pill.innerHTML = 'ECF \u2197';
         pill.addEventListener('click', function (e) { e.stopPropagation(); });
         meta.appendChild(pill);
   }

   function addAllPills() {
         document.querySelectorAll('.doc-card[data-id]').forEach(function (card) {
                 if (shouldShowPill(card.dataset.id)) addPill(card);
         });
   }

   // Watch #docGrid for any renders/re-renders
   function watchGrid() {
         var grid = document.getElementById('docGrid');
         if (!grid) return;
         if (window._ecfGridObserver) window._ecfGridObserver.disconnect();
         window._ecfGridObserver = new MutationObserver(addAllPills);
         window._ecfGridObserver.observe(grid, { childList: true, subtree: true });
   }

   // ----------------------------------------------------------
   // INIT — run after DOM ready, then re-run after short delay
   // to catch any deferred rendering by the app
   // ----------------------------------------------------------
   function init() {
         watchGrid();
         addAllPills();
         watchSuccessPanel();
         // Safety net: re-run after 500ms in case app renders cards asynchronously
      setTimeout(function () {
              addAllPills();
      }, 500);
   }

   if (document.readyState === 'loading') {
         document.addEventListener('DOMContentLoaded', init);
   } else {
         init();
   }

})();
