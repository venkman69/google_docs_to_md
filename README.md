# Overview
This is a vibe-coded app to keep google docs exported into markdown format.

The app converts Google Docs to markdown and PDF files, and uploads them back to the same folder in Google Drive. Local files are only created as a fallback if the upload fails.

# Installation
1. Clone the repo
2. Install the dependencies
```bash
uv venv
uv sync
```
3. Setup Google OAuth credentials:
   1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
   2. Create a new project or select an existing one
   3. Enable the Google Drive API:
      - Navigate to "APIs & Services" > "Library"
      - Search for "Google Drive API" and enable it
   4. Create OAuth credentials:
      - Go to "APIs & Services" > "Credentials"
      - Click "Create Credentials" > "OAuth client ID"
      - Application type: "Desktop app"
      - Give it a name and click "Create"
   5. Download the credentials:
      - Click the download icon next to your OAuth client ID
      - Rename the file to `credentials.json`
      - Place it in the root directory of this project
   6. First run will open a browser window for authentication:
      - Run the app: `./bin/run.sh`
      - Complete the OAuth flow in the browser
      - A `token.json` file will be created automatically
   7. **Note:** If you update from an older version, delete `token.json` and re-authenticate to grant the new permissions required for uploading files
5. Setup `config.yaml`, this contains a mapping of the google drive directories to local Google Drive directories - simpler to write there than to process file upload etc.
```yaml
directories:
  - "Personal/Resume": '/mnt/g/My Drive/Personal/Resume'
```
6. Run the app: `./bin/run.sh`
  * '--dry-run' to simply print actions without actually performing them
