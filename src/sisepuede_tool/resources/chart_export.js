// Chart export (ui/components/chart_export.py): the ⤓ button next to a results
// chart opens #mrv-export; "Download" redraws the chart off screen with its
// title, subtitle, source line and legend, in the chosen size, background and
// text colour, and saves it as PNG or SVG. The page's Plotly lives inside the
// widget bundle, so a full plotly.js is loaded from /vendor/plotly on first use.
(function() {
  var target = null;  // {id, title}
  var plotlyReady = null;

  function loadPlotly() {
    if (window.Plotly && window.Plotly.toImage) return Promise.resolve(window.Plotly);
    if (!plotlyReady) {
      plotlyReady = new Promise(function(resolve, reject) {
        var s = document.createElement('script');
        s.src = 'vendor/plotly/plotly.min.js';
        s.onload = function() { resolve(window.Plotly); };
        s.onerror = function() { plotlyReady = null; reject(new Error('plotly.js did not load')); };
        document.head.appendChild(s);
      });
    }
    return plotlyReady;
  }

  function graphDiv(id) {
    var box = document.getElementById(id);
    return box ? box.querySelector('.js-plotly-plot') : null;
  }

  function field(name) { return document.getElementById('mrv-export-' + name); }

  // first and last year on the x axis, when it holds years
  function yearSpan(gd) {
    var ys = [];
    (gd._fullData || []).forEach(function(tr) {
      Array.prototype.forEach.call(tr.x || [], function(x) {
        var n = Number(x);
        if (Number.isInteger(n) && n >= 1900 && n <= 2200) ys.push(n);
      });
    });
    if (!ys.length) return '';
    var a = Math.min.apply(null, ys), b = Math.max.apply(null, ys);
    return a === b ? String(a) : a + '–' + b;
  }

  function baselineLabel(id) {
    // the results bar of the same page (same module namespace)
    var ns = id.slice(0, id.lastIndexOf('-') + 1);
    var sel = document.getElementById(ns + 'rb_baseline');
    if (!sel) return '';
    var opt = sel.selectize ? sel.selectize.getItem(sel.value) : sel.options[sel.selectedIndex];
    return opt ? (opt.textContent || '').trim() : '';
  }

  window.mrvChartExport = function(btn) {
    var id = btn.getAttribute('data-chart');
    var gd = graphDiv(id);
    if (!gd) return;
    target = {id: id};
    field('title').value = btn.getAttribute('data-title') || '';
    field('subtitle').value = [baselineLabel(id), yearSpan(gd)].filter(Boolean).join(' · ');
    var w = gd.offsetWidth || 1000, h = gd.offsetHeight || 500;
    field('width').value = 1600;
    field('height').value = Math.max(800, Math.round(1600 * h / w / 10) * 10);
    document.getElementById('mrv-export').showModal();
  };

  function esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  // deep copy; typed arrays become plain arrays (JSON would turn them into objects)
  function clone(v) {
    if (ArrayBuffer.isView(v)) return Array.from(v);
    if (Array.isArray(v)) return v.map(clone);
    if (v && typeof v === 'object') {
      var out = {};
      Object.keys(v).forEach(function(key) { if (key.charAt(0) !== '_') out[key] = clone(v[key]); });
      return out;
    }
    return v;
  }

  function styled(gd, o) {
    var data = clone(gd.data);
    var layout = clone(gd.layout);
    var k = o.scale;
    var dark = o.text === 'dark';
    var text = dark ? '#1C2B33' : '#F4F1EA';
    var label = dark ? '#55615E' : '#D6D0C4';
    var grid = dark ? '#E8E1D2' : 'rgba(255,255,255,0.22)';
    var bg = o.background === 'white' ? '#FFFFFF' : 'rgba(0,0,0,0)';

    layout.width = o.width;
    layout.height = o.height;
    layout.autosize = false;
    layout.paper_bgcolor = bg;
    layout.plot_bgcolor = bg;
    layout.font = Object.assign({}, layout.font, {size: 14 * k, color: text});
    layout.hovermode = false;

    var titleH = 0;
    if (o.title || o.subtitle) {
      var t = o.title ? '<b>' + esc(o.title) + '</b>' : '';
      if (o.subtitle) t += (t ? '<br>' : '') + '<span style="font-size:' + Math.round(14 * k) + 'px;color:' + label + '">' + esc(o.subtitle) + '</span>';
      layout.title = {text: t, x: 0, xref: 'paper', xanchor: 'left', y: 1 - 22 * k / o.height, yref: 'container', yanchor: 'top',
                      font: {size: 22 * k, color: text}};
      titleH = (o.title ? 34 : 0) + (o.subtitle ? 24 : 0);
    } else {
      layout.title = {text: ''};
    }
    var m = layout.margin || {};
    layout.margin = {l: Math.max(m.l || 0, 70) * k, r: Math.max(m.r || 0, 24) * k,
                     t: (titleH + 56) * k, b: (o.source ? 80 : 50) * k, pad: 4};

    Object.keys(layout).forEach(function(key) {
      if (!/^[xy]axis\d*$/.test(key)) return;
      var ax = layout[key];
      ax.tickfont = Object.assign({}, ax.tickfont, {size: 13 * k, color: label});
      if (ax.title) ax.title.font = Object.assign({}, ax.title.font, {size: 14 * k, color: label});
      if (ax.showgrid !== false) ax.gridcolor = grid;
      ax.linecolor = grid;
      ax.tickcolor = grid;
    });
    layout.showlegend = o.legend && data.some(function(tr) { return tr.showlegend !== false; });
    if (layout.showlegend) {
      // a long legend (e.g. transformations under their sector): smaller text,
      // and the image made tall enough for every entry
      var items = data.filter(function(tr) { return tr.showlegend !== false && tr.name; }).length;
      var groups = data.filter(function(tr) { return tr.showlegend !== false && tr.legendgrouptitle && tr.legendgrouptitle.text; }).length;
      var size = (items > 20 ? 11 : 13) * k;
      var gtitle = Object.assign({}, (layout.legend || {}).grouptitlefont, {size: size, color: text});
      layout.legend = Object.assign({}, layout.legend, {font: {size: size, color: text}, grouptitlefont: gtitle, bgcolor: 'rgba(0,0,0,0)'});
      // Plotly measures each legend entry a little narrower than it draws it,
      // which cut the end of the longest names: a few spaces of slack
      // (about a tenth of a name's length, so the longest ones get the most)
      data.forEach(function(tr) {
        if (tr.showlegend !== false && tr.name) tr.name = tr.name + '\u00a0'.repeat(4 + Math.ceil(String(tr.name).length * 0.15));
        if (tr.legendgrouptitle) tr.legendgrouptitle = Object.assign({}, tr.legendgrouptitle, {font: {size: size, color: text}});
      });
      // room on the right for a legend outside the plot: Plotly sizes it before
      // the page font loads, so long names were cut; reserve it from the
      // longest name (plain text, about 0.6 em a character, plus the swatch)
      if ((layout.legend.x || 0) >= 1) {
        var plain = function(t) { return String(t || '').replace(/<[^>]*>/g, ''); };
        var longest = 0;
        data.forEach(function(tr) {
          if (tr.showlegend === false) return;
          longest = Math.max(longest, plain(tr.name).length, plain(tr.legendgrouptitle && tr.legendgrouptitle.text).length);
        });
        layout.margin.r = Math.max(layout.margin.r, Math.ceil((longest * size * 0.62 + 70) * 1.1));
        layout.legend.x = 1.01;
        layout.legend.xanchor = 'left';
        // a wide legend: the image made wider so the plot keeps its width
        var plotW = 1100 * k;
        if (o.width - layout.margin.l - layout.margin.r < plotW) {
          o.width = Math.ceil(layout.margin.l + layout.margin.r + plotW);
          layout.width = o.width;
        }
      }
      var needed = Math.ceil(items * size * 1.75 + groups * size * 2.6 + layout.margin.t + layout.margin.b);
      if (needed > o.height) { o.height = needed; layout.height = needed; }
    }
    layout.annotations = (layout.annotations || []).map(function(a) {
      var f = a.font || {};
      return Object.assign({}, a, {font: Object.assign({}, f, {size: (f.size || 12) * k, color: f.color === '#1C2B33' || !f.color ? text : f.color})});
    });
    if (o.source) {
      layout.annotations.push({text: esc(o.source), xref: 'paper', yref: 'paper', x: 0, y: 0, xanchor: 'left', yanchor: 'top',
                               yshift: -42 * k, showarrow: false, font: {size: 12 * k, color: label}});
    }
    (layout.shapes || []).forEach(function(s) { if (s.line && !dark) s.line.color = label; });
    data.forEach(function(tr) {
      // the net line is near-black: invisible on a dark slide
      if (!dark && tr.line && tr.line.color === '#1C2B33') tr.line.color = text;
      if (!dark && tr.marker && tr.marker.color === '#1C2B33') tr.marker.color = text;
    });
    return {data: data, layout: layout};
  }

  function fileName(title) {
    var s = (title || 'chart').normalize('NFKD').replace(/[^\w\s-]/g, '').trim().replace(/\s+/g, '_').toLowerCase();
    return s || 'chart';
  }

  window.mrvChartExportGo = function() {
    if (!target) return;
    var gd = graphDiv(target.id);
    var dlg = document.getElementById('mrv-export');
    if (!gd) { dlg.close(); return; }
    var o = {
      title: field('title').value.trim(),
      subtitle: field('subtitle').value.trim(),
      source: field('source').value.trim(),
      width: Math.min(Math.max(parseInt(field('width').value, 10) || 1600, 300), 6000),
      height: Math.min(Math.max(parseInt(field('height').value, 10) || 900, 200), 6000),
      format: field('format').value,
      background: field('background').value,
      text: field('text').value,
      scale: parseFloat(field('scale').value) || 1,
      legend: field('legend').checked,
    };
    var btn = document.getElementById('mrv-export-go');
    btn.disabled = true;
    loadPlotly().then(function(Plotly) {
      var fig = styled(gd, o);
      return Plotly.downloadImage(fig, {format: o.format, width: o.width, height: o.height,
                                        scale: o.format === 'png' ? 2 : 1, filename: fileName(o.title)});
    }).then(function() {
      dlg.close();
    }).catch(function(err) {
      console.error(err);
      alert(err.message || String(err));
    }).finally(function() {
      btn.disabled = false;
    });
  };
})();
