# Disney+ OTP via Gmail naar Bird SMS

Persoonlijke, eventgestuurde automatisering die een nieuwe Disney+-verificatiecode uit Gmail leest en via Bird SMS doorstuurt naar één of meer vooraf ingestelde telefoonnummers.

> **Status op 20 oktober 2026:** werkend getest van Disney+-mail tot ontvangen sms. Gmail Watch-vernieuwing via Cloud Scheduler is eveneens getest (HTTP 200). Dit is een persoonlijk project, geen generiek of commercieel product.
>
> **Let op:** deze repositorydocumentatie is samengesteld uit de implementatiestappen en codefragmenten tijdens het bouwen. Controleer voor codewijzigingen de actuele `main.py`, `watch_renewal.py` en `env.yaml` in Cloud Shell. De oorspronkelijke starterbestanden zijn tussentijds gewijzigd.

## Overzicht

```text
Disney+ verificatiemail
         |
         v
Gmail-filter: label Disney-OTP
         |
         v
Gmail API users.watch
         |
         v
Google Pub/Sub-topic: disney-otp-notification
         |
         v
Push-subscriptie: disney-otp-push-sub (OIDC)
         |
         v
Private Cloud Run: disney-otp-sms  POST /pubsub
         |                  |
         |                  +--> Gmail API: recente gelabelde mails ophalen
         |                  +--> onderwerp/afzender/leeftijd/code controleren
         |                  +--> Firestore: verzendpoging per mail + nummer
         v
Bird Channels API --> SMS naar SMS_RECIPIENTS

Cloud Scheduler: disney-otp-renew-watch
         |
         v
Private Cloud Run: POST /renew-watch
         |
         v
Gmail API users.watch vernieuwen (dagelijks)
```

## Documentatie

- [Architectuur en exacte configuratie](docs/ARCHITECTUUR.md)
- [Beheer, aanpassingen en foutopsporing](docs/BEHEER.md)
- [Technische overdracht voor een AI-assistent](docs/AI_HANDOFF.md)
- [Beveiliging en bekende beperkingen](docs/BEVEILIGING.md)
- [Voorbeeld van omgevingsvariabelen](env.example.yaml)

## Belangrijkste cloud-resources

| Resource | Waarde |
|---|---|
| Google Cloud project | `disney-otp-notification` |
| Regio Cloud Run / Firestore | `europe-west4` (Nederland) |
| Cloud Run-service | `disney-otp-sms` |
| Cloud Run serviceaccount | `disney-otp-run@disney-otp-notification.iam.gserviceaccount.com` |
| Pub/Sub-topic | `disney-otp-notification` (**enkelvoud**, niet `disney-otp-notifications`) |
| Push-subscriptie | `disney-otp-push-sub` |
| Pub/Sub push-identiteit | `disney-otp-push@disney-otp-notification.iam.gserviceaccount.com` |
| Firestore-database | `(default)`, Standard, Native, restrictive rules |
| Firestore-collectie | `sms_delivery` |
| Gmail-label | `Disney-OTP` |
| Cloud Scheduler-taak | `disney-otp-renew-watch`, dagelijks 06:00, `Europe/Amsterdam` |
| Gmail Watch onderwerp | `Your one-time passcode for Disney+` |

De service-URL kan worden opgevraagd met `gcloud run services describe`; gebruik geen hardgecodeerde URL als configuratiebron.

## Snelle beheercommando's

```bash
export PROJECT_ID=disney-otp-notification
export REGION=europe-west4
gcloud config set project "$PROJECT_ID"

# Service en logs
gcloud run services describe disney-otp-sms --region="$REGION"
gcloud run services logs read disney-otp-sms --region="$REGION" --limit=50

# Watch-vernieuwing controleren
gcloud scheduler jobs describe disney-otp-renew-watch \
  --location="$REGION" \
  --format='yaml(state,schedule,timeZone,lastAttemptTime,status)'

# Watch-vernieuwing nu uitvoeren
gcloud scheduler jobs run disney-otp-renew-watch --location="$REGION"
```

## Configuratie wijzigen

Pas voor blijvende wijzigingen **zowel** de actieve Cloud Run-configuratie als de lokale `env.yaml` aan. Anders kan een latere volledige deployment oudere waarden herstellen.

**Alleen telefoonnummers wijzigen**, zonder herbouw:

```bash
gcloud run services update disney-otp-sms --region=europe-west4 \
  --update-env-vars='SMS_RECIPIENTS=+31600000001,+31600000002'
```

**Alleen Bird-kanaal wijzigen**, zonder herbouw:

```bash
gcloud run services update disney-otp-sms --region=europe-west4 \
  --update-env-vars='BIRD_CHANNEL_ID=VERVANG_DOOR_NIEUW_ID'
```

Voor codewijzigingen: zie [deploy-instructies](docs/BEHEER.md#deployen-en-configuratie-bijwerken).

## Privacy

Commit **nooit** `env.yaml`, OAuth-clientbestanden, `gmail_credentials.json`, API-sleutels, ontvangen verificatiecodes, telefoonnummers of logdumps met gevoelige gegevens. Een `.gitignore` en een opgeschoond `env.example.yaml` zijn meegeleverd. Deel verificatiecodes uitsluitend met telefoonnummers die je zelf beheert of waarvoor je expliciete toestemming hebt.

## Licentie en verantwoordelijkheid

Privé-implementatie. Gebruik en onderhoud zijn voor rekening van de beheerder. Bird-kosten, Google Cloud-quota en het intrekken van OAuth-toestemming kunnen de werking beïnvloeden.
