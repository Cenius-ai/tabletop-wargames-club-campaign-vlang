/* Progressive enhancement only: every form and link works with JavaScript off. */
(function () {
  "use strict";

  // Show / hide password toggle.
  document.querySelectorAll("[data-password-toggle]").forEach(function (button) {
    var input = document.getElementById(button.getAttribute("aria-controls"));
    if (!input) {
      return;
    }
    button.addEventListener("click", function () {
      var isHidden = input.type === "password";
      input.type = isHidden ? "text" : "password";
      button.setAttribute("aria-pressed", String(isHidden));
      button.textContent = isHidden ? "Hide" : "Show";
    });
  });

  // Busy state + re-entrancy guard so a double click cannot post twice.
  document.querySelectorAll("form[data-busy]").forEach(function (form) {
    var submitting = false;
    form.addEventListener("submit", function (event) {
      if (submitting) {
        event.preventDefault();
        return;
      }
      if (typeof form.checkValidity === "function" && !form.checkValidity()) {
        return;
      }
      submitting = true;
      var button = form.querySelector('button[type="submit"]');
      if (!button) {
        return;
      }
      var label = form.getAttribute("data-busy-label") || button.getAttribute("data-busy-label");
      button.setAttribute("aria-busy", "true");
      button.disabled = true;
      if (label) {
        button.textContent = label;
      }
    });
  });

  // Dismiss a flash message.
  document.querySelectorAll("[data-dismiss]").forEach(function (button) {
    button.addEventListener("click", function () {
      var flash = button.closest(".flash");
      if (flash) {
        flash.remove();
      }
    });
  });
})();
