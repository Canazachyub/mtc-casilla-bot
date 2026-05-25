"""Puebla el tab 'rucs' del Sheet con datos no sensibles del CSV local."""
import csv
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

SA_JSON  = Path(r"C:\PROGRAMACION\RESOLVE\Resolve\data\credentials\service-account.json")
SHEET_ID = "1qX-_7atHYQV2iF7By-I6uJHOMohNMDwMvWBW58d6Vco"
RUCS_CSV = Path(r"C:\PROGRAMACION\RESOLVE\Resolve\data\credentials\rucs.csv")

creds = Credentials.from_service_account_file(
    str(SA_JSON),
    scopes=["https://www.googleapis.com/auth/spreadsheets"],
)
gc = gspread.authorize(creds)
ws = gc.open_by_key(SHEET_ID).worksheet("rucs")

HEADERS = ["ruc", "empresa", "auth_method", "representante_legal", "activo", "sede"]

rows = []
with open(RUCS_CSV, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        rows.append([
            row.get("ruc", ""),
            row.get("empresa", ""),
            row.get("auth_method", ""),
            row.get("representante_legal", ""),
            "TRUE" if str(row.get("activo", "1")).strip() in ("1", "TRUE", "true") else "FALSE",
            row.get("sede", ""),
        ])

ws.clear()
ws.update(range_name="A1", values=[HEADERS] + rows)
print(f"OK: {len(rows)} empresas escritas en tab 'rucs' del Sheet.")
