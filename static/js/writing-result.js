(function () {
  'use strict';

  var section = document.querySelector('.wr-ai');
  if (!section) return;

  var languageSelects = Array.prototype.slice.call(
    document.querySelectorAll('.wr-language-select')
  );
  var languageSelect = languageSelects[0];
  var overallBand = document.getElementById('wr-overall-band');
  var csrfInput = section.querySelector('[name=csrfmiddlewaretoken]');
  var languageStorageKey = 'writing-ai-summary-language';

  function createElement(tagName, className, text) {
    var node = document.createElement(tagName);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = String(text);
    return node;
  }

  try {
    var savedLanguage = window.localStorage.getItem(languageStorageKey);
    if (['en', 'ru', 'tg'].indexOf(savedLanguage) !== -1) {
      languageSelects.forEach(function (select) {
        select.value = savedLanguage;
      });
    }
  } catch (error) {
    // Storage may be disabled; the selector still works for this page.
  }

  languageSelects.forEach(function (select) {
    select.addEventListener('change', function () {
      languageSelects.forEach(function (otherSelect) {
        otherSelect.value = select.value;
      });
      try {
        window.localStorage.setItem(languageStorageKey, select.value);
      } catch (error) {
        // Storage may be disabled; the selection remains active until navigation.
      }
    });
  });

  function addTextList(parent, title, values, kind) {
    if (!Array.isArray(values) || values.length === 0) return;
    var block = createElement('section', 'wr-list-block');
    block.dataset.kind = kind;
    block.appendChild(createElement('h4', '', title));
    var list = document.createElement('ul');
    list.className = 'wr-feedback-list';
    values.forEach(function (value) {
      list.appendChild(createElement('li', '', value));
    });
    block.appendChild(list);
    parent.appendChild(block);
  }

  function isEvaluation(value) {
    if (!value || typeof value !== 'object'
      || typeof value.task_band_estimate !== 'number'
      || !Number.isFinite(value.task_band_estimate)
      || !value.criteria || !value.overall) {
      return false;
    }
    var criteria = [
      'task_achievement_or_response',
      'coherence_and_cohesion',
      'lexical_resource',
      'grammatical_range_and_accuracy'
    ];
    var criteriaValid = criteria.every(function (key) {
      var criterion = value.criteria[key];
      return criterion
        && typeof criterion.band === 'number'
        && Number.isFinite(criterion.band)
        && typeof criterion.comment === 'string'
        && Array.isArray(criterion.evidence)
        && criterion.evidence.every(function (quote) { return typeof quote === 'string'; });
    });
    var overall = value.overall;
    return criteriaValid
      && Array.isArray(overall.strengths)
      && overall.strengths.every(function (item) { return typeof item === 'string'; })
      && Array.isArray(overall.weaknesses)
      && overall.weaknesses.every(function (item) { return typeof item === 'string'; })
      && Array.isArray(overall.corrections)
      && overall.corrections.every(function (item) {
        return item && typeof item.original === 'string'
          && typeof item.improved === 'string'
          && typeof item.reason === 'string';
      })
      && Array.isArray(overall.next_steps)
      && overall.next_steps.every(function (item) { return typeof item === 'string'; })
      && typeof overall.summary === 'string';
  }

  function renderEvaluation(taskSection, resultContainer, result) {
    if (!isEvaluation(result)) return false;

    var taskNumber = taskSection.dataset.taskNumber;
    var wordCount = Number(taskSection.dataset.wordCount);
    var minimum = Number(taskSection.dataset.minWords);
    resultContainer.replaceChildren();
    var band = Number(result.task_band_estimate);
    var bandLevel = band < 5 ? 'low' : band <= 6 ? 'mid' : band <= 7 ? 'good' : 'high';
    var bandLabel = bandLevel === 'low' ? 'Needs work'
      : bandLevel === 'mid' ? 'Developing'
        : bandLevel === 'good' ? 'Good' : 'Strong';
    var bandRow = createElement('div', 'wr-task-band-row');
    var badge = createElement('div', 'wr-band wr-band--' + bandLevel);
    badge.appendChild(createElement('strong', 'wr-band-number', band.toFixed(1)));
    badge.appendChild(createElement('span', 'wr-band-caption', bandLabel));
    bandRow.appendChild(badge);

    if (wordCount < minimum) {
      bandRow.appendChild(createElement(
        'p',
        'wr-under-minimum',
        'Under the minimum: ' + wordCount + ' of ' + minimum + ' words'
      ));
    }
    resultContainer.appendChild(bandRow);

    var names = [
      taskNumber === '1' ? 'Task Achievement' : 'Task Response',
      'Coherence and Cohesion',
      'Lexical Resource',
      'Grammatical Range and Accuracy'
    ];
    var keys = [
      'task_achievement_or_response',
      'coherence_and_cohesion',
      'lexical_resource',
      'grammatical_range_and_accuracy'
    ];
    var criteriaList = createElement('div', 'wr-criteria');
    keys.forEach(function (key, index) {
      var criterion = result.criteria[key];
      var card = createElement('article', 'wr-criterion');
      var head = createElement('div', 'wr-criterion-head');
      head.appendChild(createElement('h4', '', names[index]));
      head.appendChild(createElement('span', 'wr-band-chip', 'Band ' + Number(criterion.band).toFixed(1)));
      card.appendChild(head);
      var progress = createElement('div', 'wr-progress');
      progress.setAttribute('role', 'img');
      progress.setAttribute('aria-label', 'Band ' + criterion.band + ' out of 9');
      var progressFill = document.createElement('span');
      progressFill.style.width = Math.max(0, Math.min(100, Number(criterion.band) / 9 * 100)) + '%';
      progress.appendChild(progressFill);
      card.appendChild(progress);
      card.appendChild(createElement('p', 'wr-criterion-comment', criterion.comment));
      if (criterion.evidence.length > 0) {
        var evidenceList = createElement('div', 'wr-evidence-list');
        criterion.evidence.forEach(function (quote) {
          var evidence = createElement('blockquote', 'wr-evidence');
          evidence.appendChild(createElement('span', 'wr-evidence-label', 'Evidence'));
          evidence.appendChild(document.createTextNode('“' + quote + '”'));
          evidenceList.appendChild(evidence);
        });
        card.appendChild(evidenceList);
      }
      criteriaList.appendChild(card);
    });
    resultContainer.appendChild(criteriaList);

    var listGrid = createElement('div', 'wr-list-grid');
    addTextList(listGrid, 'Strengths', result.overall.strengths, 'strengths');
    addTextList(listGrid, 'Weaknesses', result.overall.weaknesses, 'weaknesses');
    if (listGrid.childNodes.length) resultContainer.appendChild(listGrid);

    if (Array.isArray(result.overall.corrections) && result.overall.corrections.length) {
      var corrections = createElement('section', 'wr-corrections');
      corrections.appendChild(createElement('h4', '', 'Corrections'));
      var correctionList = document.createElement('ul');
      correctionList.className = 'wr-correction-list';
      result.overall.corrections.forEach(function (item) {
        var card = createElement('li', 'wr-correction');
        var flow = createElement('div', 'wr-correction-flow');
        var original = createElement('p', 'wr-correction-part wr-correction-original');
        original.appendChild(createElement('span', 'wr-correction-label', 'Your text'));
        original.appendChild(document.createTextNode(item.original));
        var improved = createElement('p', 'wr-correction-part wr-correction-improved');
        improved.appendChild(createElement('span', 'wr-correction-label', 'Better'));
        improved.appendChild(document.createTextNode(item.improved));
        flow.appendChild(original);
        flow.appendChild(createElement('span', 'wr-correction-arrow', '→'));
        flow.appendChild(improved);
        card.appendChild(flow);
        card.appendChild(createElement('p', 'wr-reason', item.reason));
        correctionList.appendChild(card);
      });
      corrections.appendChild(correctionList);
      resultContainer.appendChild(corrections);
    }

    if (result.overall.next_steps.length) {
      var nextSteps = createElement('section', 'wr-next-steps');
      nextSteps.appendChild(createElement('h4', '', 'Next steps'));
      var nextList = createElement('ol', 'wr-next-list');
      result.overall.next_steps.forEach(function (step) {
        nextList.appendChild(createElement('li', '', step));
      });
      nextSteps.appendChild(nextList);
      resultContainer.appendChild(nextSteps);
    }
    resultContainer.appendChild(createElement('section', 'wr-summary'));
    var summary = resultContainer.lastChild;
    summary.appendChild(createElement('h4', '', 'Summary'));
    summary.appendChild(createElement('p', '', result.overall.summary));
    return true;
  }

  function setOverallBand(value) {
    if (value === null || value === undefined || !Number.isFinite(Number(value))) {
      overallBand.hidden = true;
      return;
    }
    var band = Number(value);
    var level = band < 5 ? 'low' : band <= 6 ? 'mid' : band <= 7 ? 'good' : 'high';
    var badge = overallBand.querySelector('.wr-overall-badge');
    badge.classList.remove('wr-band--low', 'wr-band--mid', 'wr-band--good', 'wr-band--high');
    badge.classList.add('wr-band--' + level);
    badge.querySelector('.wr-band-number').textContent = band.toFixed(1);
    badge.querySelector('.wr-band-caption').textContent =
      level === 'low' ? 'Needs work'
        : level === 'mid' ? 'Developing'
          : level === 'good' ? 'Good' : 'Strong';
    overallBand.hidden = false;
  }

  function errorMessage(status, payload) {
    if (payload && payload.too_short === true) {
      return 'Text is too short to evaluate (minimum 20 words).';
    }
    if (status === 429) {
      var remaining = payload && Number.isInteger(payload.remaining_today)
        ? ' Remaining today: ' + payload.remaining_today + '.'
        : '';
      return 'Daily AI feedback limit reached. Try again tomorrow.' + remaining;
    }
    if (status === 401 || status === 403 || status === 404 || status === 405 || status === 409) {
      return 'This attempt is not allowed to be evaluated. Refresh the page or sign in again.';
    }
    if (status >= 500) {
      return 'The AI evaluation service is temporarily unavailable. Please retry.';
    }
    return 'The evaluation request or response was invalid. Please retry.';
  }

  function showRetry(taskSection, button, statusNode, message) {
    button.disabled = false;
    statusNode.textContent = message;
    statusNode.classList.remove('is-loading');
    statusNode.classList.add('is-error');
    var retryContainer = taskSection.querySelector('.wr-retry-container');
    retryContainer.replaceChildren();
    var retry = createElement('button', 'wr-retry-button', 'Retry');
    retry.type = 'button';
    retry.addEventListener('click', function () {
      retryContainer.replaceChildren();
      evaluate(taskSection, button, statusNode);
    });
    retryContainer.appendChild(retry);
  }

  function evaluate(taskSection, button, statusNode) {
    button.disabled = true;
    statusNode.textContent = 'Evaluating, this can take up to 30 seconds';
    statusNode.classList.remove('is-error');
    statusNode.classList.add('is-loading');
    taskSection.querySelector('.wr-retry-container').replaceChildren();

    fetch(section.dataset.evaluateUrl, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfInput.value
      },
      body: JSON.stringify({
        task_number: Number(taskSection.dataset.taskNumber),
        language: languageSelect.value
      })
    }).then(function (response) {
      return response.text().then(function (body) {
        var payload;
        try {
          payload = JSON.parse(body);
        } catch (error) {
          throw { status: response.status, payload: null };
        }
        if (!response.ok) throw { status: response.status, payload: payload };
        if (!payload || payload.ok !== true || !isEvaluation(payload.evaluation)) {
          throw { status: 200, payload: null };
        }
        return payload;
      });
    }).then(function (payload) {
      var resultContainer = taskSection.querySelector('.wr-feedback-result');
      if (!resultContainer) {
        resultContainer = createElement('div', 'wr-feedback-result');
        taskSection.appendChild(resultContainer);
      }
      if (!renderEvaluation(taskSection, resultContainer, payload.evaluation)) {
        throw { status: 200, payload: null };
      }
      statusNode.textContent = '';
      statusNode.classList.remove('is-loading', 'is-error');
      button.hidden = true;
      setOverallBand(payload.overall_band_estimate);
    }).catch(function (error) {
      showRetry(
        taskSection,
        button,
        statusNode,
        error && typeof error.status === 'number'
          ? errorMessage(error.status, error.payload)
          : 'Could not reach the AI evaluation service. Please retry.'
      );
    });
  }

  Array.prototype.forEach.call(
    document.querySelectorAll('.wr-task-ai'),
    function (taskSection) {
      var statusNode = taskSection.querySelector('.wr-status');
      var button = taskSection.querySelector('.wr-evaluate-button');
      var existingId = taskSection.dataset.existingJsonId;
      if (existingId) {
        var existingNode = document.getElementById(existingId);
        var existingEvaluation = null;
        try {
          existingEvaluation = JSON.parse(existingNode.textContent);
        } catch (error) {
          statusNode.textContent = 'The saved AI evaluation could not be displayed.';
        }
        var existingResult = taskSection.querySelector('.wr-feedback-result');
        if (!existingResult) {
          existingResult = createElement('div', 'wr-feedback-result');
          taskSection.appendChild(existingResult);
        }
        if (renderEvaluation(taskSection, existingResult, existingEvaluation) && button) {
          button.hidden = true;
        }
      } else if (button) {
        button.addEventListener('click', function () {
          evaluate(taskSection, button, statusNode);
        });
      }
    }
  );

  setOverallBand(section.dataset.overallBand || null);
})();
