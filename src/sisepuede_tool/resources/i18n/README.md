# UI text by language

Each language has a folder (`en/`, `es/`, `ar/`) with one file per area of
the app (`shell.yaml`, `data_input.yaml`, ...); the files of a language are
merged and must not repeat a key. English is the source text; es and ar have
the same files and keys. A key missing in a language falls back to English.

The language is switched in place from the topbar, without a reload, so
nothing in the session is lost (data, runs, unsaved form values). The first
language comes from `?lang=en|es|ar`, and the last choice is remembered per
browser. Arabic sets `dir="rtl"` on the page; theme.css uses logical CSS
properties, so the same stylesheet mirrors, and theme-rtl.css only adds rules
that apply under `dir="rtl"`.

## In the code (services/i18n.py)

- UI functions (`@module.ui`, built per page load): `i18n.t("area.key")`.
- Server code: pass the session language, `i18n.t("area.key", state.lang())`.
  Pages define `_t(key, **fmt)` / `_tn(key, n, **fmt)` that prefix their area,
  as in ui/page_data_input.py. Plurals: `i18n.tn(key, n, lang)`.
- Text from the app's resource files (transformer names, parameter help, card
  titles, ...): `i18n.td(kind, code, field, english_text, lang)`. English stays
  in the resource file; es/ar translate it in `data_<kind>.yaml` under
  `data.<kind>.<code>.<field>` (no English copy). Codes must not contain dots.
  Kinds: `transformers` (transformer_catalog.yaml), `params`
  (`<transformer code>.<param>` of param_schemas.yaml), `library` (NDC/LEP
  transformations), `results_groups` (card `key`), `article6`.
- Text in the page built at load is marked (`data-i18n`) and swapped by the
  browser on a switch; server-rendered outputs re-render. A `@render.ui` output
  that holds form inputs uses `@i18n.keep_inputs(state.lang)` so a switch
  doesn't redraw it and reset what the user typed (or redraws it from the
  typed values, as the Pathways editor does with `draft`).
- Values substituted into Arabic text are wrapped in invisible direction
  marks so numbers and Latin names keep their order; use `i18n.plain()` on
  text that becomes data (a default name the user can save).
- Inline styles use logical CSS (`text-align: end`, `margin-inline-start`),
  never left/right, so Arabic mirrors.
- `tests/test_i18n.py` checks that keys used in code exist, that es/ar have
  every key with the same `{placeholders}`, and that `data.*` codes exist.

## Status

| Language | Coverage | Review |
|---|---|---|
| English | every page in the sidebar, plus the hidden ones | source |
| Spanish | same | draft, needs review |
| Arabic (Egypt) | same | draft, needs review by an Egyptian reviewer |

Still English by design: sisepuede variable names, field codes and units;
category names from sisepuede attribute tables; project data from the Egypt
projects workbook; cost & benefit item names from the C&B workbook; Excel
downloads; error messages raised by services (exception text).

## Rules for translators

- Keep `{placeholders}` exactly as in English (`{label}`, `{n}`, `{total:,}`).
  `tests/test_i18n.py` checks this and that no key is missing.
- Plurals: English and Spanish use `one` / `other`. Arabic can use `zero`,
  `one`, `two`, `few` (3–10), `many` (11–99) and `other` (100+); `other`
  is required and used for any form left out. A form may write its number
  out ("مساران") and drop `{n}`.
- Sidebar labels and table headers have little room; keep them short.
- Numbers use Western digits (0–9) in every language.
- sisepuede variable names, units and codes (e.g. `ef_agrc_...`) are not
  translated.

## Glossary

The terms to use everywhere. Arabic is Modern Standard Arabic as written in
Egyptian government climate documents; Spanish is neutral Latin American,
addressing the user as "usted".

| English | Español | العربية |
|---|---|---|
| baseline | línea base | خط الأساس |
| pathway | trayectoria | مسار |
| transformation | transformación | تحوّل |
| transformer | transformador | محوّل |
| run (the model) / a run | ejecutar / ejecución | تشغيل / عملية تشغيل |
| business as usual (BAU) | escenario tendencial (short: tendencial) | سيناريو العمل كالمعتاد (short: العمل كالمعتاد) |
| electricity dispatch (NemoMod) | despacho eléctrico | توزيع الأحمال الكهربائية |
| NDC | NDC (contribución determinada a nivel nacional) | المساهمة المحددة وطنيًا |
| LEP, LTS | LEP, LTS | LEP، LTS |
| MRV | MRV | القياس والإبلاغ والتحقق |
| costs & benefits | costos y beneficios | التكاليف والمنافع |
| emissions / net emissions | emisiones / emisiones netas | الانبعاثات / صافي الانبعاثات |
| fugitive emissions | emisiones fugitivas | الانبعاثات المتسربة |
| driver (of emissions) | factor | محرّك |
| credits (Article 6) | créditos | أرصدة |
| carbon price | precio del carbono | سعر الكربون |
| target (NDC) | meta | هدف / مستهدف |
| magnitude | magnitud | الحجم |
| ramp (implementation curve) | rampa de implementación | منحنى التدرّج |
| full effect | efecto completo | التأثير الكامل |
| default | predeterminado | افتراضي |
| advanced options | opciones avanzadas | خيارات متقدمة |
| subsector | subsector | قطاع فرعي |
| landfill | relleno sanitario | مدفن صحي |
| (solid) waste | residuos (sólidos) | المخلفات (الصلبة) |
| manure (management) | (manejo del) estiércol | (إدارة) السماد الحيواني |
| greenhouse gases | gases de efecto invernadero | غازات الاحتباس الحراري |
| land use | uso del suelo | استخدام الأراضي |
| settlements (land category) | asentamientos | الأراضي العمرانية |
| direct air capture | captura directa de aire | احتجاز الكربون مباشرة من الهواء |
| septic tanks | fosas sépticas | خزانات التحليل |
| final time period (of the model) | periodo final | آخر فترة زمنية في النموذج |
| AFOLU, IPPU | AFOLU, IPPU | AFOLU، IPPU |

Numbers use Western digits (0–9). Arabic uses its own punctuation (، ؛ ؟) and
«» quotes; Spanish uses “” quotes and opening ¿ ¡.
