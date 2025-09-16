import os
import io
import json
from datetime import datetime
from flask import Flask, request, jsonify, redirect, url_for, session
from dotenv import load_dotenv
import matplotlib
matplotlib.use("Agg")  # Use non-GUI backend before importing pyplot
import matplotlib.pyplot as plt

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

from googleapiclient.http import MediaFileUpload



# Load env variables
load_dotenv()

CLIENT_SECRET_FILE = os.environ.get("CLIENT_SECRET_FILE", "credentials.json")
TOKEN_FILE = os.environ.get("TOKEN_FILE", "token.json")
DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID")
MAKE_PUBLIC = os.environ.get("MAKE_PUBLIC", "false").lower() == "true"
PORT = int(os.environ.get("PORT", 8080))

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

app = Flask(__name__)
app.secret_key = "super_secret_key"  # replace or move to .env if you want


# ---------------- OAuth Helpers ----------------
def get_drive_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            creds = flow.run_local_server(port=8090, redirect_uri_trailing_slash=True)


        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    return build("drive", "v3", credentials=creds)


# ---------------- Drive Upload ----------------
def upload_to_drive(file_path, name, folder_id=DRIVE_FOLDER_ID):
    service = get_drive_service()

    file_metadata = {"name": name}
    if folder_id:
        file_metadata["parents"] = [folder_id]

    media = MediaFileUpload(file_path, mimetype="image/png", resumable=True)
    uploaded = service.files().create(
        body=file_metadata, media_body=media, fields="id, webViewLink"
    ).execute()

    if MAKE_PUBLIC:
        service.permissions().create(
            fileId=uploaded["id"], body={"role": "reader", "type": "anyone"}
        ).execute()

    return uploaded


# ---------------- Chart Generator ----------------
def plot_chart(chart_json):
    chart_type = chart_json.get("chart_type", "bar_chart")
    data = chart_json.get("data", {})

    x_vals = [v["x_axis_value"] for v in data.values()]
    y_vals = [v["y_axis_value"] for v in data.values()]

    plt.figure(figsize=(8, 6))

    if chart_type == "bar_chart":
        plt.bar(x_vals, y_vals)
    elif chart_type == "line_chart":
        plt.plot(x_vals, y_vals, marker="o")
    elif chart_type == "pie_chart":
        plt.pie(y_vals, labels=x_vals, autopct="%1.1f%%")
    else:
        raise ValueError(f"Unsupported chart type: {chart_type}")

    plt.title(chart_json.get("label", "Chart"))
    plt.xlabel(chart_json.get("x_axis_label", "X-axis"))
    plt.ylabel(chart_json.get("y_axis_label", "Y-axis"))

    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    file_name = f"chart_{timestamp}.png"
    file_path = os.path.join("charts", file_name)
    os.makedirs("charts", exist_ok=True)

    plt.savefig(file_path, format="png")
    plt.close()

    return file_path


# ---------------- Flask Routes ----------------
@app.route("/")
def index():
    return jsonify({"message": "Chart Generator API is running"})


@app.route("/generate", methods=["POST"])
def generate_chart():
    try:
        chart_json = request.json
        if not chart_json:
            return jsonify({"error": "No JSON provided"}), 400

        img_file = plot_chart(chart_json)

        upload_result = upload_to_drive(
            img_file, name=os.path.basename(img_file), folder_id=DRIVE_FOLDER_ID
        )

        return jsonify(
            {
                "file_id": upload_result["id"],
                "webViewLink": upload_result["webViewLink"],
            }
        )

    except Exception as e:
        app.logger.error("Error generating chart", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ---------------- Run ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
