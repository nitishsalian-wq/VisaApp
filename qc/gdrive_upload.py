"""
Google Drive Integration Module
Uploads visa application documents to a shared Google Drive folder
using a Service Account. Organizes files in YYYY-MM-DD_Applicant_Name subfolders.

Setup:
1. Create a Google Cloud project and enable the Google Drive API
2. Create a Service Account and download the JSON key file
3. Place the key file as 'service_account.json' in this directory (or set GDRIVE_SERVICE_ACCOUNT_FILE env var)
4. Share the 'VISA APPLICATIONS' folder in Google Drive with the service account email
   (found in the JSON key file as 'client_email')
"""

import os
import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Configuration
SERVICE_ACCOUNT_FILE = os.environ.get(
    'GDRIVE_SERVICE_ACCOUNT_FILE',
    os.path.join(os.path.dirname(__file__), 'service_account.json')
)
ROOT_FOLDER_NAME = os.environ.get('GDRIVE_ROOT_FOLDER', 'VISA APPLICATIONS')
ROOT_FOLDER_ID = os.environ.get('GDRIVE_ROOT_FOLDER_ID', '')  # Set this if you know the folder ID

SCOPES = ['https://www.googleapis.com/auth/drive.file']


def _get_drive_service():
    """Create and return an authenticated Google Drive service instance."""
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        if not os.path.exists(SERVICE_ACCOUNT_FILE):
            logger.warning(
                f"Service account file not found at {SERVICE_ACCOUNT_FILE}. "
                "Google Drive upload is disabled. "
                "See gdrive_upload.py header for setup instructions."
            )
            return None

        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        service = build('drive', 'v3', credentials=credentials)
        return service

    except ImportError:
        logger.warning(
            "Google API libraries not installed. Run: "
            "pip install google-auth google-auth-oauthlib google-api-python-client"
        )
        return None
    except Exception as e:
        logger.error(f"Failed to initialize Google Drive service: {e}")
        return None


def _find_or_create_folder(service, folder_name, parent_id=None):
    """Find a folder by name under a parent, or create it if it doesn't exist."""
    query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    if parent_id:
        query += f" and '{parent_id}' in parents"

    results = service.files().list(
        q=query,
        spaces='drive',
        fields='files(id, name)',
        pageSize=1
    ).execute()

    files = results.get('files', [])
    if files:
        return files[0]['id']

    # Create the folder
    file_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder'
    }
    if parent_id:
        file_metadata['parents'] = [parent_id]

    folder = service.files().create(
        body=file_metadata,
        fields='id'
    ).execute()

    logger.info(f"Created Google Drive folder: {folder_name} (ID: {folder.get('id')})")
    return folder.get('id')


def _get_root_folder_id(service):
    """Get or find the root 'VISA APPLICATIONS' folder ID."""
    if ROOT_FOLDER_ID:
        return ROOT_FOLDER_ID

    # Search for the shared folder by name
    query = (
        f"name = '{ROOT_FOLDER_NAME}' and "
        f"mimeType = 'application/vnd.google-apps.folder' and "
        f"trashed = false"
    )
    results = service.files().list(
        q=query,
        spaces='drive',
        fields='files(id, name)',
        pageSize=5
    ).execute()

    files = results.get('files', [])
    if files:
        return files[0]['id']

    # Create it if not found
    return _find_or_create_folder(service, ROOT_FOLDER_NAME)


def _sanitize_folder_name(name):
    """Create a safe folder name from applicant name."""
    if not name:
        name = 'Unknown_Applicant'
    # Remove special characters, keep alphanumeric, spaces, hyphens
    name = re.sub(r'[^\w\s\-]', '', name)
    # Replace spaces with underscores
    name = re.sub(r'\s+', '_', name.strip())
    return name


def _upload_file(service, file_path, folder_id, filename=None):
    """Upload a single file to a Google Drive folder."""
    from googleapiclient.http import MediaFileUpload

    if not filename:
        filename = os.path.basename(file_path)

    file_metadata = {
        'name': filename,
        'parents': [folder_id]
    }

    media = MediaFileUpload(
        file_path,
        mimetype='application/pdf',
        resumable=True
    )

    uploaded = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, name, webViewLink'
    ).execute()

    return {
        'id': uploaded.get('id'),
        'name': uploaded.get('name'),
        'link': uploaded.get('webViewLink', '')
    }


def upload_documents(applicant_name, file_paths_with_names):
    """
    Upload all documents for a visa application to Google Drive.

    Args:
        applicant_name: Name of the applicant (used for subfolder name)
        file_paths_with_names: List of tuples (file_path, display_name)
            e.g. [('/tmp/uploads/abc/visa.pdf', 'Visa Application - John.pdf'),
                   ('/tmp/uploads/abc/passport.pdf', 'Passport Copy - John.pdf')]

    Returns:
        dict with:
            'success': bool
            'folder_link': str (Google Drive link to the subfolder)
            'uploaded_files': list of dicts with file details
            'error': str (if success is False)
    """
    result = {
        'success': False,
        'folder_link': '',
        'uploaded_files': [],
        'error': ''
    }

    service = _get_drive_service()
    if not service:
        result['error'] = 'Google Drive not configured. Documents saved locally only.'
        return result

    try:
        # Get root folder
        root_id = _get_root_folder_id(service)

        # Create date + applicant subfolder: "31-03-26_John_Doe"
        date_prefix = datetime.now().strftime('%d-%m-%y')
        safe_name = _sanitize_folder_name(applicant_name)
        subfolder_name = f"{date_prefix}_{safe_name}"

        subfolder_id = _find_or_create_folder(service, subfolder_name, root_id)

        # Get the subfolder link
        subfolder_meta = service.files().get(
            fileId=subfolder_id,
            fields='webViewLink'
        ).execute()
        result['folder_link'] = subfolder_meta.get('webViewLink', '')

        # Upload each file
        for file_path, display_name in file_paths_with_names:
            if os.path.exists(file_path):
                try:
                    uploaded = _upload_file(service, file_path, subfolder_id, display_name)
                    result['uploaded_files'].append(uploaded)
                    logger.info(f"Uploaded to Drive: {display_name}")
                except Exception as e:
                    logger.error(f"Failed to upload {display_name}: {e}")
                    result['uploaded_files'].append({
                        'name': display_name,
                        'error': str(e)
                    })

        result['success'] = True
        logger.info(
            f"Uploaded {len(result['uploaded_files'])} files to "
            f"Google Drive: {subfolder_name}"
        )

    except Exception as e:
        logger.error(f"Google Drive upload failed: {e}")
        result['error'] = f"Drive upload error: {str(e)}"

    return result


def is_gdrive_configured():
    """Check if Google Drive integration is properly configured."""
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        return False
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        return True
    except ImportError:
        return False
