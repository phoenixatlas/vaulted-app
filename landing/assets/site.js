
    // Waitlist form → POST /api/waitlist/join → Resend Contacts + Mongo
    // Backend defaults to the live Render production API — the SAME
    // backend the mobile/web admin dashboard reads from, so every form
    // submission from phoenix-atlas.com lands in the same MongoDB the
    // admin page is reading. (Historical note: this used to default to
    // the Emergent-hosted preview URL which caused a split-brain where
    // signups went to a preview DB and never showed up in prod admin.)
    //
    // Override with `window.__VAULTED_API_BASE__` before this script
    // loads if you need to repoint at a different backend. If you ever
    // switch backends again, make sure the new backend's CORS_ALLOW_ORIGINS
    // env var includes phoenix-atlas.com (and any preview subdomain)
    // or the browser will reject preflights and users see "Network hiccup".
    var WAITLIST_API_BASE = (window.__VAULTED_API_BASE__ || 'https://vaulted-app.onrender.com').replace(/\/+$/, '');

    // Track ref code from ?ref=CODE URL param → validate → show banner on
    // the waitlist form to signal social proof + explain the reward.
    var REFERRAL_CODE = (function () {
      try {
        var params = new URLSearchParams(window.location.search);
        var raw = params.get('ref');
        return raw ? raw.trim().toUpperCase().slice(0, 16) : '';
      } catch (_) { return ''; }
    })();

    async function hydrateReferralBanner() {
      if (!REFERRAL_CODE) return;
      try {
        var res = await fetch(WAITLIST_API_BASE + '/api/waitlist/refer/' + encodeURIComponent(REFERRAL_CODE));
        if (!res.ok) return;
        var body = await res.json();
        if (!body.ok) return;
        var host = document.getElementById('referral-banner');
        if (!host) return;
        var referrer = body.referrer || 'a friend';
        host.innerHTML =
          '<div style="background: linear-gradient(135deg, var(--gold) 0%, var(--gold-deep) 100%); color: #0F0B08; padding: 12px 18px; border-radius: 12px; font-size: 13px; font-weight: 700; text-align: center; margin: 12px auto 20px; max-width: 480px;">' +
          '\u{1F389} You&rsquo;ve been referred by <span style="text-decoration: underline;">' + referrer + '</span>. ' +
          'Join to both move up the queue.' +
          '</div>';
        host.style.display = 'block';
      } catch (_) {}
    }
    document.addEventListener('DOMContentLoaded', hydrateReferralBanner);

    // Track current direction for the corridor filter + POST body.
    var CURRENT_DIRECTION = 'outbound';

    function updateDirection(input) {
      CURRENT_DIRECTION = input.value === 'inbound' ? 'inbound' : 'outbound';
      // Toggle visual pill state
      var pills = document.querySelectorAll('.dir-pill');
      pills.forEach(function (p) {
        var active = p.getAttribute('data-dir') === CURRENT_DIRECTION;
        p.classList.toggle('dir-pill-active', active);
        p.style.background = active ? 'var(--gold)' : 'transparent';
        p.style.color = active ? '#0F0B08' : 'var(--text-muted)';
      });
      // Filter the corridor <select> options — show only ones matching direction
      var sel = document.getElementById('waitlist-corridor');
      if (!sel) return;
      var previous = sel.value;
      Array.prototype.forEach.call(sel.options, function (opt) {
        var m = opt.getAttribute('data-mode') || 'both';
        opt.hidden = !(m === 'both' || m === CURRENT_DIRECTION);
      });
      // Reset selection if the previously chosen option is now hidden
      if (!previous || sel.options[sel.selectedIndex].hidden) {
        sel.selectedIndex = 0;
      }
      // Update placeholder copy based on direction
      var placeholder = sel.querySelector('option[value=""]');
      if (placeholder) {
        placeholder.textContent = CURRENT_DIRECTION === 'inbound'
          ? 'Where are you sending money from?'
          : 'Where are you sending money to?';
      }
    }

    // Initialize on load to apply the default outbound filter
    document.addEventListener('DOMContentLoaded', function () {
      var checked = document.querySelector('input[name="direction"]:checked');
      if (checked) updateDirection(checked);
      // Add pill active style rules
      var s = document.createElement('style');
      s.textContent = '.dir-pill-active { background: var(--gold) !important; color: #0F0B08 !important; }';
      document.head.appendChild(s);
    });

    async function handleWaitlist(e) {
      e.preventDefault();
      var input = document.getElementById('waitlist-email');
      var corridorEl = document.getElementById('waitlist-corridor');
      var btn = document.getElementById('waitlist-btn');
      var msg = document.getElementById('waitlist-msg');
      var email = (input.value || '').trim();
      var corridor = (corridorEl && corridorEl.value ? corridorEl.value : '').trim();
      if (!email) return false;

      // Basic client-side email sanity (server re-validates).
      // Catch the common typos *before* bothering the server so the user
      // gets instant feedback and we don't trigger server-side rate limits.
      var emailOk = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
        && !/\.\./.test(email)                 // no double-dots
        && !/@-/.test(email)                   // no hyphen right after @
        && !/-\./.test(email.split('@')[1] || '') // no "-." in domain
        && !/\.$/.test(email)                  // no trailing dot
        && email.indexOf(',') === -1           // no stray commas
        && email.length <= 254;                // RFC 5321 cap
      if (!emailOk) {
        msg.style.color = '#ff8a80';
        msg.textContent = 'That doesn\u2019t look like a valid email address.';
        return false;
      }
      if (!corridor) {
        msg.style.color = '#ff8a80';
        msg.textContent = CURRENT_DIRECTION === 'inbound'
          ? 'Please pick where you\u2019re sending FROM.'
          : 'Please pick a destination so we can invite you at launch.';
        return false;
      }

      btn.disabled = true;
      var origLabel = btn.textContent;
      btn.textContent = 'Joining\u2026';
      msg.style.color = 'var(--gold-light)';
      msg.textContent = '';

      try {
        var res = await fetch(WAITLIST_API_BASE + '/api/waitlist/join', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            email: email,
            corridor: corridor,
            direction: CURRENT_DIRECTION,
            source: CURRENT_DIRECTION === 'inbound' ? 'landing-reverse' : 'landing',
            ref: REFERRAL_CODE || undefined,
          })
        });
        var data = {};
        try { data = await res.json(); } catch (_) {}

        if (res.ok && data && data.ok) {
          msg.style.color = 'var(--gold-light)';
          // Build a richer success message with position + share link
          var pos = data.position;
          var total = data.total;
          var refCode = data.referral_code;
          var shareLink = refCode ? 'https://phoenix-atlas.com/?ref=' + refCode : '';
          var greeting = data.already_joined
            ? 'You\u2019re already on the list \u2014 we\u2019ll be in touch.'
            : 'You\u2019re on the list. Check your inbox for a confirmation.';
          if (pos && total) {
            msg.innerHTML =
              '<div style="text-align:center;">' +
                '<div style="font-size: 15px; font-weight: 700; color: var(--gold-light); margin-bottom: 8px;">' +
                  greeting + ' \u2728' +
                '</div>' +
                '<div style="display: inline-block; padding: 10px 18px; background: #0F0B08; border-radius: 12px; border: 1px solid rgba(201,163,91,0.35); margin-bottom: 10px;">' +
                  '<div style="font-size: 11px; color: var(--gold); letter-spacing: 1.2px; font-weight: 700; margin-bottom: 4px;">YOUR SPOT</div>' +
                  '<div style="font-size: 26px; font-weight: 800; color: var(--gold-cream); letter-spacing: -0.5px;">#' + pos.toLocaleString() + '</div>' +
                  '<div style="font-size: 10px; color: var(--gold); opacity: 0.75; margin-top: 4px;">of ' + total.toLocaleString() + '</div>' +
                '</div>' +
                (shareLink ?
                  '<div style="font-size: 12px; color: var(--text-secondary); margin-top: 10px;">' +
                    'Skip the queue \u2014 every 3 referrals moves you up 25 spots.<br>' +
                    '<code style="background: rgba(201,163,91,0.1); padding: 6px 10px; border-radius: 8px; margin-top: 8px; display: inline-block; font-size: 12px; color: var(--gold-cream);">' + shareLink + '</code>' +
                    '<button onclick="navigator.clipboard && navigator.clipboard.writeText(\'' + shareLink + '\').then(function(){this.textContent=\'Copied!\'}.bind(this))" style="margin-left: 8px; padding: 6px 12px; background: var(--gold); color: #0F0B08; border: 0; border-radius: 999px; font-size: 11px; font-weight: 700; cursor: pointer;">Copy link</button>' +
                  '</div>' : '') +
              '</div>';
          } else {
            msg.textContent = greeting + ' \u2728';
          }
          input.value = '';
          if (corridorEl) corridorEl.selectedIndex = 0;
        } else if (res.status === 429) {
          msg.style.color = '#ff8a80';
          msg.textContent = 'Please wait a moment before trying again.';
        } else if (res.status === 400) {
          msg.style.color = '#ff8a80';
          var detail400 = (data && typeof data.detail === 'string') ? data.detail : '';
          msg.textContent = detail400 || 'Please check the email address.';
        } else if (res.status === 422) {
          // FastAPI validation error — detail is a *list* of
          // {loc, msg, type} objects. Pull a user-friendly line.
          msg.style.color = '#ff8a80';
          var friendly = 'Please enter a valid email address.';
          try {
            if (data && Array.isArray(data.detail) && data.detail.length) {
              var first = data.detail[0] || {};
              var loc = (first.loc || []).join('.');
              var raw = (first.msg || '').toString();
              // Strip the "value is not a valid email address: " prefix
              // Pydantic prepends so the user sees the actionable bit.
              raw = raw.replace(/^value is not a valid email address:\s*/i, '');
              if (loc.indexOf('email') !== -1) {
                friendly = 'That email didn\u2019t pass validation' + (raw ? ' \u2014 ' + raw : '.');
              } else if (raw) {
                friendly = raw;
              }
            }
          } catch (_) {}
          msg.textContent = friendly;
        } else {
          msg.style.color = '#ff8a80';
          msg.textContent = 'Couldn\u2019t sign you up right now \u2014 please try again in a moment.';
        }
      } catch (err) {
        msg.style.color = '#ff8a80';
        msg.textContent = 'Network hiccup \u2014 please try again.';
      } finally {
        btn.disabled = false;
        btn.textContent = origLabel;
      }
      return false;
    }
  

    // Investor one-pager form → POST /api/investor/onepager/request →
    // signed download URL. Same API base as the waitlist form.
    async function handleInvestor(e) {
      return await _investorSubmit(e, 'onepager');
    }
    async function requestDeck(e) {
      return await _investorSubmit(e, 'deck');
    }
    async function _investorSubmit(e, kind) {
      e.preventDefault();
      var btn = document.getElementById('inv-btn');
      var name = (document.getElementById('inv-name').value || '').trim();
      var email = (document.getElementById('inv-email').value || '').trim();
      var company = (document.getElementById('inv-company').value || '').trim();
      var role = (document.getElementById('inv-role').value || '').trim();
      var note = (document.getElementById('inv-note').value || '').trim();
      if (!email || !name) {
        alert('Please fill in your name and work email above first.');
        return false;
      }
      var orig = btn.textContent;
      btn.disabled = true;
      btn.textContent = kind === 'deck' ? 'Building your deck\u2026' : 'Building your PDF\u2026';
      var endpoint = kind === 'deck' ? '/api/investor/deck/request' : '/api/investor/onepager/request';
      // iOS Safari note: we intentionally DO NOT call window.open() after
      // the awaited fetch. Safari treats popups from post-await code as
      // programmatic (not user-initiated) and blocks them, which was
      // surfacing an "aborted" state to investors. Instead, we swap the
      // form for a success card with a first-class "Open the deck" button
      // that stays inside a fresh user-gesture when tapped.
      var errMsg = null;
      var respStatus = null;
      var body = null;
      try {
        var res = await fetch(WAITLIST_API_BASE + endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: email, name: name, company: company, role: role, note: note, source: 'landing-investor-' + kind })
        });
        respStatus = res.status;
        if (!res.ok) {
          var txt = '';
          try { txt = (await res.text()).slice(0, 200); } catch (_) {}
          throw new Error('Server returned ' + res.status + (txt ? (' — ' + txt) : ''));
        }
        try {
          body = await res.json();
        } catch (parseErr) {
          throw new Error('Server response was not JSON (' + (parseErr && parseErr.message ? parseErr.message : 'parse error') + ')');
        }
        if (!body || !body.download_url) {
          throw new Error('Server response missing download_url');
        }
        var url = WAITLIST_API_BASE + body.download_url;
        document.getElementById('investor-form-wrap').style.display = 'none';
        var done = document.getElementById('investor-done');
        done.style.display = 'block';
        var openBtn = document.getElementById('inv-download-btn');
        openBtn.href = url;
        openBtn.textContent = kind === 'deck' ? 'Open the deck →' : 'Open the PDF →';
        // Update copy so the user knows they need to tap the button.
        try {
          var doneTitle = done.querySelector('[data-role="done-title"]');
          var doneSub = done.querySelector('[data-role="done-sub"]');
          if (doneTitle) doneTitle.textContent = kind === 'deck' ? 'Your 5-page deck is ready.' : 'Your one-pager is ready.';
          if (doneSub) doneSub.textContent = 'A copy has been emailed to you. Tap below to open it in a new tab.';
        } catch (_) {}
        // Scroll the success card into view so investors on mobile see it.
        try { done.scrollIntoView({ behavior: 'smooth', block: 'center' }); } catch (_) {}
      } catch (err) {
        errMsg = (err && err.message) ? err.message : String(err);
      }
      if (errMsg) {
        btn.disabled = false;
        btn.textContent = orig;
        // Show the specific server/network reason so investors + our logs
        // both get actionable signal. Keeps the friendly fallback email.
        var label = kind === 'deck' ? 'deck' : 'one-pager';
        var extra = respStatus ? (' (status ' + respStatus + ')') : '';
        alert('Could not build your ' + label + ' right now' + extra + '.\n\n' + errMsg + '\n\nPlease try again in a moment, or email invest@phoenix-atlas.com.');
      }
      return false;
    }
  

    // Central booking URL for Umar's Google Calendar appointment schedule.
    // Referenced from every "Book a call" CTA on the page. Change this in
    // one place to swap schedulers (Calendly, Cal.com, etc.) later.
    window.VAULTED_BOOK_URL = 'https://calendar.app.google/U1r2UbqrQqQCxQrcA';

    function openBookingModal(source) {
      var m = document.getElementById('book-modal');
      if (!m) return;
      m.setAttribute('aria-hidden', 'false');
      document.body.classList.add('book-modal-open');
      _bookingCtaFired(source || 'unknown');
      // Trap focus on the open-calendar CTA for keyboard users
      setTimeout(function() {
        var btn = document.getElementById('book-modal-open');
        if (btn) btn.focus();
      }, 60);
    }
    function closeBookingModal() {
      var m = document.getElementById('book-modal');
      if (!m) return;
      m.setAttribute('aria-hidden', 'true');
      document.body.classList.remove('book-modal-open');
    }
    // ESC to close
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape') {
        var m = document.getElementById('book-modal');
        if (m && m.getAttribute('aria-hidden') === 'false') closeBookingModal();
      }
    });
    // Light-touch attribution — send a beacon so we can see which CTA
    // is warming leads best. Non-blocking, no PII, silent on error.
    function _bookingCtaFired(source) {
      try {
        var base = (window.__VAULTED_API_BASE__ || '');
        var payload = JSON.stringify({ source: String(source || 'unknown').slice(0, 40) });
        if (navigator.sendBeacon) {
          navigator.sendBeacon(base + '/api/investor/book-click', new Blob([payload], { type: 'application/json' }));
        } else {
          fetch(base + '/api/investor/book-click', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: payload, keepalive: true,
          }).catch(function(){});
        }
      } catch (err) { /* swallow — attribution is optional */ }
    }
  

