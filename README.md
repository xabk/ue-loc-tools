# ueloctools library
## Localization tools for Unreal, plus UE and Crowdin API integration

This pack of scripts aims to help with automating gather/export/import/compile and sync process for Unreal and Crowdin. On top of that, it adds a bunch of improvements and convenience features: it sorts and annotates the source files to help translators, creates a debug ID and 'hash' pseudolocalized locales, and lets you manipulate localization targets to avoid tedious manual tasks in Loc Dashboard (e.g., adding or deleting one or more languages to one or more targets and copying languages from one target to another).

Installation:
1. Run `#create-venv-for-loc-sync.bat` to create a virtual environment 
and install the dependencies.
2. Configure the scripts for your project: targets, Crowdin credentials, script parameters, 
and task lists based on what you need.
3. Run `!loc-sync.bat` to launch the loc tools and follow the instructions.

You can also run the script in automated mode with `python locsync.py task-list-name -u`.

By default, `base.config.yaml` contains several task lists tailored for different scenarios. Take a look at them and adjust to your needs.

Actual workflow depends on what features you want for the project, but the basics are as follows:
1. Check out related assets from Perforce using the Unreal Editor source control settings. You have to set up source control in the editor for this to work.
2. Gather and export localization data from Unreal as PO files.
3. Prepare the debug ID and source locale: lines sorted by asset paths to group things together, with additional comments and cleaned up context info, with asset names and repetition markers for convenience. Source locale is based on the debug ID locale that contains unique and simple to remember IDs like #1234 that allow you to identify any string you see in the game (default locale: io). Optionally, prepare the 'hash' locale: basic pseudolocalization locale where the script adds beginning and end markers to all strings (default locale: ia-001).
--- Possible game-specific scipts would go here ---
4. Update source files on Crowdin using source locale files generated on step 3. This requires you to configure the integration: provide API token, project ID, and organization name (empty if you're using crowdin.com).
5. Build the project on Crowdin, download latest translations, and copy them to the relevant Unreal project folders. This requires you to configure the integration: provide API token, project ID, and organization name (empty if you're using crowdin.com).
6. Import translations from PO files copied over on step 5 and compile translations in Unreal.

Game-specific scripts:
- Pull language completion rates from Crowdin and save them to a CSV for language selection menu. This requires you to adapt to the format we use or update the script.
- Pull translation stats, compile a list of top contributors per language, and save this data to a CSV for game credits. This requires you to adapt to the format we use or update the script.
- Reimport the relevant data tables from the CSVs generated in the above two steps. This requires you to adapt to the format we use or update the script.

You can adjust all the script parameters in `base.config.yaml`: set the defaults in `script-parameters/[script name]` sections and adjust them in task lists if you want under `[task list name]/[corresponding script entry]/script-parameters` section.

List of available scripts and parameters (coming later):

- Unreal Localization Targets: add/delete cultures for loc targets, copy cultures from one target to other targets.
- Check out the assets you're about to update from Perforce
- Gather, export, import, compile text in Unreal using the UE command line executable
- Generate source/debug ID locale with automated comments and sorting, generate 'hash' locale
- Add source files to Crowdin project using predefined export settings
- Update existing source files in Crowdin project
- Build, download, extract, and move translated files from Crowdin to UE Localization directory
- Generate user contribution reports on Crowdin and save the data to CSV (to reimport the data table)
- Generate translation status reports on Crowidn and save the data to CSV (to reimport the data table)
- Reimport assets (e.g., data tables from CSVs)
- Create "longest" locale with start and end markers, based on TM and MT, where English text is extended to match the length of the longest translation
