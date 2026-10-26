// Plotly legends handled by the server (Article 6 credits by sector and for
// the whole economy): a click on an entry hides or shows its series, a double
// click shows it alone (another, all again), as plotly does, but plotly's own
// toggle is cancelled and the click sent to Shiny instead, so the chart is
// redrawn with the bar totals of the series shown (plotly alone would keep the
// totals of all of them). The chart's box has data-legend-event (the event
// type) and data-legend-input (the Shiny input); the event is
// {type, value: the entry's legendgroup, only: true on a double click}.
(function() {
  function send(box, gd, ev, only) {
    var tr = ev && gd.data && gd.data[ev.curveNumber];
    if (!tr || !tr.legendgroup || !window.Shiny) return false;
    Shiny.setInputValue(box.getAttribute('data-legend-input'),
      {type: box.getAttribute('data-legend-event'), value: tr.legendgroup, only: only}, {priority: 'event'});
    return false;  // no plotly toggle: the server redraws the chart
  }

  function bind() {
    document.querySelectorAll('[data-legend-event]').forEach(function(box) {
      var gd = box.querySelector('.js-plotly-plot');
      if (!gd || !gd.on || gd._legendEvents) return;
      gd._legendEvents = true;
      // plotly fires legendclick on both clicks of a double click: a click is
      // sent only when no second one follows (as plotly's own delay)
      var timer = null;
      gd.on('plotly_legendclick', function(ev) {
        if (timer) { clearTimeout(timer); timer = null; return false; }
        timer = setTimeout(function() { timer = null; send(box, gd, ev, false); }, 300);
        return false;
      });
      gd.on('plotly_legenddoubleclick', function(ev) {
        if (timer) { clearTimeout(timer); timer = null; }
        return send(box, gd, ev, true);
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
