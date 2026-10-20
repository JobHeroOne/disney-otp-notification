import base64
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from email.utils import parseaddr

import google.auth
from flask import Flask, request
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.credentials import Credentials
from google.cloud import firestore
import requests

app = Flask(__name__)
db = firestore.Client()

GMAIL_ADDRESS = os.environ['GMAIL_ADDRESS'].lower().strip()
ALLOWED_SENDER = os.environ['ALLOWED_SENDER'].lower().strip()
LABEL_NAME = os.environ.get('GMAIL_LABEL', 'Disney-OTP')
SUBJECT = 'Your one-time passcode for Disney+'
RECIPIENTS = list(dict.fromkeys(x.strip() for x in os.environ['SMS_RECIPIENTS'].split(',') if x.strip()))
BIRD_SENDER = os.environ['BIRD_SENDER']
BIRD_KEY = os.environ['BIRD_API_KEY'].strip()
OAUTH = json.loads(os.environ['GMAIL_OAUTH_CREDENTIALS'])
if not RECIPIENTS or not all(re.fullmatch(r'\+[1-9]\d{7,14}', n) for n in RECIPIENTS):
    raise ValueError('SMS_RECIPIENTS must contain E.164 numbers')
if not re.fullmatch(r'bk_(eu1|us1)_.+', BIRD_KEY):
    raise ValueError('Bird API key must be bk_eu1_... or bk_us1_...')
BIRD_REGION = BIRD_KEY.split('_')[1]


def gmail():
    creds = Credentials(
        token=None,
        refresh_token=OAUTH['refresh_token'],
        token_uri=OAUTH.get('token_uri', 'https://oauth2.googleapis.com/token'),
        client_id=OAUTH['client_id'],
        client_secret=OAUTH['client_secret'],
        scopes=['https://www.googleapis.com/auth/gmail.readonly'],
    )
    return AuthorizedSession(creds)


def get_json(session, url, params=None):
    r = session.get(url, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def text_from_payload(payload):
    mime = payload.get('mimeType', '')
    if mime == 'text/plain' and payload.get('body', {}).get('data'):
        return base64.urlsafe_b64decode(payload['body']['data'] + '===').decode('utf-8', 'replace')
    for part in payload.get('parts', []):
        value = text_from_payload(part)
        if value:
            return value
    return ''


def send_one(message_id, recipient, code):
    # No OTPs, numbers, or API keys are written to logs.
    doc_id = hashlib.sha256((message_id + '|' + recipient).encode()).hexdigest()
    doc = db.collection('sms_delivery').document(doc_id)
    try:
        doc.create({'status': 'processing', 'created_at': firestore.SERVER_TIMESTAMP})
    except Exception as exc:
        # If document exists, this recipient has already been attempted.
        if exc.__class__.__name__ == 'Conflict':
            return
        raise
    payload = {
        'to': recipient,
        'from': BIRD_SENDER,
        'text': f'Je Disney+ verificatiecode is: {code}',
        'category': 'authentication',
    }
    try:
        response = requests.post(
            f'https://{BIRD_REGION}.platform.bird.com/v1/sms/messages',
            headers={
                'Authorization': f'Bearer {BIRD_KEY}',
                'Idempotency-Key': doc_id,
            },
            json=payload,
            timeout=15,
        )
        if response.status_code != 202:
            raise RuntimeError(f'Bird returned HTTP {response.status_code}')
        doc.update({'status': 'accepted', 'accepted_at': firestore.SERVER_TIMESTAMP})
    except Exception:
        # Keep the processing record for manual review; do not retry blindly,
        # since an SMS may have been accepted before a timeout occurred.
        doc.update({'status': 'review_required', 'updated_at': firestore.SERVER_TIMESTAMP})
        raise


def process_mailbox():
    session = gmail()
    base = 'https://gmail.googleapis.com/gmail/v1/users/me'
    labels = get_json(session, f'{base}/labels').get('labels', [])
    label_id = next((x['id'] for x in labels if x['name'] == LABEL_NAME), None)
    if not label_id:
        raise RuntimeError('Configured Gmail label was not found')
    # Bounded search on each push; the watch itself is event driven.
    # A production recovery job is still recommended for lost notifications.
    page_token = None
    for _ in range(5):
        params = {'labelIds': label_id, 'maxResults': 100, 'q': 'newer_than:15m'}
        if page_token:
            params['pageToken'] = page_token
        batch = get_json(session, f'{base}/messages', params)
        for item in batch.get('messages', []):
            msg = get_json(session, f"{base}/messages/{item['id']}", {'format': 'full'})
            if label_id not in msg.get('labelIds', []):
                continue
            headers = {h['name'].lower(): h['value'] for h in msg.get('payload', {}).get('headers', [])}
            if headers.get('subject') != SUBJECT:
                continue
            if parseaddr(headers.get('from', ''))[1].lower() != ALLOWED_SENDER:
                continue
            # Only act on newly received messages, never old replayed mail.
            age_ms = int(time.time() * 1000) - int(msg.get('internalDate', '0'))
            if age_ms < 0 or age_ms > 10 * 60 * 1000:
                continue
            body = text_from_payload(msg.get('payload', {}))
            if 'Use this passcode to verify the email address' not in body:
                continue
            match = re.search(r'(?m)^\s*(\d{6})\s*$', body)
            if not match:
                continue
            for recipient in RECIPIENTS:
                send_one(item['id'], recipient, match.group(1))
        page_token = batch.get('nextPageToken')
        if not page_token:
            break


@app.get('/')
def health():
    return {'status': 'ok'}, 200


@app.post('/pubsub')
def pubsub():
    envelope = request.get_json(silent=True)
    if not isinstance(envelope, dict) or not isinstance(envelope.get('message'), dict):
        return {'error': 'invalid Pub/Sub envelope'}, 400
    try:
        encoded = envelope['message']['data']
        notice = json.loads(base64.b64decode(encoded))
        if notice.get('emailAddress', '').lower() != GMAIL_ADDRESS:
            return {'status': 'ignored'}, 200
        if not str(notice.get('historyId', '')).isdigit():
            return {'error': 'invalid history ID'}, 400
        process_mailbox()
        return {'status': 'processed'}, 200
    except Exception:
        app.logger.exception('Mailbox processing failed (no message contents logged)')
        return {'error': 'processing failed'}, 500