// Keep the fixed header + mobile menu exactly below the (wrapping) pre-auth banner.
function layoutChrome() {
  var b = document.querySelector('.preauth-banner'), h = document.querySelector('header'), m = document.getElementById('mobile-menu');
  if (!b || !h) return;
  var bh = b.offsetHeight;
  h.style.top = bh + 'px';
  document.body.style.paddingTop = bh + 'px';
  if (m) m.style.top = (bh + h.offsetHeight) + 'px';
}
window.addEventListener('resize', layoutChrome);
document.addEventListener('DOMContentLoaded', layoutChrome);
function toggleMenu(force) {
  layoutChrome();
  var open = typeof force === 'boolean' ? force : !document.body.classList.contains('menu-open');
  document.body.classList.toggle('menu-open', open);
  var b = document.getElementById('menu-toggle');
  if (b) { b.setAttribute('aria-expanded', String(open)); b.textContent = open ? '\u2715' : '\u2630'; }
}
document.addEventListener('keydown', function (e) { if (e.key === 'Escape') toggleMenu(false); });
// Old one-page anchors (phoenix-atlas.com/#pricing etc.) -> new pages.
(function () {
  var moved = {'#corridors': '/corridors', '#reverse': '/africa-to-uk', '#features': '/send-money-to-africa#features',
    '#who-its-for': '/send-money-to-africa#who-its-for', '#compare': '/pricing#compare', '#pricing': '/pricing',
    '#security': '/security', '#invest': '/investors#invest'};
  if ((location.pathname === '/' || location.pathname === '/index.html') && moved[location.hash]) location.replace(moved[location.hash]);
})();
