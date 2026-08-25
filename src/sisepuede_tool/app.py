"""Shiny entrypoint. Pages are added milestone by milestone (see plan)."""

from shiny import App

from sisepuede_tool.ui.app_shell import app_ui, server

app = App(app_ui, server)


def main() -> None:
    from shiny import run_app

    run_app(app)


if __name__ == "__main__":
    main()
