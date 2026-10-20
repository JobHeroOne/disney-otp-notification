
import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly"
]

flow = InstalledAppFlow.from_client_secrets_file(
    "client_secret.json",
    scopes=SCOPES
)

credentials = flow.run_local_server(
    host="localhost",
    port=0,
    open_browser=True,
    access_type="offline",
    prompt="consent"
)

# Controleer of de Gmail API bereikbaar is.
service = build(
    "gmail",
    "v1",
    credentials=credentials,
    cache_discovery=False
)

profile = service.users().getProfile(
    userId="me"
).execute()

print("Gmail-autorisatie geslaagd.")
print("Geautoriseerd account:", profile["emailAddress"])

if not credentials.refresh_token:
    raise RuntimeError(
        "Geen refresh-token ontvangen. "
        "Controleer de OAuth-configuratie."
    )

# Sla alleen de benodigde OAuth-gegevens op.
data = {
    "client_id": credentials.client_id,
    "client_secret": credentials.client_secret,
    "refresh_token": credentials.refresh_token,
    "token_uri": "https://oauth2.googleapis.com/token"
}

path = Path("gmail_credentials.json")

with path.open("x", encoding="utf-8") as file:
    json.dump(data, file, indent=2)

try:
    path.chmod(0o600)
except OSError:
    pass

print("OAuth-gegevens lokaal opgeslagen.")
print("Bestand:", path.resolve())
print("Deel dit bestand met niemand.")
