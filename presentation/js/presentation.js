/*
 * Metrik — Innovation Presentation
 * Lightweight slide engine: viewport scaling, keyboard/click navigation,
 * dot indicator, progress bar. No external dependencies.
 */
(function () {
  "use strict";

  var slides = Array.prototype.slice.call(document.querySelectorAll(".slide"));
  var total = slides.length;
  var current = 0;
  var isPrinting = window.matchMedia && window.matchMedia("print").matches;

  var stage = document.getElementById("stage");
  var dotsWrap = document.getElementById("dots");
  var curNum = document.getElementById("curNum");
  var totalNum = document.getElementById("totalNum");
  var progressFill = document.getElementById("progressFill");
  var prevBtn = document.getElementById("prevBtn");
  var nextBtn = document.getElementById("nextBtn");

  totalNum.textContent = total;

  // ---- build dot indicators ----
  slides.forEach(function (_, i) {
    var b = document.createElement("button");
    b.className = "dot-btn" + (i === 0 ? " active" : "");
    b.setAttribute("aria-label", "Go to slide " + (i + 1));
    b.addEventListener("click", function () { goTo(i); });
    dotsWrap.appendChild(b);
  });
  var dotEls = Array.prototype.slice.call(dotsWrap.children);

  function render() {
    slides.forEach(function (s, i) {
      s.classList.toggle("active", i === current);
    });
    dotEls.forEach(function (d, i) {
      d.classList.toggle("active", i === current);
    });
    curNum.textContent = current + 1;
    progressFill.style.width = ((current + 1) / total * 100) + "%";
    history.replaceState(null, "", "#" + (current + 1));
  }

  function goTo(n) {
    current = Math.max(0, Math.min(total - 1, n));
    render();
  }
  function next() { goTo(current + 1); }
  function prev() { goTo(current - 1); }

  prevBtn.addEventListener("click", prev);
  nextBtn.addEventListener("click", next);

  // ---- keyboard navigation ----
  document.addEventListener("keydown", function (e) {
    switch (e.key) {
      case "ArrowRight": case "ArrowDown": case "PageDown": case " ":
        e.preventDefault(); next(); break;
      case "ArrowLeft": case "ArrowUp": case "PageUp": case "Backspace":
        e.preventDefault(); prev(); break;
      case "Home":
        e.preventDefault(); goTo(0); break;
      case "End":
        e.preventDefault(); goTo(total - 1); break;
    }
  });

  // ---- swipe support (touch trackpads / tablets) ----
  var touchStartX = null;
  document.addEventListener("touchstart", function (e) {
    touchStartX = e.changedTouches[0].clientX;
  }, { passive: true });
  document.addEventListener("touchend", function (e) {
    if (touchStartX === null) return;
    var dx = e.changedTouches[0].clientX - touchStartX;
    if (Math.abs(dx) > 60) { dx < 0 ? next() : prev(); }
    touchStartX = null;
  }, { passive: true });

  // ---- open directly on a given slide via #3 in the URL ----
  var hashN = parseInt(location.hash.replace("#", ""), 10);
  if (!isNaN(hashN) && hashN >= 1 && hashN <= total) {
    current = hashN - 1;
  }

  // ---- scale the 1920×1080 stage to fit the viewport ----
  function fitStage() {
    if (isPrinting) return; // print stylesheet takes over sizing entirely
    var vw = window.innerWidth;
    var vh = window.innerHeight;
    var scale = Math.min(vw / 1920, vh / 1080);
    stage.style.transform = "scale(" + scale + ")";
  }
  window.addEventListener("resize", fitStage);
  fitStage();

  render();
})();
