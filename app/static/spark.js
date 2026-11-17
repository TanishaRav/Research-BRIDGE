// SPARK progressive-enhancement script.
//
// Enhancements (all optional; the app works without JS):
//   - live word-count badges for [data-wordcount] textareas,
//   - positions integer validation with a >20 warning,
//   - pay-hours >10 warning,
//   - comp-type / time-kind field toggles,
//   - fetch-based autosave with an aria-live status region,
//   - drag-to-rank preference ordering with keyboard Up/Down fallback.

(function () {
  "use strict";

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
        if (max) {
          var remaining = max - words;
          badge.textContent = words + " / " + max + " words (" + remaining + " left)";
          badge.classList.toggle("over", words > Number(max));
        } else {
          badge.textContent = words + " words";
        }
      }
      field.addEventListener("input", update);
      update();
    });
  }

  function initPositions() {
    var input = document.querySelector("[data-positions]");
    if (!input) return;
    var warn = document.createElement("span");
    warn.className = "hint";
    warn.setAttribute("aria-live", "polite");
    input.insertAdjacentElement("afterend", warn);
    function update() {
      var v = input.value.trim();
      if (v !== "" && !/^\d+$/.test(v)) {
        warn.textContent = "Positions must be a whole number.";
        warn.classList.add("over");
      } else if (Number(v) > 20) {
        warn.textContent = "More than 20 positions; please confirm.";
        warn.classList.add("over");
      } else {
        warn.textContent = "";
        warn.classList.remove("over");
      }
    }
    input.addEventListener("input", update);
    update();
  }

  function initPayHours() {
    var input = document.querySelector("[data-payhours]");
    var warn = document.querySelector("[data-payhours-warn]");
    if (!input || !warn) return;
    function update() {
      var n = Number(input.value);
      if (input.value !== "" && n > 20) {
        warn.textContent = "Pay hours cannot exceed 20 per week.";
        warn.classList.add("over");
      } else if (n > 10) {
        warn.textContent = "More than 10 hours per week may be a heavy load.";
        warn.classList.add("over");
      } else {
        warn.textContent = "";
        warn.classList.remove("over");
      }
    }
    input.addEventListener("input", update);
    update();
  }

  function toggleBlocks(selectEl, classPrefix) {
    var blocks = document.querySelectorAll("." + classPrefix + "-credit, ." + classPrefix + "-pay");
    function update() {
      var val = selectEl.value;
      blocks.forEach(function (b) {
        var isCredit = b.classList.contains(classPrefix + "-credit");
        var show = (val === "credit" && isCredit) || (val === "pay" && !isCredit);
        b.style.display = show ? "" : "none";
      });
    }
    selectEl.addEventListener("change", update);
    update();
  }

  function initToggles() {
    var comp = document.querySelector("[data-comp-toggle]");
    if (comp) toggleBlocks(comp, "comp");
    var time = document.querySelector("[data-time-toggle]");
    if (time) toggleBlocks(time, "time");
  }

  function initAutosave() {
    var form = document.querySelector("form[data-autosave]");
    if (!form) return;
    var url = form.getAttribute("data-autosave");
    var status = document.getElementById("autosave-status");
    var timer = null;
    function save() {
      var data = new FormData(form);
      fetch(url, { method: "POST", body: new URLSearchParams(data), credentials: "same-origin" })
        .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
        .then(function () { if (status) status.textContent = "Draft saved."; })
        .catch(function () { if (status) status.textContent = "Autosave failed; your data is kept in the form."; });
    }
    form.addEventListener("input", function () {
      if (status) status.textContent = "Saving...";
      clearTimeout(timer);
      timer = setTimeout(save, 1200);
    });
  }

  function initDragRank() {
    var list = document.getElementById("rank-list");
    if (!list) return;
    var dragged = null;

    function items() {
      return Array.prototype.slice.call(list.querySelectorAll(".rank-item"));
    }

    list.addEventListener("dragstart", function (e) {
      var li = e.target.closest(".rank-item");
      dragged = li;
      if (li) li.classList.add("dragging");
    });
    list.addEventListener("dragend", function () {
      if (dragged) dragged.classList.remove("dragging");
      dragged = null;
    });
    list.addEventListener("dragover", function (e) {
      e.preventDefault();
      var after = null;
      items().forEach(function (li) {
        if (li === dragged) return;
        var box = li.getBoundingClientRect();
        if (e.clientY < box.top + box.height / 2 && after === null) {
          after = li;
        }
      });
      if (dragged) {
        if (after) list.insertBefore(dragged, after);
        else list.appendChild(dragged);
      }
    });

    function move(li, dir) {
      if (dir < 0 && li.previousElementSibling) {
        list.insertBefore(li, li.previousElementSibling);
      } else if (dir > 0 && li.nextElementSibling) {
        list.insertBefore(li.nextElementSibling, li);
      }
      li.querySelector(dir < 0 ? ".rank-up" : ".rank-down").focus();
    }
    list.addEventListener("click", function (e) {
      var li = e.target.closest(".rank-item");
      if (!li) return;
      if (e.target.classList.contains("rank-up")) move(li, -1);
      if (e.target.classList.contains("rank-down")) move(li, 1);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initWordCount();
    initPositions();
    initPayHours();
    initToggles();
    initAutosave();
    initDragRank();
  });
})();
