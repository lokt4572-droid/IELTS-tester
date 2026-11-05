(function () {
  try {
    window.localStorage.removeItem('chat_ai_provider');
  } catch (error) {
    // Storage may be unavailable in private browsing.
  }
  var cfg = document.getElementById('chat-config');
  if (!cfg) return;
  var thread = document.getElementById('thread');
  var form = document.getElementById('chat-form');
  var input = document.getElementById('chat-input');
  var sendBtn = document.getElementById('chat-send');
  var hint = document.getElementById('empty-hint');
  var chip = document.getElementById('ask-chip');
  var history = JSON.parse(document.getElementById('chat-data').textContent);
  var sessionId = cfg.dataset.sessionId || '';
  var attempt = cfg.dataset.attempt || '';
  var question = cfg.dataset.question || '';
  var csrfInput = document.querySelector('[name=csrfmiddlewaretoken]');
  var csrf = csrfInput ? csrfInput.value : '';
  function appendInline(parent, line) {
    var pattern = /(\*\*[^*]+\*\*|`[^`]+`)/g;
    var lastIndex = 0;
    var match;
    while ((match = pattern.exec(line)) !== null) {
      var plainText = document.createElement('span');
      plainText.textContent = line.slice(lastIndex, match.index);
      parent.appendChild(plainText);
      var token = match[0];
      var formatted = document.createElement(token.slice(0, 2) === '**' ? 'strong' : 'code');
      formatted.textContent = token.slice(token.slice(0, 2) === '**' ? 2 : 1,
        token.slice(0, 2) === '**' ? -2 : -1);
      parent.appendChild(formatted);
      lastIndex = pattern.lastIndex;
    }
    var tail = document.createElement('span');
    tail.textContent = line.slice(lastIndex);
    parent.appendChild(tail);
  }

  function appendFormatted(parent, text) {
    var list = null;
    String(text).split(/\r?\n/).forEach(function (line) {
      var match = line.match(/^\s*[-*•]\s+(.*)/);
      if (match) {
        if (!list) {
          list = document.createElement('ul');
          parent.appendChild(list);
        }
        var item = document.createElement('li');
        appendInline(item, match[1]);
        list.appendChild(item);
        return;
      }
      list = null;
      if (!line.trim()) return;
      var paragraph = document.createElement('p');
      appendInline(paragraph, line);
      parent.appendChild(paragraph);
    });
  }

  function addBubble(role, text, plain) {
    var div = document.createElement('div');
    div.className = 'bubble ' + role;
    if (plain) div.textContent = text;
    else appendFormatted(div, text);
    thread.appendChild(div);
    thread.scrollTop = thread.scrollHeight;
    hint.hidden = true;
    return div;
  }

  function replaceWithReply(bubble, text) {
    bubble.replaceChildren();
    appendFormatted(bubble, text);
  }

  history.forEach(function (message) {
    addBubble(message.role, message.content, message.role === 'user');
  });
  if (!history.length) hint.hidden = false;

  form.addEventListener('submit', function (event) {
    event.preventDefault();
    var text = input.value.trim();
    if (!text) return;
    addBubble('user', text, true);
    input.value = '';
    sendBtn.disabled = true;
    var wait = addBubble('assistant', 'Thinking…', true);
    var body = { message: text };
    if (sessionId) body.session_id = sessionId;
    else if (attempt && question) {
      body.attempt = attempt;
      body.question = question;
    }

    fetch(cfg.dataset.sendUrl, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
      body: JSON.stringify(body)
    }).then(function (response) {
      return response.json().then(function (data) {
        return { ok: response.ok, data: data };
      });
    }).then(function (result) {
      if (!result.ok) {
        wait.textContent = result.data.error || 'Something went wrong.';
        wait.style.color = '#b3261e';
        input.value = text;
        return;
      }
      replaceWithReply(wait, result.data.reply);
      if (!sessionId) {
        sessionId = String(result.data.session_id);
        window.location.href = cfg.dataset.sessionBase + sessionId + '/';
      }
    }).catch(function () {
      wait.textContent = 'Network problem. Your message was not sent.';
      input.value = text;
    }).then(function () {
      sendBtn.disabled = false;
      if (chip) chip.hidden = !!sessionId;
    });
  });

  input.addEventListener('keydown', function (event) {
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) form.requestSubmit();
  });
})();
