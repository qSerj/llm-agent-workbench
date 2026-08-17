// Local shell behaviour. Three jobs only: make long lists searchable, make
// destructive buttons ask, and say out loud that drafting takes a while.
(function () {
  "use strict";

  // A field whose list is worth searching says so with data-choices, naming the
  // datalist that holds its options. Without this the options are reachable only
  // by a double click, which nobody discovers.
  function makeSearchable(input) {
    var listId = input.getAttribute("data-choices");
    var source = document.getElementById(listId);
    if (!source || !window.TomSelect) return;
    var options = Array.prototype.map.call(
      source.querySelectorAll("option"),
      function (option) {
        return { value: option.value, text: option.value };
      }
    );
    new TomSelect(input, {
      options: options,
      create: true,               // a model or path we do not know yet is legal
      maxOptions: 1000,
      persist: false,
      placeholder: input.getAttribute("placeholder") || "",
      render: {
        no_results: function () {
          return '<div class="no-results">нет совпадений — можно ввести своё</div>';
        },
      },
    });
  }

  // The attribute sits on whatever actually destroys something. A form can hold
  // both a harmless button and a destructive one, and only the second may ask.
  function confirmDestructive(element) {
    element.addEventListener("click", function (event) {
      if (!window.confirm(element.getAttribute("data-confirm"))) {
        event.preventDefault();
      }
    });
  }

  function announceWait(form) {
    form.addEventListener("submit", function () {
      var note = document.createElement("p");
      note.className = "waiting";
      note.textContent = form.getAttribute("data-waiting");
      form.appendChild(note);
      Array.prototype.forEach.call(form.querySelectorAll("button"), function (button) {
        button.disabled = true;
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("input[data-choices]").forEach(makeSearchable);
    document.querySelectorAll("button[data-confirm]").forEach(confirmDestructive);
    document.querySelectorAll("form[data-waiting]").forEach(announceWait);
  });
})();
