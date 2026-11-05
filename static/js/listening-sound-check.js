(function () {
  var audio = document.getElementById('ls-sound-check-audio');
  var button = document.getElementById('ls-play-sound');
  var status = document.getElementById('ls-sound-check-status');
  if (!audio || !button || !status) return;

  button.addEventListener('click', function () {
    audio.currentTime = 0;
    var playResult = audio.play();
    if (playResult && typeof playResult.then === 'function') {
      playResult.then(function () {
        status.textContent = 'Test sound is playing.';
      }).catch(function () {
        status.textContent = 'The test sound could not play. Check your device audio settings and try again.';
      });
    } else {
      status.textContent = 'Test sound is playing.';
    }
  });

  audio.addEventListener('ended', function () {
    status.textContent = 'Sound check complete. You can start the exam.';
  });
})();
