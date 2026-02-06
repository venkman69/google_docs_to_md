# Overview
This is a vibe-coded app to keep google docs exported into markdown format.

# Installation
1. Clone the repo
2. Install the dependencies
```bash
uv venv
uv sync
```
3. Setup `config.yaml`, this contains a mapping of the google drive directories to local Google Drive directories - simpler to write there than to process file upload etc.
```yaml
directories:
  - "Personal/Resume": '/mnt/g/My Drive/Personal/Resume'
```
3. Run the app: `./bin/run.sh`
  * '--dry-run' to simply print actions without actually performing them
