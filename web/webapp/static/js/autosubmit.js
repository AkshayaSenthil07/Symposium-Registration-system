// Submits a form automatically (used when returning from the payment step).
(function () {
  var form = document.querySelector("form[data-autosubmit-form]");
  if (form) setTimeout(function () { form.submit(); }, 400);
})();
