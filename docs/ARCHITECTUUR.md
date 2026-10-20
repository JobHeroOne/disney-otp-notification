# Architectuur en implementatiedetails

## 1. Doel en scope

Automatisch doorsturen van een recente, door Gmail gelabelde Disney+-verificatiemail naar vooraf ingestelde sms-ontvangers. Eén Gmail-bericht kan een sms per ontvanger opleveren. De implementatie is bewust klein gehouden voor persoonlijk gebruik.

## 2. Gmail en OAuth

- Gmail-filter kent label `Disney-OTP` toe aan mail met onderwerp `Your one-time passcode for Disney+`.
- `GMAIL_ADDRESS` is het Gmail-account dat via OAuth is geautoriseerd.
- `ALLOWED_SENDER` is het exact toegestane afzenderadres; dit is **niet** hetzelfde als SPF/DKIM/DMARC-validatie.
- OAuth is een Google OAuth Desktop Client met scope `https://www.googleapis.com/auth/gmail.readonly`.
- Google OAuth-toestemming is voor een persoonlijke Gmail-gebruiker als *External* geconfigureerd. Het consent-scherm is in productie gezet; de app hoeft voor uitsluitend persoonlijk gebruik niet per se publiek geverifieerd te zijn, maar waarschuwingen en quota kunnen gelden.
- Het refresh-token, client-ID, client-secret en token-URI staan als JSON in Secret Manager-secret `gmail-oauth-credentials`.
- De Cloud Run-runtime leest die JSON via omgevingsvariabele `GMAIL_OAUTH_CREDENTIALS` (Secret Manager-mount als omgevingsvariabele).

### Gmail Watch

`users.watch` gebruikt:

```json
{
  "topicName": "projects/disney-otp-notification/topics/disney-otp-notification",
  "labelIds": ["<DYNAMISCH_GMAIL_LABEL_ID>"],
  "labelFilterBehavior": "INCLUDE"
}
```

Het **interne label-ID** wordt telkens via `users.labels.list` gezocht op naam `Disney-OTP`; de zichtbare labelnaam is niet het label-ID.

Gmail verzendt een Pub/Sub-bericht met onder meer `emailAddress` en `historyId`. Deze melding bevat **niet** de volledige e-mail en **niet** de code. Bij het registreren of vernieuwen van Watch kan ook een eerste notificatie verschijnen.

De initiële watch werd op 20 oktober 2026 succesvol aangemaakt met `historyId` `4498946` en vervaltijd `2026-10-27T09:05:06.324Z`. Die historische waarden zijn alleen een implementatienotitie; **ze zijn geen actuele watch-status en moeten niet als cursor worden hergebruikt**.

### Mailboxverwerking

De bestaande `process_mailbox()`:

