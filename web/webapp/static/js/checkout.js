// Opens the Razorpay checkout and posts the signed result back to our server for verification.
(function () {
  "use strict";
  var btn = document.getElementById("rzp-pay");
  if (!btn || typeof Razorpay === "undefined") return;
  var done = document.getElementById("rzp-done");
  function open() {
    var rzp = new Razorpay({
      key: btn.dataset.key,
      order_id: btn.dataset.order,
      amount: btn.dataset.amount,
      currency: "INR",
      name: btn.dataset.name,
      description: btn.dataset.desc,
      prefill: { name: btn.dataset.prefillName, email: btn.dataset.prefillEmail, contact: btn.dataset.prefillContact },
      method: { card: false, emi: false, paylater: false, wallet: false, upi: true, netbanking: true },
      theme: { color: "#2f5597" },
      handler: function (resp) {
        done.razorpay_order_id.value = resp.razorpay_order_id;
        done.razorpay_payment_id.value = resp.razorpay_payment_id;
        done.razorpay_signature.value = resp.razorpay_signature;
        done.submit();
      },
      modal: { ondismiss: function () { btn.disabled = false; } }
    });
    btn.disabled = true;
    rzp.open();
  }
  btn.addEventListener("click", open);
  open();
})();
