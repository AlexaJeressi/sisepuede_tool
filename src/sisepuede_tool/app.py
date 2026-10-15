"""Shiny entrypoint. Pages are added milestone by milestone (see plan)."""

from shiny import App
import sys, os, os.path, pathlib


# SET SOME PATHS
PATH_CUR = pathlib.Path(os.path.abspath(__file__)).parents[0]
PATH_PAR = PATH_CUR.parents[0]
path_par = str(PATH_PAR)
if path_par not in sys.path:
    sys.path.append(path_par) 

# try a temporary fix for posit cloud
# path_loc = pathlib.Path("/cloud/lib/venv/lib/python3.13/site-packages/sisepuede/julia")#/lock.pid")
# if path_loc.is_dir():
#     subprocess.run(['chmod', '-R', '755', str(path_loc)], check = True, )


from sisepuede_tool.ui.app_shell import app_ui, server

app = App(app_ui, server)


def main() -> None:
    from shiny import run_app

    run_app(app)


if __name__ == "__main__":
    main()