1. Haalt het interne label-ID via Gmail API op.
2. Zoekt berichten met dat label en `q=newer_than:15m` (maximaal vijf pagina's van honderd resultaten).
3. Haalt ieder bericht met `format=full` op.
4. Controleert label, exact onderwerp, exact e-mailafzenderadres, en `internalDate` van 0 tot 10 minuten oud.
5. Extraheert tekst uit `text/plain` of uit **HTML** via `html.parser.HTMLParser`.
6. Zoekt zescijferige cijferreeksen met regex `(?<!\d)\d{6}(?!\d)`; verwerkt het bericht alleen wanneer er **precies één uniek kandidaatgetal** is.
7. Roept `send_one(message_id, recipient, code)` aan voor iedere ontvanger.

De oorspronkelijke starter verwerkte alleen platte tekst en vereiste de zin `Use this passcode to verify the email address`. Beide beperkingen zijn tijdens de werkende implementatie verwijderd omdat de echte Disney+-mail alleen `text/html` bevatte.

**Belangrijk:** hoewel Gmail Watch een `historyId` levert, verwerkt de huidige `process_mailbox()` **geen Gmail History API-cursor**. Bij elke notificatie wordt recent gelabelde mail opnieuw doorzocht. Firestore voorkomt herhaalde verzendpogingen. Bij vertraging van meer dan tien minuten kan een code verloren gaan; er bestaat geen gegarandeerd herstelpad.

## 3. Pub/Sub en Cloud Run

**Google Cloud Project-ID:** `disney-otp-notification`.

**Topic:** `projects/disney-otp-notification/topics/disney-otp-notification`.

> Let op het verschil: het topic heet `disney-otp-notification`, niet `disney-otp-notifications`. Een eerdere poging met meervoud resulteerde in `Resource not found`.

Publisher-recht op het topic:

- `gmail-api-push@system.gserviceaccount.com`: `roles/pubsub.publisher`.

Push-subscriptie:

- Naam: `disney-otp-push-sub`.
- Push endpoint: `${SERVICE_URL}/pubsub`.
- Authenticatie: OIDC met `disney-otp-push@disney-otp-notification.iam.gserviceaccount.com`.
- Audience: de **basis-URL** van Cloud Run, dus zonder `/pubsub`.
- Ack deadline: 60 seconden.

Cloud Run:

- Service `disney-otp-sms` in `europe-west4`.
- Authenticatie verplicht via `--no-allow-unauthenticated`; de daadwerkelijke Cloud Run ingress-instelling is niet vastgesteld en moet apart worden gecontroleerd.
- Runtime serviceaccount `disney-otp-run@disney-otp-notification.iam.gserviceaccount.com`.
- Min. instances `0`; max. instances `1`; concurrency `1`; geheugen `512Mi`; request timeout `60s`.
- Flask-app met Gunicorn en `Procfile` (`web: gunicorn --bind :$PORT main:app`).
- Routes: `GET /` gezondheidscheck; `POST /pubsub` Gmail-verwerking; `POST /renew-watch` Gmail Watch-vernieuwing.
- `/renew-watch` is geïmplementeerd in `watch_renewal.py` als Flask Blueprint, geregistreerd in `main.py` via `app.register_blueprint(watch_bp)`.

Het `/pubsub`-endpoint controleert Gmail-adres en numeriek `historyId`, en roept dan `process_mailbox()` aan. Bij onbekend Gmail-adres antwoordt het met HTTP 200 en verwerkt het niets. Een HTTP 200 bevestigt alleen dat de applicatie de melding heeft afgehandeld, **niet** dat Bird een sms heeft verzonden.

## 4. Bird Channels API

Bij de eerste installatie gebruikte de starter een onjuist API-model met `bk_eu1_`/`bk_us1_`-sleutels. De werkende koppeling gebruikt:

```http
POST https://api.bird.com/workspaces/{BIRD_WORKSPACE_ID}/channels/{BIRD_CHANNEL_ID}/messages
Authorization: AccessKey <BIRD_API_KEY>
Content-Type: application/json
Accept: application/json
```

Schematisch payloadvoorbeeld (placeholdercode, niet echt):

```json
{
  "receiver": {
    "contacts": [
      {"identifierKey": "phonenumber", "identifierValue": "+31600000001"}
    ]
  },
  "body": {
    "type": "text",
    "text": {"text": "Je Disney+ verificatiecode is: 000000"}
  }
}
```

De API-sleutel staat in Secret Manager onder `bird-api-key`; bij een handmatige `GET /workspaces/{workspace}/channels/{channel}`-test gaf Bird HTTP 200 terug. De **uiteindelijke sms-aflevering is door de gebruiker bevestigd** na het toevoegen van HTML-herkenning.

De waarde `BIRD_SENDER` komt uit een oudere starterconfiguratie; de werkende Channels API gebruikt het kanaal en niet de eerdere sender-payload. Verifieer de actuele code voordat je deze variabele verwijdert of hergebruikt.

De code behandelt HTTP 200, 201 of 202 van Bird als *accepted*. Dit is geen garantie op bezorging op het toestel.

## 5. Firestore en deduplicatie

- Firestore Standard, Native, `(default)` database, regio `europe-west4`.
- Security rules: restrictive; server-to-server werkt met IAM.
- Cloud Run-runtime serviceaccount heeft `roles/datastore.user`.
- Collectie: `sms_delivery`.
- Document-ID: `SHA256(gmail_message_id + '|' + recipient_phone_number)`.

De functie `send_one()` voert `doc.create(...)` uit voordat Bird wordt aangeroepen. Een reeds bestaand document (Firestore Conflict) betekent dat deze combinatie van mail en ontvanger eerder is geprobeerd en wordt overgeslagen.

| Status | Betekenis |
|---|---|
| `processing` | Verzendpoging gestart, nog niet bevestigd |
| `accepted` | Bird API-verzoek geaccepteerd |
| `review_required` | Fout of onduidelijke uitkomst; geen automatische herhaling |

Een ambigu timeout-scenario kan ertoe leiden dat Bird wél verzond, terwijl Firestore `review_required` heeft. Verwijder daarom nooit lukraak documenten om verzendingen te herhalen.

## 6. Dagelijkse Gmail Watch-vernieuwing

- Cloud Scheduler-job: `disney-otp-renew-watch`.
- Regio: `europe-west4`.
- Schedule: `0 6 * * *`, timezone `Europe/Amsterdam`.
- Methode: `POST` naar `${SERVICE_URL}/renew-watch`.
- OIDC-serviceaccount: `disney-otp-push@disney-otp-notification.iam.gserviceaccount.com`.
- OIDC-audience: `${SERVICE_URL}`.
- Het endpoint herhaalt `users.watch` met het juiste label-ID en topic.
- Handmatige uitvoering is getest met `POST 200 /renew-watch` op 20 oktober 2026.

Dit proces vernieuwt de Gmail Watch-abonnementsduur, maar garandeert niet dat een ingetrokken OAuth-refresh-token automatisch wordt hersteld.

## 7. Dependencies

Volgens de starter:

```text
Flask>=3.0,<4
requests>=2.32,<3
google-auth>=2.35,<3
google-cloud-firestore>=2.19,<3
gunicorn>=22,<24
```

Het daadwerkelijke Cloud Run-runtime-image gebruikte tijdens debuggen Python 3.14. De actuele dependencies in Cloud Shell zijn leidend. Pinnen van runtime en dependencies is een mogelijke toekomstige verbetering.
