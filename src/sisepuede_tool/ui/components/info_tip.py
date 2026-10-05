"""ⓘ that explains something in a small bubble.

A native `title` tooltip only appears after hovering for about a second and
does nothing on click, so users read the ⓘ as broken. This is a button that
opens its bubble on click (and on hover / keyboard focus). Clicking anywhere
else closes it. The click handling lives in app_shell._SHELL_JS
(`.info-tip`), the bubble in theme.css.
"""

from shiny import ui


def info_tip(text: str, class_: str = "") -> ui.Tag:
    return ui.tags.button(
        "ⓘ",
        type="button",
        class_=("info-tip " + class_).strip(),
        data_tip=text,
        aria_label=text,
    )
