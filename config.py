import os
import base64
import json
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials

load_dotenv()


def get_token():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise Exception("❌ Falta BOT_TOKEN")
    return token


def get_sheet():
    sheet = os.getenv("SHEET_NAME")
    if not sheet:
        raise Exception("❌ Falta SHEET_NAME")
    return sheet


def get_google_credentials():
    env = os.getenv("ENV", "dev")

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]

    if env == "prod":
        encoded = os.getenv("GOOGLE_CREDS_BASE64")

        if not encoded:
            raise Exception("❌ Falta GOOGLE_CREDS_BASE64")

        decoded = base64.b64decode(encoded).decode("utf-8")
        creds_dict = json.loads(decoded)

        return ServiceAccountCredentials.from_json_keyfile_dict(
            creds_dict, scope
        )

    else:
        path = os.getenv("GOOGLE_CREDS_FILE", "credentials.json")

        if not os.path.exists(path):
            raise Exception(f"❌ No existe archivo: {path}")

        return ServiceAccountCredentials.from_json_keyfile_name(
            path, scope
        )