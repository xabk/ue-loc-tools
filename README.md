# ueloctools library
## Localization tools for Unreal, plus UE and Crowdin API integration

This pack of scripts aims to help with automating gather/export/import/compile and sync process for Unreal and Crowdin. On top of that, it adds a bunch of improvements and convenience features: it sorts and annotates the source files to help translators, creates a debug ID and 'hash' pseudolocalized locales, and lets you manipulate localization targets to avoid tedious manual tasks in Loc Dashboard (e.g., adding or deleting one or more languages to one or more targets and copying languages from one target to another).

## Requirements

### uv

"An extremely fast Python package and project manager, written in Rust", as they put it.

`update-loc-tools.bat` installs it if it is missing, so you normally do not
need to do this by hand. If you want to: `winget install --id=astral-sh.uv -e`.

uv also takes care of Python itself and every package, so there is nothing
else to install.

See https://docs.astral.sh/uv/getting-started/installation/ for other options.

### Crowdin CLI

Used to upload source files to Crowdin.

`update-loc-tools.bat` installs the version these tools are tested against, so
you normally do not need to do this by hand either. That version is pinned as
`crowdin_cli_version` in `pyproject.toml`, and `loc-project.py --check` warns
when the installed CLI differs from the pin.

Upgrading it is a deliberate change: bump the pin, then re-run the tests and
the upload paths in particular.

To install a specific version by hand:

```
winget install --id Crowdin.CrowdinCLI -e --version <pinned version>
```

> [!NOTE]
>
> Version 5 and later is a single portable executable and does **not** need
> Java. The 4.x releases were Java-based, so any instructions you find about
> installing a JDK or letting the installer update Java apply only to those.

Note that winget only publishes stable releases, so a preview version has to be
installed by hand.

See other installation options: https://crowdin.github.io/crowdin-cli/installation#windows

## Setting up a new project

These tools are meant to live in a `loctools` subfolder of the project that uses
them: the project owns the configs and any project-specific scripts, and this
repo stays generic.

1. Create the project repo, then add these tools as a submodule:

   ```
   git submodule add -b main <this repo> loctools
   ```

   The `-b main` matters: without a branch recorded in `.gitmodules`,
   `git submodule update --remote` has nothing to follow.

2. Scaffold the project files:

   ```
   uv run --project loctools loctools/loc-project.py
   ```

   That writes `base.config.yaml`, `crowdin.config.yaml`, `!loc-sync.bat`,
   `update-loc-tools.bat`, `.gitignore` and `sync-guide.md`. It refuses to
   overwrite anything that already exists, so it is safe to re-run.

3. Fill in the Crowdin token and project ID in `crowdin.config.yaml`.

4. Edit `base.config.yaml`: loc targets and locales, `project_dir` and
   `engine_dir`, and `unreal_binary` if the project runs UE5 or renames its
   editor target. Set `file_format` under `update-source-files` if the
   project's existing Crowdin files are not plain gettext.

5. For Perforce, paste `loctools/templates/p4ignore-snippet.txt` into the
   `p4ignore.txt` at your **workspace root**. Step 2 cannot do this for you:
   that file lives outside the project.

6. Put any project-specific scripts in `project/` and register them under
   `tasks:` with a `file:` key. That folder is intentionally empty here.

7. Run `update-loc-tools.bat`. It installs the dependencies and verifies the
   config, the machine and the tools before you commit anything.

8. Commit to git. For Perforce, reconcile and submit.

## Upgrading a project to a newer version of the tools

1. Pull the new version:

   ```
   git submodule update --remote --merge loctools
   ```

   `update-loc-tools.bat` does exactly this as its second step, so running the
   script is usually enough.

2. See what the templates changed:

   ```
   uv run --project loctools loctools/loc-project.py --upgrade
   ```

   This reports every config key where your project and the template now
   differ, and modifies nothing: a config is judgment, not data. Apply what
   you want by hand.

   It compares keys rather than files, so it will not tell you that a new
   template file appeared. On a version bump, glance at `loctools/templates/`
   for anything new.

3. Run `update-loc-tools.bat` to re-sync the dependencies and re-run the
   checks.

4. Commit the new submodule pointer:

   ```
   git commit -am "Bump loctools"
   ```

A Perforce-only copy has no `.git`, so the script detects that, skips the
update and just verifies. Sync in Perforce to update those.

## Checking a project

`loc-project.py` has a mode for each question:

| command | what it answers |
| --- | --- |
| no flags | scaffold a new project from the templates |
| `--check` | is the config valid? |
| `--check-env` | does this machine have what the project needs? |
| `--upgrade` | how do my config and the template differ? |
| `--ensure-crowdin` | install the pinned Crowdin CLI if it is missing |

