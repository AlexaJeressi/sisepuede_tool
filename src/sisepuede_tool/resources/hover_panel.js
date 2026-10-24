// Hover panel (ui/components/hover_panel.py): a strip above a chart that shows
// the details of the bar under the cursor, so a long hover (a transformation's
// projects) doesn't cover the other bars. A bar's customdata is
// [name, detail line, project count, projects one per line (name, a tab, its
// description)]; the strip keeps the last bar shown until another one is hovered.
(function() {
  function show(panel, cd) {
    var body = panel.querySelector('.hover-panel-body');
    panel.classList.add('on');
    var head = document.createElement('div');
    head.className = 'hover-panel-head';
    var b = document.createElement('b');
    b.textContent = cd[0];
    head.appendChild(b);
    head.appendChild(document.createTextNode('  ' + cd[1]));
    var count = document.createElement('div');
    count.className = 'hover-panel-count';
    count.textContent = cd[2];
    body.replaceChildren(head, count);
    var names = String(cd[3] || '').split('\n').filter(Boolean);
    if (names.length) {
      var ul = document.createElement('ul');
      names.forEach(function(n) {
        var li = document.createElement('li');
        var cut = n.indexOf('\t');
        var name = document.createElement('b');
        name.textContent = cut < 0 ? n : n.slice(0, cut);
        li.appendChild(name);
        if (cut >= 0 && n.slice(cut + 1).trim()) {
          var d = document.createElement('div');
          d.className = 'hover-panel-desc';
          d.textContent = n.slice(cut + 1);
          li.appendChild(d);
        }
        ul.appendChild(li);
      });
      body.appendChild(ul);
    }
  }

  function bind() {
    document.querySelectorAll('.hover-panel[data-chart]').forEach(function(panel) {
      var box = document.getElementById(panel.getAttribute('data-chart'));
      var gd = box ? box.querySelector('.js-plotly-plot') : null;
      if (!gd || !gd.on || gd._hoverPanel === panel) return;
      gd._hoverPanel = panel;
      // a new chart: back to the hint
      panel.classList.remove('on');
      panel.querySelector('.hover-panel-body').replaceChildren();
      gd.on('plotly_hover', function(ev) {
        var pt = ev && ev.points && ev.points[0];
        if (pt && Array.isArray(pt.customdata) && pt.customdata.length >= 4) show(panel, pt.customdata);
      });
    });
  }

  var queued = false;
  new MutationObserver(function() {
    if (queued) return;
    queued = true;
    requestAnimationFrame(function() { queued = false; bind(); });
  }).observe(document.documentElement, {childList: true, subtree: true});
})();
