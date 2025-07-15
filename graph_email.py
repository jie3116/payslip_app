import os
import requests
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
TENANT_ID = os.getenv('TENANT_ID')
EMAIL_USER = os.getenv('EMAIL_USER')


def get_token():
    url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    headers = { 'Content-Type': 'application/x-www-form-urlencoded' }
    data = {
        'grant_type': 'client_credentials',
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'scope': 'https://graph.microsoft.com/.default'
    }

    resp = requests.post(url, headers=headers, data=data)
    resp.raise_for_status()
    return resp.json()['access_token']


def send_graph_email(to_email, subject, body, attachment_path=None):
    token = get_token()
    url = 'https://graph.microsoft.com/v1.0/users/' + EMAIL_USER + '/sendMail'

    with open(attachment_path, 'rb') as f:
        file_bytes = f.read()

    filename = os.path.basename(attachment_path)
    encoded_file = file_bytes.decode('latin1')  # for Graph API you might need to base64 encode

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
                    "name": filename,
                    "contentBytes": file_bytes.encode("base64").decode()
                }
            ] if attachment_path else []
        },
        "saveToSentItems": "true"
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    response = requests.post(url, json=message, headers=headers)
    response.raise_for_status()
    print(f"✅ Email berhasil dikirim ke {to_email}")