`--check` validates the config on its own, so it does not depend on the machine
it runs on. `--check-env` covers the machine: the Unreal editor binary, which is
an error because gather, export, import and compile all run through it, and the
Perforce settings the editor writes on first connect, which is only a warning.
Both only check what the task lists in your config actually use.

> [!IMPORTANT]
>
> The editor binary is usually not in source control, so a fresh machine has
> none until someone builds it. No script can install it for you.

## Installation and usage
1. Set the project up or upgrade it as described above. `update-loc-tools.bat`
installs the requirements and verifies the result.
2. Configure the scripts for your project: paths, targets, Crowdin credentials, script parameters,
and task lists based on what you need.
3. `!loc-sync.bat`, or `uv run --project loctools loctools/loc-sync.py`, will launch the script and present you with the list of tasks.
It also accepts a task list name as a command-line parameter for automation, for example `!loc-sync.bat "[X, ALL] #5 Import Translations"`.
Note that _uv_ takes care of everything automatically, from Python itself to all the required packages.
Add `-u` to run unattended, without the confirmation prompt: `!loc-sync.bat "<task list name>" -u`.

Other useful flags: `--list-tasks` prints the individual tasks and their
descriptions, and `--debug` turns on verbose logging. Logs go to
`logs/locsync.log` next to your config.

## Configuration
By default, `base.config.yaml` contains several task lists tailored for different scenarios. Take a look at them and adjust to your needs.

Actual workflow depends on what features you want for the project, but the basics are as follows:
1. Check out related assets from Perforce using the Unreal Editor source control settings. You have to set up source control in the editor for this to work; `loc-project.py --check-env` warns you when those settings are missing.
2. Gather and export localization data from Unreal as PO files.
3. Prepare the debug ID and source locale: lines sorted by asset paths to group things together, with additional comments and cleaned up context info, with asset names and repetition markers for convenience. Source locale is based on the debug ID locale that contains unique and simple to remember IDs like #1234 that allow you to identify any string you see in the game (default locale: io). Optionally, prepare the 'hash' locale: basic pseudolocalization locale where the script adds beginning and end markers to all strings (default locale: ia-001).
--- Possible game-specific scripts would go here ---
4. Update source files on Crowdin using source locale files generated on step 3. This requires you to configure the integration: provide API token, project ID, and organization name (empty if you're using crowdin.com).
5. Build the project on Crowdin, download latest translations, and copy them to the relevant Unreal project folders. This requires you to configure the integration: provide API token, project ID, and organization name (empty if you're using crowdin.com).
6. Import translations from PO files copied over on step 5 and compile translations in Unreal.

Game-specific scripts:
- Pull language completion rates from Crowdin and save them to a CSV for language selection menu. This requires you to adapt to the format we use or update the script.
- Pull translation stats, compile a list of top contributors per language, and save this data to a CSV for game credits. This requires you to adapt to the format we use or update the script.
- Reimport the relevant data tables from the CSVs generated in the above two steps. This requires you to adapt to the format we use or update the script.

You can adjust all the script parameters in `base.config.yaml`: set the defaults in `script-parameters/[script name]` sections and adjust them in task lists if you want under `[task list name]/[corresponding script entry]/script-parameters` section.

The tasks a project can put in a task list, by the name you use under
`script:`:

| task | what it does |
| --- | --- |
| `p4-checkout` | check out the localization files and any extra assets from Perforce |
| `ue-loc-gather-cmd` | gather, export, import and compile text in Unreal via the editor command line |
| `test-lang` | generate the source/debug-ID locale with sorting and automated comments, plus the hash pseudo-locale |
| `mt-pseudo` | create the "longest" locale from TM and MT, where English is extended to the length of the longest translation |
| `update-source-files` | add or update source files on Crowdin, with the export settings and file type you configure |
| `build-and-download` | build on Crowdin, download the translations and move them into the UE Localization folders |
| `completion-rates` | pull language completion rates into a CSV, for a language selection menu |
| `community-credits` | pull contributor stats into a CSV, for game credits |
| `po-csv-converter` | convert between the PO files and CSV, including bilingual CSVs |
| `import-screens` | upload screenshots to Crowdin, optionally pulling them from Google Drive |

Two more run as standalone scripts rather than tasks, and are configured in the
same file for convenience:

| script | what it does |
| --- | --- |
| `targets.py` | add or delete locales across loc targets, and copy locales from one target to others |
| `scripts/ue-reimport-assets.py` | reimport assets, for example data tables from the CSVs above |

The last two are why `script-parameters` may contain `targets` and
`ue-reimport-assets` sections that match no registered task.
