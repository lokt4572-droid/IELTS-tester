
(function () {
  var root = document.documentElement;
 
  /* ---- dark / light theme (choice is remembered in this browser) ---- */
  var themeBtn = document.getElementById('theme-toggle');
  function systemDark() {
    return !!(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
  }
  function currentTheme() {
    return root.getAttribute('data-theme') || (systemDark() ? 'dark' : 'light');
  }
  function paintThemeBtn() {
    if (!themeBtn) return;
    var dark = currentTheme() === 'dark';
    themeBtn.setAttribute('aria-pressed', dark ? 'true' : 'false');
    var label = dark ? 'Switch to light mode' : 'Switch to dark mode';
    themeBtn.setAttribute('aria-label', label);
    themeBtn.title = label;
  }
  if (themeBtn) {
    paintThemeBtn();
    themeBtn.addEventListener('click', function () {
      var next = currentTheme() === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      try { localStorage.setItem('theme', next); } catch (e) { /* private mode: ignore */ }
      paintThemeBtn();
    });
  }
 
  /* ---- mobile menu ---- */
  var navBtn = document.getElementById('nav-toggle');
  var nav = document.getElementById('site-nav');
  if (navBtn && nav) {
    navBtn.addEventListener('click', function () {
      var open = nav.classList.toggle('open');
      navBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  }
 
  /* ---- mark the current page in the menu (longest matching link wins) ---- */
  if (nav) {
    var path = window.location.pathname;
    var best = null, bestLen = 0;
    Array.prototype.slice.call(nav.querySelectorAll('a:not(.btn)')).forEach(function (a) {
      var p = a.pathname;
      if (!p || p === '/') return;
      if ((path === p || path.indexOf(p) === 0) && p.length > bestLen) { best = a; bestLen = p.length; }
    });
    if (best) best.setAttribute('aria-current', 'page');
  }
 
  /* ---- chat page extras (only runs when the chat form exists) ---- */
  var chatInput = document.getElementById('chat-input');
  var chatForm = document.getElementById('chat-form');
  if (chatInput && chatForm) {
    chatInput.placeholder = (chatInput.placeholder || 'Type your question') + ' (Ctrl+Enter to send)';
 
    var fit = function () {
      chatInput.style.height = 'auto';
      chatInput.style.height = Math.min(chatInput.scrollHeight + 2, 240) + 'px';
    };
    chatInput.addEventListener('input', fit);
    chatForm.addEventListener('submit', function () { setTimeout(fit, 0); });
    fit();
 
    // Example questions: fill the box, let the student edit before sending.
    Array.prototype.slice.call(document.querySelectorAll('[data-prompt]')).forEach(function (btn) {
      btn.addEventListener('click', function () {
        chatInput.value = btn.getAttribute('data-prompt');
        fit();
        chatInput.focus();
      });
    });
  }
})();