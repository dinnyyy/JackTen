"""Launch the local poker table in your browser.

    python play.py
    python play.py --bots "JackTen=cmd:python my_bot.py" random random

Opens the home page: play against bots, watch bots play, or run simulations
and download the stats as CSV. --bots sets the default lineup on the home page.
Ctrl+C to quit.
"""

import argparse
import threading
import webbrowser

from ui.server import serve


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bots", nargs="+", default=["random"] * 5, help="default bot lineup")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    app, httpd = serve(args.host, args.port, args.bots)
    url = f"http://{args.host}:{args.port}/"
    print(f"JackTen table running at {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if app.session:
            app.session.stop()
        if app.sim:
            app.sim.cancel.set()
        httpd.server_close()


if __name__ == "__main__":
    main()
