(function () {
  'use strict';

  var root = document.getElementById('ls-exam');
  if (!root) return;

  var beginButton = document.getElementById('ls-begin-test');
  var readyPanel = document.getElementById('ls-exam-ready');
  var audio = document.getElementById('ls-exam-audio');
  var audioTools = document.getElementById('ls-audio-tools');
  var audioError = document.getElementById('ls-audio-error');
  var audioErrorMessage = document.getElementById('ls-audio-error-message');
  var retryButton = document.getElementById('ls-audio-retry');
  var tapPanel = document.getElementById('ls-tap-audio');
  var tapButton = document.getElementById('ls-tap-audio-button');
  var volume = document.getElementById('ls-exam-volume');
  var phaseReadout = document.getElementById('ls-phase-readout');
  var sectionLabel = document.getElementById('ls-section-label');
  var phaseLabel = document.getElementById('ls-phase-label');
  var countdown = document.getElementById('ls-countdown');
  var saveStatus = document.getElementById('ls-exam-save-status');
  var errorStatus = document.getElementById('ls-exam-error');
  var form = document.getElementById('ls-exam-form');
  var scheduleNode = document.getElementById('ls-exam-initial-schedule');
  var answerNode = document.getElementById('ls-exam-initial-answers');
  var audioMapNode = document.getElementById('ls-exam-audio-map');
  if (!audio || !form || !scheduleNode || !answerNode || !audioMapNode) return;

  var schedule = JSON.parse(scheduleNode.textContent || '[]');
  var audioMap = JSON.parse(audioMapNode.textContent || '{}');
  var answers = JSON.parse(answerNode.textContent || '{}');
  var offsetMs = 0;
  var begun = root.getAttribute('data-begun') === 'true';
  var activePhase = null;
  var activePhaseKey = '';
  var audioLoadKey = '';
  var audioResumeAt = 0;
  var isSaving = false;
  var saveAgain = false;
  var finishing = false;
  var nextStateRetryAt = 0;
  var storageKey = 'listening_attempt_answers_' + root.getAttribute('data-attempt-id');
  var phaseTitles = {
    preview: 'Look at the questions',
    listen: 'Listen',
    check: 'Check your answers',
    review: 'Review'
  };

  function serverNow() {
    return Date.now() + offsetMs;
  }

  function parseInitialAnswers() {
    try {
      var parsed = JSON.parse(answerNode.textContent || '{}');
      return parsed && typeof parsed === 'object' ? parsed : {};
    } catch (error) {
      return {};
    }
  }

  function readLocalCopy() {
    try {
      var raw = localStorage.getItem(storageKey);
      if (!raw) return null;
      var value = JSON.parse(raw);
      if (!value || !value.answers || typeof value.answers !== 'object') return null;
      return value;
    } catch (error) {
      return null;
    }
  }

  function storeLocalCopy(snapshot) {
    try {
      localStorage.setItem(storageKey, JSON.stringify({
        savedAt: new Date().toISOString(),
        answers: snapshot || answers
      }));
    } catch (error) {
      // The server remains the durable copy when browser storage is unavailable.
    }
  }

  function applyAnswers() {
    Array.prototype.forEach.call(form.querySelectorAll('[data-question-number]'), function (control) {
      var number = control.getAttribute('data-question-number');
      var value = answers[number];
      if (control.type === 'radio') {
        control.checked = value === control.value;
      } else {
        control.value = typeof value === 'string' ? value : '';
      }
    });
    Array.prototype.forEach.call(form.querySelectorAll('[data-multi-questions]'), function (group) {
      var numbers = group.getAttribute('data-multi-questions').split(',');
      var selected = numbers.length ? answers[numbers[0]] : [];
      if (!Array.isArray(selected)) selected = [];
      Array.prototype.forEach.call(group.querySelectorAll('[data-multi-option]'), function (input) {
        input.checked = selected.indexOf(input.value) !== -1;
      });
    });
  }

  function collectAllAnswers() {
    var values = {};
    Array.prototype.forEach.call(form.querySelectorAll('[data-question-number]'), function (control) {
      var number = control.getAttribute('data-question-number');
      if (control.type === 'radio') {
        if (control.checked) values[number] = control.value;
        else if (!(number in values)) values[number] = '';
      } else {
        values[number] = control.value;
      }
    });
    Array.prototype.forEach.call(form.querySelectorAll('[data-multi-questions]'), function (group) {
      var selected = Array.prototype.map.call(
        group.querySelectorAll('[data-multi-option]:checked'),
        function (input) { return input.value; }
      );
      group.getAttribute('data-multi-questions').split(',').forEach(function (number) {
        values[number] = selected.slice();
      });
    });
    return values;
  }

  function saveableAnswers(phase) {
    var all = collectAllAnswers();
    if (!phase) return {};
    if (phase.phase === 'review') return all;
    var panel = document.querySelector(
      '[data-exam-section="' + phase.section_number + '"]'
    );
    if (!panel) return {};
    var subset = {};
    Array.prototype.forEach.call(panel.querySelectorAll('[data-question-number]'), function (control) {
      var number = control.getAttribute('data-question-number');
      subset[number] = all[number];
    });
    Array.prototype.forEach.call(panel.querySelectorAll('[data-multi-questions]'), function (group) {
      group.getAttribute('data-multi-questions').split(',').forEach(function (number) {
        subset[number] = all[number];
      });
    });
    return subset;
  }

  function reportError(message) {
    errorStatus.textContent = message || '';
  }

  function redirectToResult(url) {
    if (url) window.location.assign(url);
  }

  function updateFromServer(data) {
    if (data.server_now) offsetMs = Date.parse(data.server_now) - Date.now();
    if (Array.isArray(data.schedule)) schedule = data.schedule;
    begun = true;
    if (!data.finished) finishing = false;
    if (readyPanel) readyPanel.hidden = true;
    audioTools.hidden = false;
    if (data.finished) {
      finishing = true;
      redirectToResult(data.result_url);
      return;
    }
    renderTimeline();
  }

  function fetchState() {
    return fetch(root.getAttribute('data-state-url'), {
      method: 'GET',
      credentials: 'same-origin',
      headers: { 'Accept': 'application/json' }
    }).then(function (response) {
      return response.json().then(function (data) {
        if (!response.ok || !data.ok) {
          throw new Error(data.error || 'The exam schedule could not be loaded.');
        }
        updateFromServer(data);
      });
    }).catch(function (error) {
      finishing = false;
      nextStateRetryAt = Date.now() + 3000;
      reportError(error.message || 'The exam schedule could not be loaded. Refresh to retry.');
    });
  }

  function phaseAtClientTime() {
    var now = serverNow();
    for (var index = 0; index < schedule.length; index += 1) {
      var item = schedule[index];
      var start = Date.parse(item.start);
      var end = Date.parse(item.end);
      if (start <= now && now < end) {
        return {
          phase: item.phase,
          section_number: item.section_number,
          start_ms: start,
          end_ms: end,
          remaining_seconds: Math.max(0, Math.ceil((end - now) / 1000)),
          key: item.phase + ':' + item.section_number + ':' + item.start
        };
      }
    }
    return { phase: 'finished', section_number: null, remaining_seconds: 0, key: 'finished' };
  }

  function formatCountdown(seconds) {
    var minutes = Math.floor(seconds / 60);
    var remainder = seconds % 60;
    return String(minutes).padStart(2, '0') + ':' + String(remainder).padStart(2, '0');
  }

  function lockSections(phase) {
    var currentSection = phase.section_number || 0;
    var isReview = phase.phase === 'review';
    Array.prototype.forEach.call(document.querySelectorAll('[data-exam-section]'), function (panel) {
      var sectionNumber = Number(panel.getAttribute('data-exam-section'));
      var visible = isReview || sectionNumber <= currentSection;
      panel.classList.toggle('ls-hidden', !visible);
      panel.setAttribute(
        'data-readonly',
        !isReview && sectionNumber < currentSection ? 'true' : 'false'
      );
      Array.prototype.forEach.call(panel.querySelectorAll('input, select, textarea, button'), function (control) {
        control.disabled = !visible || (!isReview && sectionNumber !== currentSection);
      });
      panel.setAttribute('aria-hidden', visible ? 'false' : 'true');
    });
    document.getElementById('ls-review-panel').classList.toggle('ls-hidden', !isReview);
  }

  function displayPhase(phase) {
    var name = phase.phase;
    if (name === 'finished') {
      phaseLabel.textContent = 'Finishing your test…';
      countdown.textContent = '';
      if (!finishing && Date.now() >= nextStateRetryAt) {
        finishing = true;
        fetchState();
      }
      return;
    }
    sectionLabel.textContent = phase.section_number
      ? 'Section ' + phase.section_number
      : 'All sections';
    phaseLabel.textContent = phaseTitles[name] || 'Exam';
    countdown.textContent = phase.remaining_seconds === null
      ? ''
      : formatCountdown(phase.remaining_seconds);
    lockSections(phase);
    if (activePhaseKey !== phase.key) {
      var previousSection = activePhase ? activePhase.section_number : null;
      var enteringReview = phase.phase === 'review';
      if (activePhase && activePhase.phase === 'listen') stopAudio();
      activePhaseKey = phase.key;
      activePhase = phase;
      if (phase.phase === 'listen') startAudio(phase);
      else tapPanel.hidden = true;
      phaseReadout.setAttribute('data-phase', phase.phase);
      if (
        begun &&
        (enteringReview || (
          previousSection !== null &&
          phase.section_number !== null &&
          previousSection !== phase.section_number
        ))
      ) {
        saveAnswers();
      }
    } else {
      activePhase = phase;
    }
  }

  function renderTimeline() {
    if (!begun || !schedule.length) return;
    displayPhase(phaseAtClientTime());
  }

  function showAudioError(message) {
    console.warn('Listening exam audio error');
    audioErrorMessage.textContent = message;
    audioError.hidden = false;
    retryButton.hidden = false;
    tapPanel.hidden = true;
  }

  function showTapToContinue() {
    console.warn('Listening exam audio playback was blocked');
    audioErrorMessage.textContent = 'Audio playback was blocked. Tap to continue or retry.';
    audioError.hidden = false;
    retryButton.hidden = false;
    tapPanel.hidden = false;
  }

  function setAudioPositionAndPlay(phase) {
    if (!activePhase || activePhase.phase !== 'listen') return;
    var elapsed = Math.max(0, (serverNow() - phase.start_ms) / 1000);
    if (elapsed >= Number(audio.duration || Infinity)) return;
    try {
      audio.currentTime = elapsed;
    } catch (error) {
      audio.addEventListener('loadedmetadata', function onMetadata() {
        audio.removeEventListener('loadedmetadata', onMetadata);
        if (!activePhase || activePhase.phase !== 'listen') return;
        var resumeElapsed = Math.max(0, (serverNow() - phase.start_ms) / 1000);
        if (resumeElapsed < Number(audio.duration || Infinity)) audio.currentTime = resumeElapsed;
        playCurrentAudio();
      });
      return;
    }
    playCurrentAudio();
  }

  function playCurrentAudio() {
    if (!activePhase || activePhase.phase !== 'listen') return;
    var playResult = audio.play();
    if (playResult && typeof playResult.then === 'function') {
      playResult.then(function () {
        tapPanel.hidden = true;
        audioError.hidden = true;
      }).catch(function () {
        showTapToContinue();
      });
    }
  }

  function startAudio(phase) {
    var source = audioMap[String(phase.section_number)];
    if (!source) {
      showAudioError('The section audio is unavailable. Retry after checking your connection.');
      return;
    }
    audioLoadKey = phase.key;
    audioResumeAt = Math.max(0, (serverNow() - phase.start_ms) / 1000);
    tapPanel.hidden = true;
    audioError.hidden = true;
    if (audio.getAttribute('src') !== source) {
      audio.pause();
      audio.src = source;
      audio.load();
    }
    if (audio.readyState >= 1) {
      setAudioPositionAndPlay(phase);
    } else {
      audio.addEventListener('loadedmetadata', function onMetadata() {
        audio.removeEventListener('loadedmetadata', onMetadata);
        if (audioLoadKey !== phase.key) return;
        setAudioPositionAndPlay(phase);
      });
    }
  }

  function retryAudio() {
    if (!activePhase || activePhase.phase !== 'listen') return;
    var elapsed = Math.max(0, (serverNow() - activePhase.start_ms) / 1000);
    if (elapsed >= Number(audio.duration || Infinity)) {
      audioError.hidden = true;
      tapPanel.hidden = true;
      return;
    }
    if (audio.readyState >= 1) {
      audio.currentTime = elapsed;
      playCurrentAudio();
    } else {
      audio.load();
      audio.addEventListener('loadedmetadata', function onMetadata() {
        audio.removeEventListener('loadedmetadata', onMetadata);
        retryAudio();
      });
    }
  }

  function stopAudio() {
    audio.pause();
    tapPanel.hidden = true;
    audioError.hidden = true;
  }

  function unlockAudio() {
    audio.src = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA=';
    var playResult = audio.play();
    audio.pause();
    audio.currentTime = 0;
    if (playResult && typeof playResult.catch === 'function') {
      playResult.catch(function () {});
    }
  }

  function beginTest() {
    if (begun) return;
    unlockAudio();
    beginButton.disabled = true;
    reportError('');
    var csrf = root.querySelector('[name=csrfmiddlewaretoken]');
    fetch(root.getAttribute('data-begin-url'), {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf ? csrf.value : ''
      },
      body: '{}'
    }).then(function (response) {
      return response.json().then(function (data) {
        if (!response.ok || !data.ok) {
          throw new Error(data.error || 'The test could not be started.');
        }
        updateFromServer(data);
      });
    }).catch(function (error) {
      beginButton.disabled = false;
      reportError(error.message || 'The test could not be started. Try again.');
    });
  }

  function saveableSnapshot() {
    answers = collectAllAnswers();
    return saveableAnswers(activePhase);
  }

  function syncAfterSave(responseData) {
    if (responseData && responseData.finished) {
      redirectToResult(responseData.result_url);
      return Promise.resolve();
    }
    if (responseData && responseData.schedule && responseData.server_now) {
      updateFromServer(responseData);
      return Promise.resolve();
    }
    return fetchState();
  }

  function saveAnswers() {
    answers = collectAllAnswers();
    storeLocalCopy(answers);
    if (!begun || !activePhase || activePhase.phase === 'finished') return Promise.resolve();
    if (isSaving) {
      saveAgain = true;
      return Promise.resolve();
    }
    var outgoing = saveableSnapshot();
    isSaving = true;
    saveStatus.textContent = 'Saving…';
    reportError('');
    var csrf = root.querySelector('[name=csrfmiddlewaretoken]');
    return fetch(root.getAttribute('data-save-url'), {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf ? csrf.value : ''
      },
      body: JSON.stringify({ answers: outgoing })
    }).then(function (response) {
      return response.json().then(function (data) {
        if (!response.ok || !data.ok) {
          if (data.finished) {
            updateFromServer(data);
            return;
          }
          return syncAfterSave(data).then(function () {
            throw new Error(data.error || 'Your answers could not be saved.');
          });
        }
        var serverSavedAt = new Date(data.saved_at);
        saveStatus.textContent = 'Saved at ' + serverSavedAt.toLocaleTimeString([], {
          hour: '2-digit',
          minute: '2-digit'
        });
        return syncAfterSave(data);
      });
    }).catch(function (error) {
      saveStatus.textContent = '';
      reportError(error.message || 'Saving failed. Your answers remain on this device.');
    }).finally(function () {
      isSaving = false;
      if (saveAgain) {
        saveAgain = false;
        saveAnswers();
      }
    });
  }

  function onUserInput() {
    answers = collectAllAnswers();
    storeLocalCopy(answers);
  }

  function timelineTick() {
    if (!begun || finishing) return;
    renderTimeline();
  }

  if (volume) {
    audio.volume = Number(volume.value);
    volume.addEventListener('input', function () {
      audio.volume = Number(volume.value);
    });
  }
  audio.addEventListener('error', function () {
    if (activePhase && activePhase.phase === 'listen') {
      showAudioError('Section audio failed to load. Check your connection and retry.');
    }
  });
  audio.addEventListener('contextmenu', function (event) {
    event.preventDefault();
  });
  document.addEventListener('keydown', function (event) {
    if (['MediaPlayPause', 'MediaTrackNext', 'MediaTrackPrevious', 'MediaStop'].indexOf(event.key) !== -1) {
      event.preventDefault();
    }
  });
  if (form) {
    form.addEventListener('input', onUserInput);
    form.addEventListener('change', function (event) {
      var group = event.target.closest('[data-multi-questions]');
      if (group) {
        var checked = group.querySelectorAll('[data-multi-option]:checked');
        if (checked.length > Number(group.getAttribute('data-choose') || 0)) {
          event.target.checked = false;
        }
      }
      onUserInput();
    });
    form.addEventListener('focusout', saveAnswers);
  }

  if (beginButton) beginButton.addEventListener('click', beginTest);
  retryButton.addEventListener('click', retryAudio);
  tapButton.addEventListener('click', retryAudio);

  var localCopy = readLocalCopy();
  var serverSavedAt = Date.parse(root.getAttribute('data-server-saved-at') || '') || 0;
  if (localCopy && Date.parse(localCopy.savedAt || '') > serverSavedAt) {
    answers = localCopy.answers;
  } else {
    answers = parseInitialAnswers();
  }
  applyAnswers();

  var initialServerNow = Date.parse(root.getAttribute('data-server-now') || '');
  if (Number.isFinite(initialServerNow)) offsetMs = initialServerNow - Date.now();
  if (begun) {
    renderTimeline();
    fetchState();
  }
  window.setInterval(timelineTick, 250);
  window.setInterval(saveAnswers, 20000);
  window.addEventListener('beforeunload', function (event) {
    if (begun && !finishing) {
      event.preventDefault();
      event.returnValue = '';
    }
  });
})();
