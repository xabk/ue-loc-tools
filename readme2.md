# Installation

Scripts and config files come with the repo under `Content/Python/loc-tools`.

You'll only have to install the two requirements: `uv` and `Crowdin CLI`.

## Requirements

### uv

"An extremely fast Python package and project manager, written in Rust", as they put it.

You can install it with `winget install --id=astral-sh.uv  -e`.

See https://docs.astral.sh/uv/getting-started/installation/ for other options.

### Crowdin CLI

A Crowdin CLI application to simplify routine operations: https://github.com/crowdin/crowdin-cli.

You can download and install it using this link: https://github.com/crowdin/crowdin-cli/releases/latest/download/crowdin.exe

>[!IMPORTANT]
>
> Choose `Yes` when the installer asks you if you want to update the Java version, or it won't continue:
> 
> ![image](https://github.com/user-attachments/assets/08b82d18-3d3e-4369-a42d-dd4a255a9e62)
>
> Do not install Java from the page that is opened automatically: it's an older version, which isn't enough for this.
>
> Instead, download and install the latest version from https://www.oracle.com/java/technologies/downloads/?er=221886#jdk24-windows.

See other installation options: https://crowdin.github.io/crowdin-cli/installation#windows

# Usage

`uv run loc-sync.py` or `!loc-sync.bat` will launch the script and present you with the list of tasks.

It also accepts task names as command-line parameters for automation, for example, `uv run loc-sync.py "[X, ALL] #5 Import Translations"`.

Note that _uv_ should take care of everything automatically, from Python to all the required packages.

## Updating the files on Crowdin: automatic vs manual

There are two ways of updating the files on Crowdin.

One is automatic, where a script just updates all the files for you and drops any translations for existing strings if the source has changed, even if it was just a minor typo fix. 
This is the default method, since it's faster and easier.

The other is manual, where the script preps the files for you and opens the folder with the files, and then you have to update them manually one by one. 
This gives you a chance to see the diffs for each file and preserve some translations. 
This is a nice option if you know you've been fixing a lot of minor typos in the repo but not on Crowdin, and you don't want to lose translations because of that.

### Updating the files automatically

`!all-targets.bat` will ask you if you want to import translations and if you want to update the files. 
If you say `Yes` to updating the files, it will update them automatically.

### Updating the files manually

Use `!all-targets-manual.bat`. When the script pauses and tells you to update the files:

1. Open the Files section on Crowdin: https://csp.crowdin.com/u/projects/87/files.
2. Open the folder with the files to upload: `Content/Localization/~Temp/#Sources/CSVs/`. The script should open it for you.
3. Hint: Open Perforce and see which files in `Content/Localization/~Temp/#Sources/CSVs/` have been modified: you can upload only these files to Crowdin. <details><summary>Perforce screenshot</summary>![image](https://github.com/user-attachments/assets/e3589b6c-0719-4f46-a135-44518386132a)</details>
4. Drag and drop the files, one by one, to their respective folders on Crowdin:
   - Keep translations for minor typo fixes only. <details><summary>Crowdin typo screenshot</summary>...Couldn't find an example during the last update...</details>
   - _Do not keep translations_ for meaningful changes, changes in variables, and even formatting changes that need to be reflected in translation, which includes adding or removing full stops, adding or removing spacing, etc. <details><summary>Crowdin drop translations screenshot</summary>[!image](https://github.com/user-attachments/assets/8b9c3100-6a11-4ce5-90fa-f350162d60e1)</details>
5. In Perforce, revert unchanged files and submit the `#Sources` folder to keep track of what we upload to Crowdin. That enables the hint under #3 to save time.

### Reverting the files

If something goes wrong during the update, e.g., if you spot a lot of dropped/added strings when there shouldn't be as many, or the text looks odd, you can always revert the file on Crowdin.

![image](https://github.com/user-attachments/assets/87ee8fd9-5053-4948-9239-d5fbc26b599c)

### Importing translations from Crowdin

Use either `!all-targets.bat` or `!all-targets-manual.bat`: both will ask you if you want to import translations, 
and if you answer `Yes`, they'll compile and download translations from Crowdin, then import and compile them in Unreal.
