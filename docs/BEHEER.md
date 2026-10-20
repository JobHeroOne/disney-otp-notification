# Beheer, wijzigingen en foutopsporing

Deze handleiding gaat uit van Google Cloud Shell en een lokale werkmap `~/disney-otp-cloud-run-v2` met de **actueel werkende** broncode, inclusief `main.py`, `watch_renewal.py`, `requirements.txt`, `Procfile` en een privé `env.yaml`.

## 1. Basiscontroles

```bash
export PROJECT_ID=disney-otp-notification
export REGION=europe-west4
export SERVICE=disney-otp-sms
gcloud config set project "$PROJECT_ID"

# Huidige serviceconfiguratie en URL
gcloud run services describe "$SERVICE" --region="$REGION"

# Recente requests en fouten
gcloud run services logs read "$SERVICE" --region="$REGION" --limit=50

# Pub/Sub-configuratie
gcloud pubsub topics list --format='table(name)'
gcloud pubsub subscriptions describe disney-otp-push-sub \
  --format='yaml(name,topic,pushConfig)'

# Dagelijkse vernieuwing
gcloud scheduler jobs describe disney-otp-renew-watch \
  --location="$REGION" \
  --format='yaml(state,schedule,timeZone,lastAttemptTime,status)'
```

## 2. Deployen en configuratie bijwerken

**Let op:** `env.yaml` in Cloud Shell wordt **niet automatisch** naar een bestaande Cloud Run-revisie gesynchroniseerd. Een wijziging vraagt een nieuwe revisie via een volledige deploy of `gcloud run services update`.

### Optie A: alleen omgevingsvariabelen veranderen (sneller)

Pas daarnaast altijd de bijbehorende waarden in je lokale privébestand `env.yaml` aan.

```bash
# Voorbeeld: twee zelf beheerde ontvangers
gcloud run services update disney-otp-sms --region=europe-west4 \
  --update-env-vars='SMS_RECIPIENTS=+31600000001,+31600000002'

# Voorbeeld: ander Bird Channel ID
gcloud run services update disney-otp-sms --region=europe-west4 \
  --update-env-vars='BIRD_CHANNEL_ID=VERVANG_DOOR_NIEUW_ID'

# Voorbeeld: channel in een andere workspace
gcloud run services update disney-otp-sms --region=europe-west4 \
  --update-env-vars='BIRD_WORKSPACE_ID=VERVANG,BIRD_CHANNEL_ID=VERVANG'
```

Na elke wijziging is een nieuwe Cloud Run-revisie actief. De Pub/Sub-subscriptie, Watch en service-URL blijven normaal gesproken ongewijzigd.

### Optie B: code of alle waarden uit env.yaml opnieuw deployen

```bash
cd ~/disney-otp-cloud-run-v2
python3 -m py_compile main.py watch_renewal.py

gcloud run deploy disney-otp-sms \
  --source . \
  --region europe-west4 \
  --service-account disney-otp-run@disney-otp-notification.iam.gserviceaccount.com \
  --no-allow-unauthenticated \
  --min-instances 0 \
  --max-instances 1 \
  --concurrency 1 \
  --memory 512Mi \
  --timeout 60 \
  --env-vars-file env.yaml \
  --set-secrets GMAIL_OAUTH_CREDENTIALS=gmail-oauth-credentials:latest,BIRD_API_KEY=bird-api-key:latest
```

Vervang `env.yaml` nooit door `env.example.yaml`: de laatste bevat placeholders. Zorg dat je wijzigingen ook in Git staan **zonder** echte sleutels, telefoonnummers of privé-instellingen te committen.

## 3. Gmail Watch nu vernieuwen

```bash
gcloud scheduler jobs run disney-otp-renew-watch --location=europe-west4

gcloud run services logs read disney-otp-sms \
  --region=europe-west4 --limit=30
```

Zoek naar `POST 200 .../renew-watch`. Het vernieuwingsendpoint mag na een geslaagde registratie een nieuwe Gmail-notificatie veroorzaken. Dat is normaal. Een HTTP 200 bevestigt succesvolle requestverwerking, maar voor de daadwerkelijke Watch-expiratiedatum moet je desgewenst de response van Gmail API raadplegen.

## 4. Testen

### Pub/Sub naar Cloud Run, zonder echte mail

```bash
gcloud pubsub topics publish disney-otp-notification \
  --message='{"emailAddress":"test@example.com","historyId":"123456789"}'

gcloud run services logs read disney-otp-sms --region=europe-west4 --limit=30
```

Deze fictieve melding moet genegeerd worden doordat `emailAddress` afwijkt van `GMAIL_ADDRESS`. Verwacht HTTP 200, **geen** sms. Let erop dat reeds aanwezige Pub/Sub-retries andere logregels kunnen veroorzaken.

### Echte end-to-end test

1. Vraag **één** nieuwe Disney+-code aan.
2. Controleer of de mail binnenkomt met label `Disney-OTP`.
3. Kijk naar een recente `POST 200 .../pubsub` of een HTTP 500-fout.
4. Controleer Firestore-collectie `sms_delivery` op een nieuwe registratie.
5. Controleer of alle ingestelde ontvangers een sms ontvangen. Deel de code niet in tickets, GitHub Issues of AI-chats.

