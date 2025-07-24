# graph_email.py
import os
import requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv('GRAPH_CLIENT_ID')
TENANT_ID = os.getenv('GRAPH_TENANT_ID')
CLIENT_SECRET = os.getenv('GRAPH_CLIENT_SECRET')
EMAIL_ADDRESS = os.getenv('EMAIL_USER')  # Email pengirim

def get_token():
    url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    data = {
        'grant_type': 'client_credentials',
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'scope': 'https://graph.microsoft.com/.default'
    }

    response = requests.post(url, headers=headers, data=data)
    response.raise_for_status()
    return response.json()['access_token']

def send_graph_email(to_email, subject, body, pdf_path):
    token = get_token()

    with open(pdf_path, 'rb') as f:
        pdf_bytes = f.read()

    message = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": "Text",
                "content": body
            },
            "toRecipients": [
                {"emailAddress": {"address": to_email}}
            ],
            "attachments": [
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": os.path.basename(pdf_path),
                    "contentBytes": pdf_bytes.decode('latin1')
                }
            ]
        },
        "saveToSentItems": "true"
    }

    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }

    url = f"https://graph.microsoft.com/v1.0/users/{EMAIL_ADDRESS}/sendMail"

    response = requests.post(url, headers=headers, json=message)
    if response.status_code == 202:
        print(f"✅ Email Graph API terkirim ke {to_email}")
    else:
        print(f"❌ Gagal kirim Graph API ke {to_email}: {response.status_code} - {response.text}")
