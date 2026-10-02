// Camera QR scanning with the browser's built-in BarcodeDetector (Chrome / Edge on Android,
// ChromeOS and many desktops). No external library is loaded. Falls back to manual / USB input.
(function () {
  "use strict";
  var btn = document.getElementById("start-camera");
  var video = document.getElementById("camera");
  var note = document.getElementById("camera-note");
  var input = document.getElementById("code");
  var form = document.getElementById("code-form");
  if (!btn) return;
  if (!("BarcodeDetector" in window) || !navigator.mediaDevices) {
    btn.disabled = true;
    note.textContent = "This browser cannot scan with the camera. Use Chrome on Android, a USB scanner, " +
      "or scan the QR with the phone's camera app - it opens this page automatically.";
    return;
  }
  var detector = new window.BarcodeDetector({ formats: ["qr_code"] });
  btn.addEventListener("click", function () {
    navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } }).then(function (stream) {
      video.srcObject = stream;
      video.classList.remove("hidden");
      btn.classList.add("hidden");
      video.play();
      var busy = false;
      var timer = setInterval(function () {
        if (busy || video.readyState < 2) return;
        busy = true;
        detector.detect(video).then(function (codes) {
          busy = false;
          if (codes.length) {
            clearInterval(timer);
            stream.getTracks().forEach(function (t) { t.stop(); });
            input.value = codes[0].rawValue;
            form.submit();
          }
        }).catch(function () { busy = false; });
      }, 250);
    }).catch(function () {
      note.textContent = "Camera permission was denied. Allow camera access or type the code.";
    });
  });
})();
