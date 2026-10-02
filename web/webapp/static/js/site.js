// Small progressive enhancements. The site works without JavaScript.
(function () {
  "use strict";

  // mobile navigation / sidebar toggles
  document.querySelectorAll("[data-toggle]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var target = document.getElementById(btn.getAttribute("data-toggle"));
      if (target) {
        var open = target.classList.toggle("open");
        btn.setAttribute("aria-expanded", open ? "true" : "false");
      }
    });
  });
  document.addEventListener("click", function (e) {
    var side = document.getElementById("sidebar");
    if (side && side.classList.contains("open") && !side.contains(e.target) &&
        !e.target.closest("[data-toggle='sidebar']")) {
      side.classList.remove("open");
    }
  });

  // show / hide password
  document.querySelectorAll(".pw-toggle").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var input = btn.parentElement.querySelector("input");
      var show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.textContent = show ? "Hide" : "Show";
    });
  });

  // password strength meter
  document.querySelectorAll("[data-strength]").forEach(function (input) {
    var bar = document.querySelector(input.getAttribute("data-strength") + " i");
    if (!bar) return;
    input.addEventListener("input", function () {
      var v = input.value, score = 0;
      if (v.length >= 8) score++;
      if (/[A-Z]/.test(v) && /[a-z]/.test(v)) score++;
      if (/[0-9]/.test(v) && (v.length >= 10 || /[^A-Za-z0-9]/.test(v))) score++;
      bar.className = v ? "s" + Math.max(1, score) : "";
    });
  });

  // confirmation prompts for dangerous buttons
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (!window.confirm(form.getAttribute("data-confirm"))) e.preventDefault();
    });
  });

  // prevent double submit
  document.querySelectorAll("form").forEach(function (form) {
    form.addEventListener("submit", function () {
      if (form.hasAttribute("data-confirm") && form.dataset.confirmed === "no") return;
      setTimeout(function () {
        form.querySelectorAll("button[type=submit]:not([data-multi])").forEach(function (b) { b.disabled = true; });
      }, 0);
    });
  });

  // auto-submit filters
  document.querySelectorAll("[data-autosubmit]").forEach(function (el) {
    el.addEventListener("change", function () { el.form.submit(); });
  });

  // copy buttons
  document.querySelectorAll("[data-copy]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      navigator.clipboard.writeText(btn.getAttribute("data-copy")).then(function () {
        var old = btn.textContent; btn.textContent = "Copied"; setTimeout(function () { btn.textContent = old; }, 1500);
      });
    });
  });

  document.querySelectorAll("[data-print]").forEach(function (b) {
    b.addEventListener("click", function () { window.print(); });
  });

  // team member rows
  var addBtn = document.getElementById("add-member");
  if (addBtn) {
    var list = document.getElementById("members");
    var max = parseInt(addBtn.getAttribute("data-max"), 10);
    function refresh() {
      var n = list.querySelectorAll(".member").length;
      addBtn.disabled = n >= max;
    }
    addBtn.addEventListener("click", function () {
      var tpl = document.getElementById("member-template");
      list.appendChild(tpl.content.cloneNode(true));
      refresh();
    });
    list.addEventListener("click", function (e) {
      if (e.target.matches("[data-remove]")) { e.target.closest(".member").remove(); refresh(); }
    });
    refresh();
  }
})();
