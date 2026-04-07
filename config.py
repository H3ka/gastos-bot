import os
import json
from dotenv import load_dotenv
import base64

# cargar variables locales (.env)
load_dotenv()

# entorno
ENV = os.getenv("ENV", "dev")


# 🔐 TOKEN
def get_token():
    print(f"Obteniendo TOKEN para entorno: {ENV}")
    if ENV == "prod":
        token = os.getenv("TOKEN")
    else:
        token = os.getenv("TOKEN_DEV")

    if not token:
        raise Exception(f"TOKEN no definido para entorno: {ENV}")

    return token


# 🔐 GOOGLE CREDENTIALS
def get_google_credentials(scope, ServiceAccountCredentials):
    print(f"Obteniendo credenciales para entorno: {ENV}")
    if ENV == "prod":
        encoded = os.getenv("GOOGLE_CREDENTIALS_BASE64")

        if not encoded:
            raise Exception("Falta GOOGLE_CREDENTIALS_BASE64")

        decoded = base64.b64decode(encoded).decode("utf-8")
        print("DEBUG decoded:", decoded[:50])  # opcional
        credenciales_dict = json.loads(decoded)

        return ServiceAccountCredentials.from_json_keyfile_dict(
            credenciales_dict, scope
        )

    else:
        return ServiceAccountCredentials.from_json_keyfile_name(
            "credenciales.json", scope
        )