**Aflevering is door de gebruiker in oktober 2026 getest na het toevoegen van HTML-ondersteuning.** Een latere codewijziging of Bird-kanaalwisseling vereist opnieuw testen.

## 5. Foutopsporing

| Symptoom | Meest waarschijnlijke diagnose | Actie |
|---|---|---|
| Gmail ontvangt mail met label, maar geen nieuwe Cloud Run POST | Gmail Watch verlopen, Pub/Sub-permissies of subscription | Scheduler-status, topic IAM en push-config controleren |
| `/pubsub` HTTP 401/403 | OIDC/Cloud Run Invoker-probleem | Push-serviceaccount, audience en invoker-policy controleren |
| `/pubsub` HTTP 500 | Gmail-, Firestore- of Bird-fout | Cloud Run-traceback en foutstatus bekijken; geen secrets delen |
| `/pubsub` HTTP 200, geen Firestore-document | Mail wordt overgeslagen, of testbericht genegeerd | Onderwerp, afzender, Gmail-label, leeftijd, HTML-codeherkenning controleren |
| Firestore `accepted`, geen sms op telefoon | Bird accepteerde aanvraag, aflevering niet bewezen | Delivery status in Bird controleren, kanaal/saldo/netwerk onderzoeken |
| Firestore `review_required` | Fout/onduidelijke Bird-uitkomst | Bird controleren voordat je eventueel handmatig opnieuw verzendt |
| Firestore `processing` blijft staan | Crash tussen registratie en statusupdate | Bird raadplegen, nooit blind Firestore-document verwijderen |
| Geen nieuwe codes na zeven dagen | Gmail Watch werd niet vernieuwd | Scheduler en `/renew-watch` controleren |
| OAuth 400 `invalid_grant` | Refresh-token ingetrokken of verlopen | Persoonlijke OAuth-autorisatie opnieuw uitvoeren; secret bijwerken |
| Worker failed to boot, melding `bk_eu1_` | Oude Bird-startercode gedeployed | Werkende Bird Channels API-code herstellen en redeployen |

### Bekende historische fouten en oplossingen

- `Resource not found (resource=disney-otp-notifications)`: het echte topic gebruikt het **enkelvoud** `disney-otp-notification`.
- HTTP 503 bij startup door `Bird API key must be bk_eu1_... or bk_us1_...`: oude client verwachtte een ander sleuteltype; vervangen door `AccessKey` via `api.bird.com`.
- HTTP 200 zonder sms en zonder Firestore-collectie: de mail bevatte uitsluitend `text/html`; HTML-parser toegevoegd en te strikte vaste Engelse zin verwijderd.
- Een shell-plakactie met `cat >> main.py <<'PY'` brak een endpoint; code hersteld uit `main.py.before-watch-renewal`, waarna `/renew-watch` in `watch_renewal.py` is ondergebracht.

## 6. OAuth- en Bird-secrets

Cloud Run gebruikt de Secret Manager-secrets:

- `gmail-oauth-credentials`: JSON met `client_id`, `client_secret`, `refresh_token`, `token_uri`.
- `bird-api-key`: Bird API Access Key als tekst.

Alleen de runtime-identiteit `disney-otp-run@...` heeft secret-toegang nodig (`roles/secretmanager.secretAccessor` op deze twee secrets). Verander secrets alleen na gecontroleerde rotatie; een runtime met `latest` gebruikt de secretversie volgens de Cloud Run/Secret Manager-resolutie. Controleer na wijziging desnoods met een nieuwe revisie en end-to-end test.

**Nooit secretinhoud naar het scherm sturen om te debuggen.** Controleer hoogstens aanwezigheid, naam en versie.

## 7. Rechten en herstel

- Cloud Run-runtime: `roles/datastore.user` en secretAccessor voor de twee genoemde secrets.
- Gmail push-identiteit: `roles/pubsub.publisher` op het topic.
- Push-serviceaccount: `roles/run.invoker` op `disney-otp-sms`.
- Scheduler gebruikt dezelfde push-identiteit om `/renew-watch` beveiligd aan te roepen.
- Om OIDC te configureren moet de beheerder de juiste `iam.serviceAccounts.actAs`-rechten hebben; een mislukte Scheduler-call kan aanvullende serviceagent-rechten vereisen.

Gmail Watch moet opnieuw worden aangemaakt na langdurige uitval. De bestaande code leest geen `users.history.list`, zodat gemiste mails niet automatisch worden gereconstrueerd.

## 8. Optioneel onderhoud

- Bij wijzigingen in afzender, e-mailsjabloon of taal: pas de controles in `process_mailbox()` aan en test opnieuw.
- Bij twijfel over sms-ontvangst: eerst Bird Delivery Logs/status bekijken, daarna Firestore. Dit voorkomt duplicaten.
- Bewaar een kopie van de werkende bronbestanden in een **private** repository (zonder secrets).
- Controleer periodiek Cloud Scheduler `lastAttemptTime`/`status` en Cloud Run-fouten. Er is nog geen automatische foutalerting ingesteld.
