#!/usr/bin/env python3
"""Seed a HubSpot test account with demo contacts, companies, and deals.

Uses the same OAuth credentials issued for the Estuary demo. Reads them from
hubspot-capture/flow.yaml when present, otherwise from env vars CLIENT_ID,
CLIENT_SECRET, REFRESH_TOKEN.
"""
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path


def load_creds():
    cap = Path(__file__).parent.parent / "hubspot-capture" / "flow.yaml"
    if cap.exists():
        text = cap.read_text()
        ids = dict(re.findall(r'(client_id|client_secret|refresh_token):\s*"?([^"\s]+)"?', text))
        if all(k in ids for k in ("client_id", "client_secret", "refresh_token")):
            return ids["client_id"], ids["client_secret"], ids["refresh_token"]
    return os.environ["CLIENT_ID"], os.environ["CLIENT_SECRET"], os.environ["REFRESH_TOKEN"]


def fetch_access_token(client_id, client_secret, refresh_token):
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    })
    proc = subprocess.run(
        ["curl", "-sS", "--fail-with-body",
         "-X", "POST",
         "-H", "Content-Type: application/x-www-form-urlencoded",
         "--data", body,
         "https://api.hubapi.com/oauth/v1/token"],
        capture_output=True, text=True, timeout=30,
    )
    if proc.returncode != 0:
        sys.exit(f"token refresh failed: {proc.stdout} {proc.stderr}")
    return json.loads(proc.stdout)["access_token"]


def post(token, path, body):
    proc = subprocess.run(
        ["curl", "-sS",
         "-X", "POST",
         "-H", f"Authorization: Bearer {token}",
         "-H", "Content-Type: application/json",
         "--data", json.dumps(body),
         f"https://api.hubapi.com{path}"],
        capture_output=True, text=True, timeout=60,
    )
    return json.loads(proc.stdout) if proc.stdout else {}


COMPANIES = [
    ("Acme Co", "acmedemo.io"),
    ("Globex", "globexdemo.io"),
    ("Initech", "initechdemo.io"),
    ("Umbrella Corp", "umbrellademo.io"),
    ("Hooli", "hoolidemo.io"),
    ("Pied Piper", "piedpiperdemo.io"),
    ("Wonka Industries", "wonkademo.io"),
    ("Stark Industries", "starkdemo.io"),
    ("Cyberdyne Systems", "cyberdynedemo.io"),
    ("Tyrell Corp", "tyrelldemo.io"),
    ("Soylent Corp", "soylentdemo.io"),
    ("Bluth Company", "bluthdemo.io"),
    ("Vandelay Industries", "vandelaydemo.io"),
    ("Massive Dynamic", "massivedemo.io"),
    ("Oscorp", "oscorpdemo.io"),
]
FIRSTS = ["Alice", "Bob", "Carol", "Dave", "Eve", "Frank", "Grace", "Heidi",
          "Ivan", "Judy", "Karl", "Lily", "Mallory", "Nina", "Oscar", "Peggy",
          "Quentin", "Rivka", "Sybil", "Trent", "Ursula", "Victor", "Walter",
          "Xena", "Yara", "Zoe"]
LASTS = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
         "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
         "Wilson", "Anderson", "Thomas"]
DEAL_STAGES = [
    ("appointmentscheduled", 0.25),
    ("qualifiedtobuy", 0.20),
    ("presentationscheduled", 0.15),
    ("decisionmakerboughtin", 0.10),
    ("contractsent", 0.10),
    ("closedwon", 0.12),
    ("closedlost", 0.08),
]
DEAL_NAME_PARTS = [
    ("Q4", "Q1", "Q2", "Q3"),
    ("Renewal", "Expansion", "Upgrade", "Pilot", "Trial", "New Logo", "Add-on", "Multi-year", "Enterprise"),
    ("Deal", "Contract", "Engagement", "Opportunity"),
]


def weighted_choice(choices):
    total = sum(w for _, w in choices)
    r = random.random() * total
    upto = 0
    for c, w in choices:
        upto += w
        if r <= upto:
            return c
    return choices[-1][0]


def main():
    random.seed(42)
    client_id, client_secret, refresh_token = load_creds()
    token = fetch_access_token(client_id, client_secret, refresh_token)
    print(f"got access token (len={len(token)})")

    run_tag = int(time.time())  # makes emails unique per run so the seeder is re-runnable
    contacts = []
    for first in FIRSTS:
        last = random.choice(LASTS)
        domain = random.choice(COMPANIES)[1]
        email = f"{first.lower()}.{last.lower()}.{run_tag}@{domain}"
        contacts.append({
            "properties": {
                "email": email,
                "firstname": first,
                "lastname": last,
                "company": random.choice(COMPANIES)[0],
                "jobtitle": random.choice(["CEO", "CTO", "VP Eng", "VP Sales", "Director", "Manager", "Engineer"]),
                "lifecyclestage": random.choice(["lead", "marketingqualifiedlead", "salesqualifiedlead", "opportunity", "customer"]),
            }
        })
    r = post(token, "/crm/v3/objects/contacts/batch/create", {"inputs": contacts})
    print(f"contacts: {len(r.get('results', []))} created (status={r.get('status', 'COMPLETE')})")

    valid_industries = ["COMPUTER_SOFTWARE", "INFORMATION_TECHNOLOGY_AND_SERVICES",
                        "FINANCIAL_SERVICES", "RETAIL", "INTERNET",
                        "MANAGEMENT_CONSULTING", "MARKETING_AND_ADVERTISING",
                        "HOSPITAL_HEALTH_CARE", "BIOTECHNOLOGY"]
    companies = [{"properties": {"name": n, "domain": d, "industry": random.choice(valid_industries),
                                  "numberofemployees": random.choice([10, 50, 250, 1000, 5000])}} for n, d in COMPANIES]
    r = post(token, "/crm/v3/objects/companies/batch/create", {"inputs": companies})
    print(f"companies: {len(r.get('results', []))} created")

    deals = []
    for i in range(40):
        parts = (random.choice(DEAL_NAME_PARTS[0]), random.choice(COMPANIES)[0],
                 random.choice(DEAL_NAME_PARTS[1]), random.choice(DEAL_NAME_PARTS[2]))
        deals.append({
            "properties": {
                "dealname": " ".join(parts),
                "dealstage": weighted_choice(DEAL_STAGES),
                "pipeline": "default",
                "amount": str(random.choice([1500, 4800, 9200, 18000, 35000, 75000, 120000, 220000])),
                "closedate": int((time.time() + random.uniform(-30, 60) * 86400) * 1000),
            }
        })
    r = post(token, "/crm/v3/objects/deals/batch/create", {"inputs": deals})
    print(f"deals: {len(r.get('results', []))} created")


if __name__ == "__main__":
    main()
