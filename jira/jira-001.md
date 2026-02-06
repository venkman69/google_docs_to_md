1. Create a new project and initialize it using `uv`
2. Setup a python script that reads a yaml file containing a list of directories in Google Drive to scan for documents.
3. It should keep track of the time of change for each document and if the document has changed since last recorded time, then it should perform a conversion of that document to markdown and save it to the same folder as an additional document.
4. The script should backup the old markdown artifact, if it exists, with an extension of `.bak`.


# Task 2:
1. add a dry run flag to the script (use typer).
2. move the script to a `src` folder.
3. Create a bin folder and create a shell script to run main.py
4. Update the main.py to place the output markdown files into the folder on the 'value' side of the config.yaml, for example, in the below block the output folder will be '/mnt/g/My Drive/Personal/Resume'.
```yaml
directories:
  - "Personal/Resume": '/mnt/g/My Drive/Personal/Resume'
```
5. main.py should also recurse into folder below the specified folder in the config.yaml.