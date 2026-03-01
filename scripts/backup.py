import os
import os.path
import io
import json
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/drive.file']

CREDENTIALS_DIR = Path(".credentials")
CLIENT_SECRET_FILE = CREDENTIALS_DIR / "client_secret.json"
TOKEN_FILE = CREDENTIALS_DIR / "token.json"

def get_service():
    """Builds and returns a Google Drive API service object."""
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CLIENT_SECRET_FILE.exists():
                print(f"❌ Error: {CLIENT_SECRET_FILE} not found.")
                print("Please place your client_secret.json in the .credentials/ folder.")
                return None
            
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRET_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save the credentials for the next run
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())

    return build('drive', 'v3', credentials=creds)

def upload_file(file_path, folder_id=None):
    """
    Uploads a file to Google Drive using the resumable upload method.
    """
    service = get_service()
    if not service:
        return None

    file_path = Path(file_path)
    if not file_path.exists():
        print(f"❌ Error: Local file {file_path} not found.")
        return None

    file_metadata = {'name': file_path.name}
    if folder_id:
        file_metadata['parents'] = [folder_id]

    # Use MediaFileUpload with resumable=True for efficiency
    media = MediaFileUpload(str(file_path),
                            mimetype='application/octet-stream',
                            resumable=True)

    try:
        print(f"🚀 Initiating resumable upload for: {file_path.name}...")
        request = service.files().create(body=file_metadata,
                                        media_body=media,
                                        fields='id')
        
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"📤 Uploaded {int(status.progress() * 100)}%.")
        
        print(f"✅ Upload Complete! File ID: {response.get('id')}")
        return response.get('id')

    except HttpError as error:
        print(f"❌ An error occurred: {error}")
        return None

if __name__ == '__main__':
    # Placeholder for usage
    import sys
    if len(sys.argv) > 1:
        upload_file(sys.argv[1])
    else:
        print("Usage: python drive_backup.py <file_path>")
