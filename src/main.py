import os
import yaml
import json
import logging
import io
import shutil
import datetime
import typer
from typing import Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import markdownify

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

app = typer.Typer()

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
CONFIG_FILE = 'config.yaml'
STATE_FILE = 'state.json'
TOKEN_FILE = 'token.json'
CREDENTIALS_FILE = 'credentials.json'

def load_config():
    if not os.path.exists(CONFIG_FILE):
        logging.error(f"Config file {CONFIG_FILE} not found.")
        return None
    with open(CONFIG_FILE, 'r') as f:
        return yaml.safe_load(f)

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def get_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                logging.error(f"{CREDENTIALS_FILE} not found. Please place your Google Drive API credentials in this file.")
                return None
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
    return build('drive', 'v3', credentials=creds)

def backup_file(filepath, dry_run=False):
    if os.path.exists(filepath):
        backup_path = filepath + '.bak'
        if not dry_run:
            shutil.copy2(filepath, backup_path)
        logging.info(f"Backed up {filepath} to {backup_path}" + (" (Dry Run)" if dry_run else ""))

def convert_to_markdown(service, file_id, file_name, output_dir, dry_run=False):
    try:
        if dry_run:
            # Simulate conversion
            safe_filename = "".join([c for c in file_name if c.isalpha() or c.isdigit() or c in (' ', '-', '_')]).strip()
            output_path = os.path.join(output_dir, f"{safe_filename}.md")
            logging.info(f"Would convert {file_name} to markdown at {output_path} (Dry Run)")
            return True

        # Export Google Doc as HTML
        request = service.files().export_media(fileId=file_id, mimeType='text/html')
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()

        html_content = fh.getvalue().decode('utf-8')
        md_content = markdownify.mdownify(html_content, heading_style="ATX")
        
        # Sanitize filename
        safe_filename = "".join([c for c in file_name if c.isalpha() or c.isdigit() or c in (' ', '-', '_')]).strip()
        output_path = os.path.join(output_dir, f"{safe_filename}.md")
        
        backup_file(output_path, dry_run=dry_run)
        
        with open(output_path, 'w') as f:
            f.write(md_content)
        logging.info(f"Converted {file_name} to markdown at {output_path}")
        return True
    except Exception as e:
        logging.error(f"Failed to convert {file_name}: {e}")
        return False

def resolve_path_to_id(service, path):
    if not path or path == '/':
        return 'root'
    
    parts = [p for p in path.split('/') if p]
    parent_id = 'root'
    
    for part in parts:
        query = f"name = '{part}' and '{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])
        
        if not files:
            logging.error(f"Folder '{part}' not found in path '{path}'")
            return None
        
        if len(files) > 1:
            logging.warning(f"Multiple folders named '{part}' found. Using the first one ({files[0]['id']}).")
        
        parent_id = files[0]['id']
        
    return parent_id

def scan_folder(service, folder_id, local_dir, state, dry_run=False):
    logging.info(f"Scanning folder ID: {folder_id} -> Local: {local_dir}")
    
    if not dry_run:
        os.makedirs(local_dir, exist_ok=True)
    elif not os.path.exists(local_dir):
         logging.info(f"Would create directory: {local_dir} (Dry Run)")

    try:
        # 1. Process Documents
        query_docs = f"'{folder_id}' in parents and mimeType = 'application/vnd.google-apps.document' and trashed = false"
        results_docs = service.files().list(q=query_docs, fields="nextPageToken, files(id, name, modifiedTime)").execute()
        items_docs = results_docs.get('files', [])

        for item in items_docs:
            file_id = item['id']
            file_name = item['name']
            modified_time = item['modifiedTime']
            
            # Check if changed
            last_recorded_time = state.get(file_id)
            
            if last_recorded_time != modified_time:
                logging.info(f"File {file_name} changed (new: {modified_time}, old: {last_recorded_time}). Converting...")
                if convert_to_markdown(service, file_id, file_name, local_dir, dry_run=dry_run):
                    if not dry_run:
                        state[file_id] = modified_time
                        save_state(state)
            else:
                logging.info(f"File {file_name} unchanged.")

        # 2. Process Subfolders (Recursive)
        query_folders = f"'{folder_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        results_folders = service.files().list(q=query_folders, fields="nextPageToken, files(id, name)").execute()
        items_folders = results_folders.get('files', [])
        
        for folder in items_folders:
            sub_folder_id = folder['id']
            sub_folder_name = folder['name']
            
            # Sanitize folder name for local path
            safe_folder_name = "".join([c for c in sub_folder_name if c.isalpha() or c.isdigit() or c in (' ', '-', '_')]).strip()
            sub_local_dir = os.path.join(local_dir, safe_folder_name)
            
            scan_folder(service, sub_folder_id, sub_local_dir, state, dry_run=dry_run)
            
    except Exception as e:
        logging.error(f"Error scanning folder {folder_id}: {e}")

@app.command()
def main(dry_run: bool = typer.Option(False, "--dry-run", help="Run without making changes")):
    config = load_config()
    if not config:
        return

    state = load_state()
    service = get_service()
    
    if not service:
        return

    for directory in config.get('directories', []):
        folder_id = None
        path = None
        folder_name = None
        custom_output_dir = None

        if isinstance(directory, str):
            path = directory
            folder_name = os.path.basename(path)
        elif isinstance(directory, dict):
            # Check for legacy keys: id/path/name
            if 'id' in directory or 'path' in directory:
                folder_id = directory.get('id')
                path = directory.get('path')
                folder_name = directory.get('name')
                if not folder_name and path:
                     folder_name = os.path.basename(path)
            # New format: { "Drive/Path": "/Local/Path" }
            elif len(directory) == 1:
                path, custom_output_dir = list(directory.items())[0]
                folder_name = os.path.basename(path)
        
        if not folder_id and not path:
             logging.error(f"Directory entry {directory} invalid. Skipping.")
             continue
             
        if not folder_id and path:
            logging.info(f"Resolving path: {path}")
            folder_id = resolve_path_to_id(service, path)
            if not folder_id:
                continue

        if not folder_name:
             folder_name = "Unknown"

        logging.info(f"Scanning folder: {folder_name} ({folder_id})")
        
        # Determine local output directory
        if custom_output_dir:
            local_dir = custom_output_dir
        else:
            local_dir = os.path.join(os.getcwd(), "downloads", folder_name)
        
        # Start recursive scan
        scan_folder(service, folder_id, local_dir, state, dry_run=dry_run)

if __name__ == '__main__':
    app()
