# Beveiliging, privacy en bekende beperkingen

Dit is een bewust eenvoudig persoonlijk project dat eenmalige accountverificatiecodes verwerkt. Zulke codes zijn **inloggevoelig**. Deel ze alleen met telefoonnummers die je zelf beheert of die expliciet bevoegd zijn om toegang tot het account te gebruiken.

## Bestaande waarborgen

- Gmail OAuth met `gmail.readonly` (geen mail verzenden, verwijderen of wijzigen via de app).
- Gmail-filter en extra controle op label, exact onderwerp, afzenderadres, recente ontvangst en een unieke zescijferige code.
- Privé Cloud Run-service, geauthenticeerde Pub/Sub-push en Scheduler-aanroep met OIDC.
- Bird API-sleutel en Gmail OAuth-gegevens in Google Secret Manager, niet in broncode.
- Firestore-document per Gmail-bericht en ontvanger voorkomt dubbele geautomatiseerde verzendpogingen.
- De applicatie is ontworpen om geen OTP, API-sleutels en telefoonnummers expliciet te loggen.
- Geen automatische retry van een onduidelijke Bird-uitkomst.

## Beperkingen

1. **Afzendercontrole is geen e-mailauthenticatie.** `From` kan worden vervalst; SPF/DKIM/DMARC of Gmail-authentication-resultaten worden nog niet gecontroleerd.
2. **OAuth-scope is breed.** `gmail.readonly` kan meer lezen dan alleen berichten met het `Disney-OTP`-label. Filtering in Python is geen beperking van de verleende API-toegang.
3. **Geen History API-cursor.** Bij notificaties zoekt de app slechts de laatste 15 minuten en accepteert berichten tot tien minuten oud. Storing of vertraging kan een bericht missen.
4. **Codeherkenning is generiek.** Een unieke zescijferige reeks in HTML wordt als code beschouwd. Als de mailopmaak verandert, kan een verkeerde reeks worden opgepikt of geen code gevonden worden.
5. **Geen bezorggarantie.** Bird HTTP `accepted` is geen bewijs dat het bericht op de telefoon is aangekomen.
6. **Geen automatische probleemmelding.** Fouten zijn te zien in Cloud Run, Scheduler en Bird, maar er is geen monitoring-alert.
7. **Deduplicatie is conservatief.** Firestore `processing` of `review_required` blokkeert automatisch opnieuw sturen voor hetzelfde bericht/nummer; dat kan incidenteel een sms kosten.
8. **Geen rate-limit per ontvanger buiten reguliere Cloud Run-instellingen.** Onverwacht veel passende mails kunnen tot sms-kosten leiden.
9. **Eenmalige codes zijn gevoelig.** SMS is niet hetzelfde beveiligingsniveau als een authenticator/passkey en kan onder andere door nummerovername worden onderschept.

## Repositoryhygiëne

**Niet committen:** `env.yaml`, `.env`, `gmail_credentials.json`, `credentials.json`, OAuth-tokens, sleutels, logbestanden, echte sms-nummers, echte OTP-voorbeelden en secret-exportbestanden.

Het `env.example.yaml` bevat alleen placeholders. Zet ook geen echte nummers of tokens in GitHub Issues of AI-prompts.

## Veilige wijzigingen

- Maak vóór een codewijziging een back-up of Git-commit.
- Controleer syntax via `python3 -m py_compile main.py watch_renewal.py`.
- Deploy met `--no-allow-unauthenticated`.
- Test eerst de Pub/Sub-route met een fictief e-mailadres.
- Test daarna hoogstens één echte verificatiecode; controleer Firestore en Bird als er twijfel is.
- Leg veranderingen in codeherkenning en API-payload vast in deze documentatie.
