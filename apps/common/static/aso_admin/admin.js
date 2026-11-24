/* Small admin conveniences. Everything here is optional polish: the admin works without it. */
document.addEventListener('DOMContentLoaded', function () {
  // Search box: show the hint ("Search by order number...") inside the box instead of under it.
  var bar = document.getElementById('searchbar');
  var help = document.getElementById('searchbar_helptext');
  if (bar) {
    bar.placeholder = help ? help.textContent.trim() : 'Search';
    if (help) { help.style.display = 'none'; var br = help.previousElementSibling; if (br && br.tagName === 'BR') br.style.display = 'none'; }
  }

  // Phones: filters sit above the list as one folded "Filters" panel instead of a long column below it.
  var filter = document.getElementById('changelist-filter');
  if (filter && window.matchMedia('(max-width: 767px)').matches) {
    var wrap = document.createElement('details');
    wrap.className = 'aso-filter-toggle';
    var summary = document.createElement('summary');
    summary.textContent = 'Filters';
    wrap.appendChild(summary);
    var changelist = document.getElementById('changelist');
    changelist.parentNode.insertBefore(wrap, changelist);
    wrap.appendChild(filter);
    var h2 = filter.querySelector('h2'); if (h2) h2.hidden = true;
    // Any filter other than "All" in use? Say so on the button.
    var used = Array.prototype.some.call(filter.querySelectorAll('li.selected a'), function (a) {
      return a.getAttribute('href') !== '?' && !/^(All|Any date)$/.test(a.textContent.trim());
    });
    if (used) summary.textContent = 'Filters (in use)';
  }
});
