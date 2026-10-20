# AI_HANDOFF: context voor toekomstige ChatGPT/AI-sessies

> Dit bestand is geschreven als technisch overdrachtsdocument. Lees dit samen met `README.md`, `docs/ARCHITECTUUR.md`, `docs/BEHEER.md` en vooral de **actuele werkende broncode**. Ga nooit zonder inspectie uit van de oorspronkelijke starter-ZIP; die is verouderd.

## Doel van de gebruiker

Persoonlijk hobbyproject: nieuwe Disney+-verificatiemails in persoonlijke Gmail automatisch als sms versturen via Bird naar één of meer geautoriseerde nummers. De gebruiker verkiest **praktische, kleine wijzigingen** boven productiearchitectuur. Communicatie in het **Nederlands**, zonder onnodige complexiteit. Werk bij voorkeur stapsgewijs met exact kopieerbare Cloud Shell-commando's.

## Actuele toestand, bevestigd op 20 oktober 2026

- Gmail OAuth, Secret Manager, Gmail-filter `Disney-OTP`, Pub/Sub, private Cloud Run, Firestore en Bird Channels API zijn ingesteld.
- End-to-end test met echte Disney+-code is succesvol: de sms is aangekomen.
- `/renew-watch` bestaat via `watch_renewal.py` (Flask Blueprint), is gedeployed en heeft HTTP 200 opgeleverd.
- Cloud Scheduler-job `disney-otp-renew-watch` is ingesteld op dagelijks 06:00 Europe/Amsterdam. Gebruiker heeft bevestigd dat `state: ENABLED`, schedule en timezone kloppen.
- Google Cloud project-ID `disney-otp-notification`, regio `europe-west4`.
- Pub/Sub **topic** `disney-otp-notification` (zonder extra s); **subscription** `disney-otp-push-sub`.
- Cloud Run-service `disney-otp-sms`; serviceaccount `disney-otp-run@disney-otp-notification.iam.gserviceaccount.com`.
- Push/Scheduler-identiteit `disney-otp-push@disney-otp-notification.iam.gserviceaccount.com`.
- Firestore `(default)`, collectie `sms_delivery`.
- Secret Manager: `gmail-oauth-credentials` (JSON) en `bird-api-key`.
- Werkmap in Cloud Shell: `~/disney-otp-cloud-run-v2`.

## Zeer belangrijke details

1. **Bird is Channels API**, niet het API-model uit de originele starter:
   - `POST https://api.bird.com/workspaces/{BIRD_WORKSPACE_ID}/channels/{BIRD_CHANNEL_ID}/messages`.
   - `Authorization: AccessKey <BIRD_API_KEY>`.
   - Body: `receiver.contacts[].identifierKey='phonenumber'`, `identifierValue`, `body.type='text'`, `body.text.text`.
   - De oude `bk_eu1_`/`bk_us1_`-validatie en `platform.bird.com/v1/sms/messages` mogen niet terugkomen.
2. **Disney-mails zijn `text/html`**, geen `text/plain`. De werkende code gebruikt `HTMLParser` in `text_from_payload()`.
3. De originele verplichte zin `Use this passcode to verify the email address` is verwijderd. Werkende code zoekt één **uniek** zescijferig getal via `(?<!\d)\d{6}(?!\d)`.
4. De Gmail-push bevat `emailAddress` en `historyId`. Huidige code **negeert `historyId` voor daadwerkelijke history-retrieval** en gebruikt `messages.list` met het label en `newer_than:15m`; een bericht mag maximaal tien minuten oud zijn.
5. Firestore dedupe: SHA-256 van `message_id + '|' + recipient`, documentstatus `processing`, `accepted` of `review_required`. Eenmaal aangemaakt blokkeert het document nieuwe pogingen voor die ontvanger en dat bericht.
6. `/renew-watch` staat in het **aparte** `watch_renewal.py`, met Flask Blueprint geregistreerd in `main.py`. Een eerdere poging om deze route rechtstreeks aan `main.py` toe te voegen mislukte door slecht geplakte shell-tekst; niet zomaar dubbel toevoegen.
7. De lokale `env.yaml` is niet automatisch gesynchroniseerd met de draaiende Cloud Run-revisie. `--update-env-vars` wijzigt de service, volledige `gcloud run deploy --env-vars-file env.yaml` neemt alle lokale waarden opnieuw over.
8. `BIRD_SENDER` is een verouderd restant in de oude starterconfiguratie; het werkende Bird Channel bepaalt de afzender.

## Wat eerst te inspecteren bij nieuwe taak

Laat de gebruiker in Cloud Shell de relevante regels tonen zonder geheime waarden, bijvoorbeeld:

```bash
cd ~/disney-otp-cloud-run-v2
python3 -m py_compile main.py watch_renewal.py
grep -nE '^def |^@app\.|BIRD_WORKSPACE_ID|api.bird.com|HTMLParser|codes =|register_blueprint' main.py watch_renewal.py
gcloud run services logs read disney-otp-sms --region=europe-west4 --limit=30
```

Voor specifieke wijzigingen vraag gericht het **kleinst noodzakelijke codefragment**, bijvoorbeeld `sed -n '...'`, en vermijd lange heredoc-plakacties als die eerder in de Shell fout gingen. Maak altijd eerst een back-up of gebruik Git. Deel nooit tokens, volledige env-waarden, OTP's of echte nummers.

## Gebruikelijke gebruikersvragen

**Extra sms-nummers:** wijzig `SMS_RECIPIENTS` in `env.yaml`, nummers met komma's in E.164, en maak nieuwe Cloud Run-revisie met `gcloud run services update --update-env-vars=...` of volledige deploy. De code dedupliceert identieke nummers.

**Ander Bird Channel:** wijzig `BIRD_CHANNEL_ID`, en zo nodig `BIRD_WORKSPACE_ID`, zowel lokaal als op Cloud Run. Controleer of de bestaande Access Key bevoegd is voor dat kanaal.

**Gmail Watch verlopen:** controleer Scheduler-job, test `gcloud scheduler jobs run disney-otp-renew-watch --location=europe-west4`, controleer `/renew-watch` HTTP-status en zo nodig de OAuth-refresh-token.

**Mail gelabeld maar geen sms:** controleer `/pubsub`-logs; bij HTTP 200 zonder nieuwe `sms_delivery` wordt de mail waarschijnlijk gefilterd of code niet herkend. Kijk naar MIME, onderwerp, afzender, leeftijd en regex. Bij `review_required` eerst Bird onderzoeken, niet automatisch opnieuw versturen.

## Beperkingen bewust geaccepteerd

- Geen Gmail History API-cursor, geen recovery/replay.
- Geen expliciete SPF/DKIM/DMARC-verificatie.
- Geen automatische alerting, beperkte retries.
- Geen commercieel SLA of harde bezorggarantie.

Vraag niet opnieuw of de gebruiker een enterprise-grade architectuur wil tenzij de eisen veranderen. Wijs wel op concrete veiligheidsrisico's wanneer ze relevant zijn, bijvoorbeeld na uitbreiden naar derden.

## Eerlijkheid over bronnen

Dit document is gereconstrueerd uit een werkende conversatie en de oorspronkelijke `v2`-starter. **De actuele Cloud Shell-bestanden zijn niet rechtstreeks uit de repository opgehaald.** Bij afwijkingen geldt de code die momenteel daadwerkelijk draait. Schrijf niet dat onbekende zaken zijn geverifieerd of getest.
