#!/usr/bin/env python3
"""HubSpot OAuth helper — captures the redirect, exchanges the code for a refresh_token.

Usage:
    export HUBSPOT_CLIENT_ID=<your-client-id>
    export HUBSPOT_CLIENT_SECRET=<your-client-secret>
    python3 oauth_helper.py

Open the printed AUTHORIZE_URL in a browser, complete the consent flow, and
this script will print the resulting REFRESH_TOKEN. Paste that into your
capture spec (hubspot-capture/flow.yaml).

The HubSpot OAuth app's redirect URI must include http://localhost:16963/.
"""
import http.server
import json
import os
import socketserver
import subprocess
import sys
import threading
import urllib.parse

CLIENT_ID = os.environ.get("HUBSPOT_CLIENT_ID") or sys.exit(
    "set HUBSPOT_CLIENT_ID (copy it via `hs project open` → app → Auth tab)"
)
CLIENT_SECRET = os.environ.get("HUBSPOT_CLIENT_SECRET") or sys.exit(
    "set HUBSPOT_CLIENT_SECRET (copy it via `hs project open` → app → Auth tab)"
)
REDIRECT_URI = "http://localhost:16963/"
PORT = 16963

REQUIRED_SCOPES = [
    "oauth",
    "crm.lists.read",
    "crm.objects.companies.read",
    "crm.objects.companies.write",
    "crm.objects.contacts.read",
    "crm.objects.contacts.write",
    "crm.objects.deals.read",
    "crm.objects.deals.write",
    "crm.objects.owners.read",
    "crm.schemas.companies.read",
    "crm.schemas.contacts.read",
    "crm.schemas.deals.read",
    "e-commerce",
    "forms",
    "tickets",
]
OPTIONAL_SCOPES = [
    "automation",
    "content",
    "crm.objects.custom.read",
    "crm.objects.feedback_submissions.read",
    "crm.objects.goals.read",
    "crm.objects.marketing_events.read",
    "crm.objects.orders.read",
    "crm.schemas.custom.read",
    "marketing.campaigns.read",
]

AUTH_URL = (
    "https://app.hubspot.com/oauth/authorize?"
    + urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "scope": " ".join(REQUIRED_SCOPES),
        "optional_scope": " ".join(OPTIONAL_SCOPES),
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "state": "estuary-demo",
    })
)

result = {}
done = threading.Event()


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        qs = urllib.parse.urlparse(self.path).query
        params = dict(urllib.parse.parse_qsl(qs))
        if "code" in params:
            result["code"] = params["code"]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>OAuth callback received.</h1><p>You can close this tab.</p>")
            done.set()
        elif "error" in params:
            result["error"] = params
            self.send_response(400)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(json.dumps(params).encode())
            done.set()
        else:
            self.send_response(204)
            self.end_headers()


def serve():
    with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
        httpd.timeout = 1
        while not done.is_set():
            httpd.handle_request()


def main():
    print("AUTHORIZE_URL:", AUTH_URL, flush=True)
    t = threading.Thread(target=serve, daemon=True)
    t.start()
    print(f"Listening on http://127.0.0.1:{PORT}/ ...", flush=True)
    if not done.wait(timeout=600):
        print("Timed out after 10 minutes waiting for OAuth callback.", file=sys.stderr)
        sys.exit(1)
    if "error" in result:
        print("OAuth error:", json.dumps(result["error"]), file=sys.stderr)
        sys.exit(1)

    code = result["code"]
    print("CODE:", code, flush=True)
    body = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "code": code,
    })
    proc = subprocess.run(
        [
            "curl", "-sS", "--fail-with-body",
            "-X", "POST",
            "-H", "Content-Type: application/x-www-form-urlencoded",
            "--data", body,
            "https://api.hubapi.com/oauth/v1/token",
        ],
        capture_output=True, text=True, timeout=30,
    )
    if proc.returncode != 0:
        print("Token exchange failed:", proc.stdout, proc.stderr, file=sys.stderr)
        sys.exit(1)
    payload = json.loads(proc.stdout)

    print("REFRESH_TOKEN:", payload["refresh_token"], flush=True)
    print("ACCESS_TOKEN:", payload["access_token"], flush=True)
    print("EXPIRES_IN:", payload.get("expires_in"), flush=True)


if __name__ == "__main__":
    main()
