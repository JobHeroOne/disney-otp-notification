# Disney OTP SMS Cloud Run starter

This app is an event-triggered Gmail label search (bounded to 15 minutes), not yet a Gmail History API cursor processor. It requires Gmail Watch renewal, a secured Pub/Sub push subscription, and a recovery strategy for lost notifications. The Firestore `sms_delivery` collection prevents automated resends of the same Gmail message to the same recipient. On ambiguous Bird failures it marks `review_required` for manual review instead of blindly retrying.

## Files
- `main.py`: Flask entrypoint, function `app`
- `requirements.txt`: Python dependencies

## Configuration
Cloud Run env vars: `GMAIL_ADDRESS`, `ALLOWED_SENDER`, `GMAIL_LABEL`, `SMS_RECIPIENTS`, `BIRD_SENDER`.
Secret env vars: `GMAIL_OAUTH_CREDENTIALS` from `gmail-oauth-credentials`, `BIRD_API_KEY` from `bird-api-key`.

Deploy with `gcloud run deploy disney-otp-sms --source . --function`? NO: this is a Flask application. Use `gcloud run deploy disney-otp-sms --source . --region europe-west4 --no-allow-unauthenticated --service-account=... --set-env-vars=... --set-secrets=...` and the Procfile supplied in this archive.

Important: Configure Pub/Sub push auth before use. Do not send an actual Disney code until verifying sender address and recipient authorization. Only authorized recipients should receive login codes. Bird `202 Accepted` is not delivery confirmation. This starter intentionally avoids logging secrets and OTP values.
