#!/usr/bin/env python3
"""Log in to Zerodha Kite Connect and save today's access token.

    python3 india/kite_login.py

Reads api_key and api_secret from ~/.kite/credentials.json (outside this
repo). Prints the login URL, asks for the request_token on the redirect
URL, and exchanges it at Kite's session endpoint. The checksum is
sha256(api_key + request_token + api_secret). The access token is written
to ~/.kite/token.json with today's date. The secret and the token are
never printed.

credentials.json:
    {"api_key": "...", "api_secret": "..."}

Nothing here places an order. Standard library only.
"""

import datetime
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

LOGIN_URL = "https://kite.zerodha.com/connect/login"
SESSION_URL = "https://api.kite.trade/session/token"
CRED_PATH = os.path.expanduser("~/.kite/credentials.json")
TOKEN_PATH = os.path.expanduser("~/.kite/token.json")


class LoginError(Exception):
    pass


def load_credentials(path):
    """api_key and api_secret. The file stays outside the repo."""
    if not os.path.isfile(path):
        raise LoginError("put api_key and api_secret in %s" % path)
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise LoginError("cannot read %s: %s" % (path, exc))
    if not isinstance(data, dict):
        raise LoginError("%s must be a JSON object" % path)
    api_key = str(data.get("api_key") or "").strip()
    api_secret = str(data.get("api_secret") or "").strip()
    if not api_key or not api_secret:
        raise LoginError("%s needs api_key and api_secret" % path)
    return api_key, api_secret


def login_url(api_key):
    query = urllib.parse.urlencode([("v", "3"), ("api_key", api_key)])
    return LOGIN_URL + "?" + query


def request_token_from(text):
    """The token itself, or the whole redirect URL that carries it."""
    raw = (text or "").strip()
    if "request_token=" in raw:
        if "://" not in raw:
            raw = "https://local/?" + raw.split("?", 1)[-1]
        values = urllib.parse.parse_qs(urllib.parse.urlparse(raw).query).get("request_token") or []
        if not values or not values[0].strip():
            raise LoginError("the redirect URL has no request_token")
        return values[0].strip()
    if not raw or any(ch.isspace() for ch in raw):
        raise LoginError("paste the request_token from the redirect URL")
    return raw


def checksum(api_key, request_token, api_secret):
    """sha256(api_key + request_token + api_secret), hex."""
    raw = (api_key + request_token + api_secret).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _message(raw):
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, AttributeError):
        return ""
    if isinstance(data, dict):
        return str(data.get("message") or data.get("error_type") or "")
    return ""


def urlopen_send(method, url, fields, headers):
    """One HTTP call. Returns (status, body). HTTP errors come back as statuses."""
    data = None
    if fields is not None:
        data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    if fields is not None:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        resp = urllib.request.urlopen(req, timeout=60)
        return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def exchange(api_key, api_secret, request_token, send=None):
    """POST the checksum. Returns the access token. Does not print it."""
    send = send or urlopen_send
    form = {
        "api_key": api_key,
        "request_token": request_token,
        "checksum": checksum(api_key, request_token, api_secret),
    }
    headers = {"X-Kite-Version": "3"}
    status, body = send("POST", SESSION_URL, form, headers)
    try:
        data = json.loads(body.decode("utf-8"))
    except (ValueError, AttributeError):
        data = None
    if status != 200 or not isinstance(data, dict) or data.get("status") != "success":
        detail = _message(body) if body else ""
        raise LoginError("Kite did not return a session (%s)%s" % (
            status, (": " + detail) if detail else ""))
    token = str(((data.get("data") or {}).get("access_token")) or "").strip()
    if not token:
        raise LoginError("Kite returned a session with no access token")
    return token


def save_token(path, access_token, day):
    """Write {access_token, date}. The file is outside the repo."""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    payload = {"access_token": access_token, "date": day.isoformat()}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
        fh.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def load_token(path, day):
    """Today's access token. A token saved on another date is refused."""
    if not os.path.isfile(path):
        raise LoginError("no token at %s. Run python3 india/kite_login.py" % path)
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise LoginError("cannot read %s: %s" % (path, exc))
    saved = str((data or {}).get("date") or "")
    token = str((data or {}).get("access_token") or "").strip()
    if saved != day.isoformat() or not token:
        raise LoginError("access token is for %s, today is %s. Run python3 india/kite_login.py" % (
            saved or "an unknown day", day.isoformat()))
    return token


def main(argv=None, input_fn=None, send=None, today=None, cred_path=None, token_path=None):
    cred_path = cred_path or CRED_PATH
    token_path = token_path or TOKEN_PATH
    ask = input_fn or input
    day = today or datetime.date.today()
    try:
        api_key, api_secret = load_credentials(cred_path)
        print(login_url(api_key))
        pasted = ask("Paste the request_token from the redirect URL: ")
        request_token = request_token_from(pasted)
        access_token = exchange(api_key, api_secret, request_token, send)
        save_token(token_path, access_token, day)
    except (LoginError, OSError, urllib.error.URLError) as exc:
        print("kite_login.py: %s" % exc, file=sys.stderr)
        return 1
    print("Saved the access token for %s." % day.isoformat())
    return 0


if __name__ == "__main__":
    sys.exit(main())
