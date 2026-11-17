// SPARK progressive-enhancement script.
//
// Placeholder hooks wired up in later features:
//   - live word-count for long-answer custom questions,
//   - autosave of student profile drafts,
//   - drag-to-rank preference ordering.
// The app is fully usable without JavaScript; this only enhances.

(function () {
  "use strict";

  // Word-count badges for [data-wordcount] textareas (FEAT-002+).
  function initWordCount() {
    var fields = document.querySelectorAll("textarea[data-wordcount]");
    fields.forEach(function (field) {
      var badge = document.createElement("span");
      badge.className = "wordcount";
      badge.setAttribute("aria-live", "polite");
      field.insertAdjacentElement("afterend", badge);
      function update() {
        var words = field.value.trim().split(/\s+/).filter(Boolean).length;
        var max = field.getAttribute("data-wordcount");
        badge.textContent = max ? words + " / " + max + " words" : words + " words";
      }
      field.addEventListener("input", update);
      update();
    });
  }

  // Autosave stub: later features POST drafts here.
  function initAutosave() {
    // Intentionally empty until FEAT-002 wires profile autosave.
  }

  // Drag-rank stub: later features enhance ordered preference lists.
  function initDragRank() {
    // Intentionally empty until FEAT-003 wires preference ranking.
  }

  document.addEventListener("DOMContentLoaded", function () {
    initWordCount();
    initAutosave();
    initDragRank();
  });
})();
