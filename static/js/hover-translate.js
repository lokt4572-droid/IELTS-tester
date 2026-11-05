(function () {
  var dataEl = document.getElementById('reading-translations');
  var switcher = document.getElementById('translation-switcher');
  if (!dataEl || !switcher) return;

  var translations = JSON.parse(dataEl.textContent);
  var languages = Object.keys(translations).filter(function (language) {
    return translations[language] && typeof translations[language].words === 'object' &&
      translations[language].words !== null && !Array.isArray(translations[language].words);
  });
  if (!languages.length) return;

  var passages = Array.prototype.slice.call(document.querySelectorAll('.passage-text'));
  if (!passages.length) return;

  var hasBoth = languages.indexOf('ru') !== -1 && languages.indexOf('tg') !== -1;
  var options = languages.slice();
  if (hasBoth) options.push('both');
  options.push('off');

  var mode = languages.indexOf('ru') !== -1 ? 'ru' : languages[0];
  try {
    var storedMode = localStorage.getItem('tr_lang');
    if (options.indexOf(storedMode) !== -1) mode = storedMode;
  } catch (e) {}

  var tooltip = document.createElement('div');
  tooltip.className = 'tr-tooltip';
  tooltip.setAttribute('role', 'tooltip');
  tooltip.hidden = true;
  document.body.appendChild(tooltip);

  var activeWord = null;
  var showTimer = null;
  var touchMode = !!(window.matchMedia &&
    window.matchMedia('(hover: none), (pointer: coarse)').matches);

  function normalize(value) {
    return value.toLowerCase().replace(/[^a-z0-9]/g, '');
  }

  function lookup(language, key) {
    var dictionary = translations[language];
    if (!dictionary || !dictionary.words) return null;
    var base = dictionary.forms && dictionary.forms[key] ? dictionary.forms[key] : key;
    var entry = dictionary.words[base];
    return entry && typeof entry.t === 'string' && entry.t ? entry : null;
  }

  function matchKey(key) {
    for (var i = 0; i < languages.length; i += 1) {
      if (lookup(languages[i], key)) return true;
    }
    return false;
  }

  function translationFor(modeName, key) {
    if (modeName === 'both') {
      return ['ru', 'tg'].filter(function (language) {
        return languages.indexOf(language) !== -1;
      }).map(function (language) {
        return { language: language, entry: lookup(language, key) };
      }).filter(function (result) { return result.entry; });
    }
    var entry = lookup(modeName, key);
    return entry ? [{ language: modeName, entry: entry }] : [];
  }

  function setWordTranslation(word) {
    var key = word.getAttribute('data-word');
    var results = translationFor(mode, key);
    if (!results.length || mode === 'off') {
      word.removeAttribute('data-tr');
      return;
    }
    word.setAttribute('data-tr', results.map(function (result) {
      return result.entry.t;
    }).join('; '));
  }

  function appendEntry(container, result) {
    var line = document.createElement('div');
    line.className = 'tr-tooltip-line';
    var label = document.createElement('span');
    label.className = 'tr-tooltip-language';
    label.textContent = result.language === 'tg' ? 'TJ: ' : result.language.toUpperCase() + ': ';
    line.appendChild(label);
    var text = document.createElement('strong');
    text.textContent = result.entry.t;
    line.appendChild(text);
    if (result.entry.pos) {
      var pos = document.createElement('small');
      pos.textContent = ' (' + result.entry.pos + ')';
      line.appendChild(pos);
    }
    if (result.entry.ex) {
      var example = document.createElement('div');
      example.className = 'tr-tooltip-example';
      example.textContent = result.entry.ex;
      line.appendChild(example);
    }
    if (result.entry.ok === false || result.entry.check === true) {
      var mark = document.createElement('small');
      mark.className = 'tr-unverified';
      mark.textContent = ' · unverified';
      line.appendChild(mark);
    }
    container.appendChild(line);
  }

  function positionTooltip(word) {
    var rect = word.getBoundingClientRect();
    var tipRect = tooltip.getBoundingClientRect();
    var left = Math.max(8, Math.min(rect.left, window.innerWidth - tipRect.width - 8));
    var top = rect.bottom + tipRect.height + 8 <= window.innerHeight
      ? rect.bottom + 8
      : Math.max(8, rect.top - tipRect.height - 8);
    tooltip.style.left = left + 'px';
    tooltip.style.top = top + 'px';
  }

  function renderTooltip(word) {
    if (!word || mode === 'off') {
      tooltip.hidden = true;
      activeWord = null;
      return;
    }
    var results = translationFor(mode, word.getAttribute('data-word'));
    if (!results.length) {
      tooltip.hidden = true;
      activeWord = null;
      return;
    }
    tooltip.textContent = '';
    results.forEach(function (result) { appendEntry(tooltip, result); });
    activeWord = word;
    tooltip.hidden = false;
    positionTooltip(word);
  }

  function showWord(word, delayed) {
    clearTimeout(showTimer);
    if (mode === 'off') return;
    setWordTranslation(word);
    if (delayed) {
      showTimer = setTimeout(function () { renderTooltip(word); }, 150);
    } else {
      renderTooltip(word);
    }
  }

  function hideTooltip() {
    clearTimeout(showTimer);
    tooltip.hidden = true;
    activeWord = null;
  }

  function wordFromTarget(target) {
    return target && target.closest ? target.closest('.tr-word') : null;
  }

  function wrapPassage(passage) {
    var walker = document.createTreeWalker(passage, NodeFilter.SHOW_TEXT, {
      acceptNode: function (node) {
        var parent = node.parentElement;
        if (!node.nodeValue || !node.nodeValue.trim() || !parent ||
            parent.closest('input, textarea, button, select, option, .plabel, .tr-word')) {
          return NodeFilter.FILTER_REJECT;
        }
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    var nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);

    nodes.forEach(function (node) {
      var text = node.nodeValue;
      var matcher = /[A-Za-z]+(?:['’][A-Za-z]+)*/g;
      var tokens = [];
      var token;
      while ((token = matcher.exec(text))) {
        tokens.push({ start: token.index, end: matcher.lastIndex, key: normalize(token[0]) });
      }
      if (!tokens.length) return;

      var fragment = document.createDocumentFragment();
      var cursor = 0;
      var changed = false;
      for (var i = 0; i < tokens.length;) {
        var matched = null;
        var matchedEnd = i;
        for (var count = Math.min(3, tokens.length - i); count > 0; count -= 1) {
          var contiguous = true;
          for (var j = i; j < i + count - 1; j += 1) {
            if (/\S/.test(text.slice(tokens[j].end, tokens[j + 1].start))) {
              contiguous = false;
              break;
            }
          }
          if (!contiguous) continue;
          var key = tokens.slice(i, i + count).map(function (part) {
            return part.key;
          }).join(' ');
          if (matchKey(key)) {
            matched = key;
            matchedEnd = i + count - 1;
            break;
          }
        }
        if (!matched) {
          i += 1;
          continue;
        }
        var start = tokens[i].start;
        var end = tokens[matchedEnd].end;
        if (start > cursor) fragment.appendChild(document.createTextNode(text.slice(cursor, start)));
        var span = document.createElement('span');
        span.className = 'tr-word';
        span.setAttribute('data-word', matched);
        span.textContent = text.slice(start, end);
        span.tabIndex = mode === 'off' ? -1 : 0;
        setWordTranslation(span);
        fragment.appendChild(span);
        cursor = end;
        changed = true;
        i = matchedEnd + 1;
      }
      if (changed) {
        if (cursor < text.length) fragment.appendChild(document.createTextNode(text.slice(cursor)));
        node.parentNode.replaceChild(fragment, node);
      }
    });
  }

  function paintMode() {
    passages.forEach(function (passage) {
      passage.classList.toggle('tr-disabled', mode === 'off');
      Array.prototype.forEach.call(passage.querySelectorAll('.tr-word'), function (word) {
        word.tabIndex = mode === 'off' ? -1 : 0;
        setWordTranslation(word);
      });
    });
    Array.prototype.forEach.call(switcher.querySelectorAll('button'), function (button) {
      button.setAttribute('aria-pressed', button.dataset.mode === mode ? 'true' : 'false');
    });
    if (activeWord) renderTooltip(activeWord);
    else hideTooltip();
  }

  languages.forEach(function (language) {
    var button = document.createElement('button');
    button.type = 'button';
    button.dataset.mode = language;
    button.textContent = language === 'tg' ? 'TJ' : language.toUpperCase();
    switcher.appendChild(button);
  });
  if (hasBoth) {
    var bothButton = document.createElement('button');
    bothButton.type = 'button';
    bothButton.dataset.mode = 'both';
    bothButton.textContent = 'Both';
    switcher.appendChild(bothButton);
  }
  var offButton = document.createElement('button');
  offButton.type = 'button';
  offButton.dataset.mode = 'off';
  offButton.textContent = 'Off';
  switcher.appendChild(offButton);
  switcher.hidden = false;

  passages.forEach(wrapPassage);
  switcher.addEventListener('click', function (event) {
    var button = event.target.closest('button[data-mode]');
    if (!button) return;
    mode = button.dataset.mode;
    try { localStorage.setItem('tr_lang', mode); } catch (e) {}
    paintMode();
  });

  passages.forEach(function (passage) {
    passage.addEventListener('mouseover', function (event) {
      if (touchMode) return;
      var word = wordFromTarget(event.target);
      if (word && word !== wordFromTarget(event.relatedTarget)) showWord(word, true);
    });
    passage.addEventListener('mouseout', function (event) {
      if (touchMode) return;
      var word = wordFromTarget(event.target);
      if (word && word !== wordFromTarget(event.relatedTarget)) hideTooltip();
    });
    passage.addEventListener('click', function (event) {
      if (!touchMode) return;
      var word = wordFromTarget(event.target);
      if (word) {
        event.preventDefault();
        if (activeWord === word) hideTooltip();
        else showWord(word, false);
      } else {
        hideTooltip();
      }
    });
    passage.addEventListener('focusin', function (event) {
      var word = wordFromTarget(event.target);
      if (word && mode !== 'off') showWord(word, false);
    });
    passage.addEventListener('focusout', function (event) {
      if (wordFromTarget(event.target)) hideTooltip();
    });
  });
  document.addEventListener('click', function (event) {
    if (touchMode && !wordFromTarget(event.target) &&
        !event.target.closest('#translation-switcher')) hideTooltip();
  });
  window.addEventListener('scroll', hideTooltip, true);

  paintMode();
})();
