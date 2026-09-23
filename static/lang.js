// Simple SW/EN toggle. Elements carry data-sw + data-en; toggle swaps text.
function applyLang(l) {
  document.querySelectorAll('[data-sw]').forEach(function (e) {
    if (e.children.length > 0) return; // skip elements with nested HTML
    var v = l === 'sw' ? e.getAttribute('data-sw') : e.getAttribute('data-en');
    if (v !== null) e.textContent = v;
  });
  document.documentElement.lang = l === 'sw' ? 'sw' : 'en';
  var b = document.getElementById('langbtn');
  if (b) b.textContent = l === 'sw' ? 'EN' : 'SW';
}
function toggleLang() {
  var cur = localStorage.getItem('lang') || 'sw';
  var next = cur === 'sw' ? 'en' : 'sw';
  localStorage.setItem('lang', next);
  applyLang(next);
}
document.addEventListener('DOMContentLoaded', function () {
  applyLang(localStorage.getItem('lang') || 'sw');
});
