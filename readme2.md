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

## Importing translations from Crowdin

Use either `!all-targets.bat` or `!all-targets-manual.bat`: both will ask you if you want to import translations, 
and if you answer `Yes`, they'll compile and download translations from Crowdin, then import and compile them in Unreal.

# Ordering Loc

1. Sync the files up to Crowdin, either automatically or manually, see above.
2. Open `All Strings` in one of the languages (say, Japanese). ![image](https://github.com/user-attachments/assets/ad8affa3-489d-4760-8007-d4b4f52e73bc)
3. Switch to Side-by-side view if the editor is in any other view. ![image](https://github.com/user-attachments/assets/8da7cd7e-b64e-4d6d-8f6c-f8671b9734b4) ![image](https://github.com/user-attachments/assets/e57452a9-5dc0-4621-bbdf-dddedd56e437)
4. Filter for Untranslated strings. ![image](https://github.com/user-attachments/assets/d957962d-a559-45cd-8168-96ea1a86fdf7)
5. Select all Untranslated strings. First, tick the checkbox to the left of the search box to select all strings on the current page. Then, if there are more than 50 strings and the banner appears, click `Select all NNN items matching the current filter` link on the banner to select all filtered strings on all pages. ![image](https://github.com/user-attachments/assets/244baad5-b3bf-493f-9f8a-52e1ab20464a)
6. Label the new strings, following the pattern: `TASK-EA-NN`, e.g., `TASK-EA-01` (which I have already created). Check the last EA batch number in `#loc-announce`. Make sure the strings are filtered and all filtered strings are selected. ![image](https://github.com/user-attachments/assets/4d383992-4646-40e5-aaba-271e0b6692cb) ![image](https://github.com/user-attachments/assets/fcbc3274-0a53-41cb-b8b8-e030acc0b22e)
7. Optional: Create tasks based on this label. Parameters: Create pending proofreading tasks, create translation cost estimates, _do not exclude_ strings that are part of other tasks, filter by the label you've created/used, select all files, and select all languages. ![image](https://github.com/user-attachments/assets/400eacc1-e731-4058-9cc9-f7e5fd0973d3) ![image](https://github.com/user-attachments/assets/b8a3fde8-0bc8-4c5a-aea5-570c5d5df9dc) ![image](https://github.com/user-attachments/assets/be29120b-2ec9-41b5-9728-c3fad28414e8) ![image](https://github.com/user-attachments/assets/60c9aaa7-3aef-4ad6-9229-8ea5ff8fccfe)
8. Optional: If Tasks have been created, run `x-tasks.py` in `Content/Python/loc-tools/` to assign the tasks to the primary team members.
9. Check the volume. If you created the tasks, there should be reports in `Reports` → `Archive`. If not, create a report under `Reports` → `Cost Estimate`, filtering by Label. Do not forget to press `Apply` when you select the filters: `Language` = one language, e.g., Japanese, to speed things up, `Strings Added` = `All Time`, `Label` = `<Your label>`. Use the `Volume Estimate` template, which will set the rates to one and zeros. ![image](https://github.com/user-attachments/assets/bb8891e5-506d-4713-b382-926053fe2cba) ![image](https://github.com/user-attachments/assets/6a2d46be-6c08-4ce1-9596-57682c0ed579) ![image](https://github.com/user-attachments/assets/c3af38ad-a694-44b4-897c-593a834b0e0d)
10. Check the volume. Wait until the reports finishes and open it, either from the notification at the bottom or from `Reports` → `Archive`. What you want is `Translation` and `TM Savings` numbers under `Subtotal`. It's in USD, but since we set the rate to 1, these are also the word counts. `Translation` is `new words`, `TM Savings` is `repetitions and 100% TM matches`.  You can also check out the volume per file in the table below if you're interested. ![image](https://github.com/user-attachments/assets/69d91843-3713-494c-80a5-ade378fb12d8)
11. Post the task in `#loc-announce`. Specify a nice title, some intro/task description, scope (label and tasks, if created), volume, deadline, and any additional comments. Use any of the older in-game batches as a template, also included below. ![image](https://github.com/user-attachments/assets/76b76a6e-266e-4fc1-801f-96b5b60c4aeb)

### Task template for EA
```
**Batch EA-01: First update in Early Access**

Hey! There's a new batch, it's for the first update in Early Access.

**Scope**: It's all the new text in the project, in all files. Also marked with `TASK-EA-01`. And I've created and assigned the tasks if you prefer those.

**Crowdin word counts**: It's `NNN` new words and `NNN` words in repetitions and TM matches.

**Deadline**: It'd be great to have this by `noon CEST, June, 13th`.

...Any additional comments...
```
