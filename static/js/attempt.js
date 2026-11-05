(function () {
  var form = document.getElementById('exam-form');
  if (!form) return;

  var saveUrl = form.dataset.saveUrl;
  var endAt = Date.now() + parseInt(form.dataset.secondsLeft, 10) * 1000;
  var timerEl = document.getElementById('timer');
  var stateEl = document.getElementById('save-state');
  var csrf = form.querySelector('[name=csrfmiddlewaretoken]').value;
  var submitting = false;

  /* ---- timer ---- */
  function fmt(s) {
    var m = Math.floor(s / 60), r = s % 60;
    return String(m).padStart(2, '0') + ':' + String(r).padStart(2, '0');
  }
  function tick() {
    var left = Math.max(0, Math.round((endAt - Date.now()) / 1000));
    timerEl.textContent = fmt(left);
    timerEl.classList.toggle('low', left <= 300);
    if (left <= 0 && !submitting) { submitting = true; form.submit(); }
  }
  tick();
  setInterval(tick, 1000);

  /* ---- parts ---- */
  var parts = Array.prototype.slice.call(document.querySelectorAll('.part'));
  var tabs = Array.prototype.slice.call(document.querySelectorAll('.part-tab'));
  function showPart(n) {
    parts.forEach(function (p) { p.hidden = p.dataset.part !== String(n); });
    tabs.forEach(function (t) { t.classList.toggle('active', t.dataset.part === String(n)); });
  }
  tabs.forEach(function (t) { t.addEventListener('click', function () { showPart(t.dataset.part); }); });

  /* ---- question palette ---- */
  var questions = Array.prototype.slice.call(document.querySelectorAll('.q'));
  var palette = document.getElementById('palette');
  var buttons = [];
  var lastPart = null;
  questions.forEach(function (q) {
    if (lastPart !== null && q.dataset.part !== lastPart) {
      var gap = document.createElement('span'); gap.className = 'pal-gap'; palette.appendChild(gap);
    }
    lastPart = q.dataset.part;
    var b = document.createElement('button');
    b.type = 'button'; b.className = 'pal-btn'; b.textContent = q.dataset.number;
    b.setAttribute('aria-label', 'Go to question ' + q.dataset.number);
    b.addEventListener('click', function () {
      showPart(q.dataset.part);
      q.scrollIntoView({ block: 'center' });
      var f = q.querySelector('input, select');
      if (f) f.focus({ preventScroll: true });
    });
    palette.appendChild(b);
    buttons.push(b);
  });

  function isAnswered(q) {
    var radios = q.querySelectorAll('input[type=radio]');
    if (radios.length) return !!q.querySelector('input[type=radio]:checked');
    var f = q.querySelector('input[type=text], select');
    return !!(f && f.value.trim());
  }
  function refreshPalette() {
    questions.forEach(function (q, i) { buttons[i].classList.toggle('done', isAnswered(q)); });
  }
  refreshPalette();

  /* ---- autosave ---- */
  var timeout = null;
  function save() {
    stateEl.textContent = 'Saving…';
    fetch(saveUrl, { method: 'POST', body: new FormData(form), headers: { 'X-CSRFToken': csrf }, credentials: 'same-origin' })
      .then(function (r) {
        if (r.status === 409) { window.location.reload(); return; }
        stateEl.textContent = r.ok ? 'Saved' : 'Not saved';
      })
      .catch(function () { stateEl.textContent = 'Offline: will retry'; });
  }
  function onChange() {
    refreshPalette();
    clearTimeout(timeout);
    timeout = setTimeout(save, 600);
  }
  form.addEventListener('input', onChange);
  form.addEventListener('change', onChange);
  // Enter inside a text gap should not submit the whole test.
  form.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && e.target.tagName === 'INPUT' && e.target.type === 'text') e.preventDefault();
  });

  /* ---- finish ---- */
  form.addEventListener('submit', function (e) {
    if (submitting) return;
    var blank = questions.filter(function (q) { return !isAnswered(q); }).length;
    var msg = blank ? blank + ' question' + (blank === 1 ? ' is' : 's are') + ' unanswered. Finish the test now?'
                    : 'Finish the test and see your score?';
    if (!window.confirm(msg)) { e.preventDefault(); return; }
    submitting = true;
  });

  /* ---- highlighter ---- */
  var hlBtn = document.getElementById('hl-btn');
  var currentRange = null;
  function passageContaining(node) {
    while (node && node !== document.body) {
      if (node.nodeType === 1 && node.classList.contains('passage-text')) return node;
      node = node.parentNode;
    }
    return null;
  }
  document.addEventListener('selectionchange', function () {
    var sel = window.getSelection();
    if (!sel.rangeCount || sel.isCollapsed) { hlBtn.hidden = true; return; }
    var range = sel.getRangeAt(0);
    var host = passageContaining(range.commonAncestorContainer);
    if (!host) { hlBtn.hidden = true; return; }
    currentRange = range.cloneRange();
    var rect = range.getBoundingClientRect();
    hlBtn.style.top = Math.max(60, rect.top - 40) + 'px';
    hlBtn.style.left = Math.max(8, rect.left) + 'px';
    hlBtn.hidden = false;
  });
  hlBtn.addEventListener('mousedown', function (e) { e.preventDefault(); });
  hlBtn.addEventListener('click', function () {
    if (!currentRange) return;
    var mark = document.createElement('mark');
    try { currentRange.surroundContents(mark); }
    catch (err) { stateEl.textContent = 'Select text inside a single paragraph to highlight.'; }
    window.getSelection().removeAllRanges();
    hlBtn.hidden = true;
  });
  function unwrap(mark) {
    var parent = mark.parentNode;
    while (mark.firstChild) parent.insertBefore(mark.firstChild, mark);
    parent.removeChild(mark);
    parent.normalize();
  }
  document.addEventListener('click', function (e) {
    if (e.target.tagName === 'MARK' && passageContaining(e.target)) unwrap(e.target);
  });
  document.getElementById('clear-hl').addEventListener('click', function () {
    Array.prototype.slice.call(document.querySelectorAll('.passage-text mark')).forEach(unwrap);
  });
})();
