(function () {
  'use strict';

  var root = document.getElementById('ls-practice');
  if (!root) return;

  var form = document.getElementById('ls-practice-form');
  var saveStatus = document.getElementById('ls-save-status');
  var errorStatus = document.getElementById('ls-error');
  var saveButton = document.getElementById('ls-save-now');
  var submitButton = document.getElementById('ls-submit');
  var attemptId = root.getAttribute('data-attempt-id');
  var storageKey = 'listening_attempt_answers_' + attemptId;
  var isSaving = false;
  var saveAgain = false;
  var answers = {};

  function parseTime(value) {
    var parsed = Date.parse(value || '');
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function readInitialAnswers() {
    var element = document.getElementById('ls-initial-answers');
    if (!element) return {};
    try {
      var parsed = JSON.parse(element.textContent || '{}');
      return parsed && typeof parsed === 'object' ? parsed : {};
    } catch (error) {
      return {};
    }
  }

  function readStoredCopy() {
    try {
      var raw = localStorage.getItem(storageKey);
      if (!raw) return null;
      var saved = JSON.parse(raw);
      if (!saved || typeof saved !== 'object' || !saved.answers ||
          typeof saved.answers !== 'object') return null;
      return saved;
    } catch (error) {
      return null;
    }
  }

  function writeStoredCopy(savedAt, answerSnapshot) {
    try {
      localStorage.setItem(storageKey, JSON.stringify({
        savedAt: savedAt || new Date().toISOString(),
        answers: answerSnapshot || answers
      }));
    } catch (error) {
      // Storage may be unavailable; server autosave remains active.
    }
  }

  function applyAnswers() {
    Array.prototype.forEach.call(
      form.querySelectorAll('[data-question-number]'),
      function (control) {
        var number = control.getAttribute('data-question-number');
        var value = answers[number];
        if (control.type === 'radio') {
          control.checked = value === control.value;
        } else if (control.type === 'checkbox') {
          control.checked = Array.isArray(value) && value.indexOf(control.value) !== -1;
        } else {
          control.value = typeof value === 'string' ? value : '';
        }
      }
    );

    Array.prototype.forEach.call(form.querySelectorAll('[data-multi-questions]'), function (group) {
      var numbers = group.getAttribute('data-multi-questions').split(',');
      var selected = numbers.length ? answers[numbers[0]] : [];
      if (!Array.isArray(selected)) selected = [];
      Array.prototype.forEach.call(group.querySelectorAll('[data-multi-option]'), function (input) {
        input.checked = selected.indexOf(input.value) !== -1;
      });
    });
  }

  function collectAnswers() {
    var current = {};
    Array.prototype.forEach.call(form.querySelectorAll('[data-question-number]'), function (control) {
      var number = control.getAttribute('data-question-number');
      if (control.type === 'radio') {
        if (control.checked) current[number] = control.value;
        else if (!(number in current)) current[number] = '';
      } else if (control.type !== 'checkbox') {
        current[number] = control.value;
      }
    });
    Array.prototype.forEach.call(form.querySelectorAll('[data-multi-questions]'), function (group) {
      var selected = Array.prototype.map.call(
        group.querySelectorAll('[data-multi-option]:checked'),
        function (input) { return input.value; }
      );
      group.getAttribute('data-multi-questions').split(',').forEach(function (number) {
        current[number] = selected.slice();
      });
    });
    return current;
  }

  function answerIsPresent(value) {
    if (Array.isArray(value)) return value.length > 0;
    return typeof value === 'string' && value.trim().length > 0;
  }

  function refreshCounts() {
    var current = collectAnswers();
    Array.prototype.forEach.call(document.querySelectorAll('[data-section-count]'), function (counter) {
      var sectionNumber = counter.getAttribute('data-section-count');
      var panel = document.querySelector('[data-section-panel="' + sectionNumber + '"]');
      if (!panel) return;
      var questionNumbers = [];
      Array.prototype.forEach.call(panel.querySelectorAll('[data-question-number]'), function (control) {
        var number = control.getAttribute('data-question-number');
        if (questionNumbers.indexOf(number) === -1) questionNumbers.push(number);
      });
      Array.prototype.forEach.call(panel.querySelectorAll('[data-multi-questions]'), function (group) {
        group.getAttribute('data-multi-questions').split(',').forEach(function (number) {
          if (questionNumbers.indexOf(number) === -1) questionNumbers.push(number);
        });
      });
      var answered = questionNumbers.filter(function (number) {
        return answerIsPresent(current[number]);
      }).length;
      counter.textContent = answered + '/' + questionNumbers.length + ' answered';
    });
  }

  function setError(message) {
    errorStatus.textContent = message || '';
  }

  function saveAnswers() {
    answers = collectAnswers();
    var savedSnapshot = answers;
    writeStoredCopy(new Date().toISOString(), savedSnapshot);
    if (isSaving) {
      saveAgain = true;
      return Promise.resolve();
    }
    isSaving = true;
    setError('');
    saveStatus.textContent = 'Saving…';
    var csrfInput = form.querySelector('[name=csrfmiddlewaretoken]');
    return fetch(root.getAttribute('data-save-url'), {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfInput ? csrfInput.value : ''
      },
      body: JSON.stringify({ answers: answers })
    }).then(function (response) {
      return response.json().then(function (data) {
        if (!response.ok || !data.ok) {
          throw new Error(data.error || 'Your answers could not be saved.');
        }
        var latestLocalCopy = readStoredCopy();
        if (!latestLocalCopy || parseTime(latestLocalCopy.savedAt) <= parseTime(data.saved_at)) {
          writeStoredCopy(data.saved_at, savedSnapshot);
        }
        var savedTime = new Date(data.saved_at);
        saveStatus.textContent = 'Saved at ' + savedTime.toLocaleTimeString([], {
          hour: '2-digit',
          minute: '2-digit'
        });
        refreshCounts();
      });
    }).catch(function (error) {
      saveStatus.textContent = '';
      setError(error.message || 'Saving failed. Your answers are kept on this device; try again.');
    }).finally(function () {
      isSaving = false;
      if (saveAgain) {
        saveAgain = false;
        saveAnswers();
      }
    });
  }

  function switchSection(number) {
    Array.prototype.forEach.call(document.querySelectorAll('[data-section-panel] audio'), function (audio) {
      audio.pause();
    });
    Array.prototype.forEach.call(document.querySelectorAll('[data-section-panel]'), function (panel) {
      var active = panel.getAttribute('data-section-panel') === number;
      panel.classList.toggle('ls-hidden', !active);
    });
    Array.prototype.forEach.call(document.querySelectorAll('[data-section-tab]'), function (tab) {
      var active = tab.getAttribute('data-section-tab') === number;
      tab.classList.toggle('ls-active', active);
      tab.setAttribute('aria-selected', active ? 'true' : 'false');
    });
  }

  function unansweredSummary() {
    var current = collectAnswers();
    var lines = [];
    Array.prototype.forEach.call(document.querySelectorAll('[data-section-panel]'), function (panel) {
      var number = panel.getAttribute('data-section-panel');
      var allNumbers = [];
      Array.prototype.forEach.call(panel.querySelectorAll('[data-question-number]'), function (control) {
        var questionNumber = control.getAttribute('data-question-number');
        if (allNumbers.indexOf(questionNumber) === -1) allNumbers.push(questionNumber);
      });
      Array.prototype.forEach.call(panel.querySelectorAll('[data-multi-questions]'), function (group) {
        group.getAttribute('data-multi-questions').split(',').forEach(function (questionNumber) {
          if (allNumbers.indexOf(questionNumber) === -1) allNumbers.push(questionNumber);
        });
      });
      var missing = allNumbers.filter(function (questionNumber) {
        return !answerIsPresent(current[questionNumber]);
      }).length;
      lines.push('Section ' + number + ': ' + missing + ' unanswered');
    });
    return lines.join('\n');
  }

  function submitAnswers() {
    var summary = unansweredSummary();
    if (!window.confirm('Submit your answers?\n\n' + summary)) return;
    answers = collectAnswers();
    writeStoredCopy(new Date().toISOString());
    setError('');
    submitButton.disabled = true;
    var csrfInput = form.querySelector('[name=csrfmiddlewaretoken]');
    fetch(root.getAttribute('data-submit-url'), {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfInput ? csrfInput.value : ''
      },
      body: JSON.stringify({ answers: answers })
    }).then(function (response) {
      if (response.redirected) {
        window.location.assign(response.url);
        return null;
      }
      return response.json().then(function (data) {
        if (!response.ok || !data.ok) {
          throw new Error(data.error || 'Your answers could not be submitted.');
        }
        if (data.redirect_url) window.location.assign(data.redirect_url);
      });
    }).catch(function (error) {
      submitButton.disabled = false;
      setError(error.message || 'Submission failed. Please try again.');
    });
  }

  answers = readInitialAnswers();
  var storedCopy = readStoredCopy();
  var serverTime = parseTime(root.getAttribute('data-server-saved-at'));
  if (storedCopy && parseTime(storedCopy.savedAt) > serverTime) {
    answers = storedCopy.answers;
  }
  applyAnswers();
  refreshCounts();

  form.addEventListener('input', function () {
    answers = collectAnswers();
    writeStoredCopy(new Date().toISOString());
    refreshCounts();
  });
  form.addEventListener('change', function (event) {
    var multi = event.target.closest('[data-multi-questions]');
    if (multi) {
      var checked = multi.querySelectorAll('[data-multi-option]:checked');
      var limit = Number(multi.getAttribute('data-choose') || 0);
      if (checked.length > limit) event.target.checked = false;
    }
    answers = collectAnswers();
    writeStoredCopy(new Date().toISOString());
    refreshCounts();
  });
  form.addEventListener('focusout', function () {
    saveAnswers();
  });

  Array.prototype.forEach.call(document.querySelectorAll('[data-section-tab]'), function (tab) {
    tab.addEventListener('click', function () {
      saveAnswers();
      switchSection(tab.getAttribute('data-section-tab'));
    });
  });
  Array.prototype.forEach.call(document.querySelectorAll('[data-speed-control]'), function (select) {
    select.addEventListener('change', function () {
      var audio = select.closest('.ls-audio-controls').querySelector('audio');
      if (audio) audio.playbackRate = Number(select.value);
    });
  });
  Array.prototype.forEach.call(document.querySelectorAll('[data-replay]'), function (button) {
    button.addEventListener('click', function () {
      var audio = button.closest('.ls-audio-controls').querySelector('audio');
      if (!audio) return;
      audio.currentTime = 0;
      var result = audio.play();
      if (result && typeof result.catch === 'function') {
        result.catch(function () {
          setError('Audio could not play. Use the audio player controls to try again.');
        });
      }
    });
  });

  saveButton.addEventListener('click', saveAnswers);
  submitButton.addEventListener('click', submitAnswers);
  window.setInterval(saveAnswers, 20000);
})();
