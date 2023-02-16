# Loc Sync Guide
Loc sync scripts live in the `Content/Python` folder in the project directory 
and are synced and updated along with the project.

It's a bunch of scripts that could be run separately but the intended way
is to launch them in batches—or task lists—via `loc-sync.py`.

These scripts can check out localization-related assets from Perforce, 
gather, export, import, and compile text in Unreal, prepare the source 
locale for translation, create debug ID and hash pseudolocalization locales, 
add and update files on Crowdin, build and download latest translations 
from Crowdin, plus do some other project-specific things. All without you having 
to open the Unreal Editor or downloading and copying any files yourself.

### Contents
- [Task Lists](#loc-sync-task-lists)
- [Typical Scenarios](#typical-scenarios)
- [Errors](#errors-and-logging)

## Usage

Navigate to the `Content` folder in your project directory, select the `Python` 
folder, then hold `shift` and `right click` to open the extended context menu, 
choose `Open in Terminal` and this will open a terminal window. 
Type `python loc-sync.py` to run the script and you'll see the task lists available 
(configured in base.config.yaml).

# Loc sync task lists
When you run the loc sync script it reads tasks, parameters 
and task lists from base.config.yaml and prints them out for you to choose.

Task lists cover the most common things you do with the project and translations. 
And you can always create your own.

By default, you have the following list and here's what each of the task lists does.

### `1: full-but-no-source-update`
By default, this runs all the tasks you've set up except for the one 
that updates the source files on Crowdin. This is to avoid leaking something 
when you just need to grab the latest translations and import them into the game. 
And maybe do some other project-specific things, like updating completion rates 
or translators in credits.

### `2: update-source`
*Warning*: this doesn't gather the latest text from the UE project, 
this only updates the source files on Crowdin with what's already exported locally. 
The idea is to use it after #1 (but you could also run it after #5 or #6). 
If you need to gather and then update, you can use #7.

### `3: add-source`
This only has one task: adding new files to Crowdin. Sort of a utility script 
to simplify adding new translation targets (which result in new files) with 
the correct settings.

### `4: full-sync`
This does all the tasks you've set up, including updating the source. 
Use this if you're certain that everything's fine and you want to update the sources.

### `5: recreate-test-language`
This resets all the debug IDs and recreates them from scratch. 
This is mainly for a case when you change the number of digits in a debug ID 
and have to recreate it. You might want to do this for some other reason, though.

### `6: local-gather-test-import`
This will gather and export the text from UE, update the debug/hash locales, 
and then import and compile the text in UE. 
Good if you only need to update debug/hash locales 
and don't want to touch Crowdin at all.

### `7: gather-and-update-source-only`
This will gather and export the text from UE, update the debug/hash locales, 
and then update the sources on Crowdin.

# Typical scenarios

## Launch a new batch of translations (update source files on Crowdin)
Make sure you sync to latest change list in Perforce/UGS, run the loc sync script 
and choose `#7: gather-and-update-source-only` if you only want to update the sources 
on Crowdin, or `#4: full-sync` if you also want to import the latest translations from 
Crowdin first.

## Import translations from Crowdin
Sync to latest in Perforce/UGS, run the loc sync script 
and choose `#1: full-but-no-source-update`. 

## Both import latest translations from Crowdin and update source files on Crowdin
It is recommended to avoid doing a full sync as your first task list 
and do it in two steps instead:
1. First, run `#1: full-but-no-source-update` anyway and make sure everything's fine 
with the imported translations
2. Then run the loc sync script again and choose one of the following ways 
to update the source on Crowdin:
    - `#2: update-source`: only do this if you're certain 
    that nothing has changed after you've done step one
    - `#7: gather-and-update-source-only`: this will regather text and 
    update source on Crowdin so it will include any changes made after you ran step one
    - `#4: full-sync`: this is a bit of an overkill and it takes longer 
    but will do the trick as well, usually you'd do this 

You could just choose #4 in the first place but this would change things on Crowdin and 
if something's wrong with the translations you've just imported, 
it's going to be harder to track the problems.

## If you want to add a new localization target to the project
Configure the `add-source-files` task in `base.config.yaml` under 
`script-parameters section` by adding the loc target you want to add to Crowdin 
to the `loc_targets` array. Leave the rest of the parameters unchanged unless you 
know what you're doing. The run `#6: local-gather-test-import` followed by 
`#3: add-source`.

## If you want to fix a typo and keep the translations
The way Unreal works with POs, fixing a typo results in all translations being dropped. 
Same happens on Crowdin, since Unreal doesn't use the PO features to avoid it. So you 
have to take care of this manually.

1. Fix the typo on Crowdin. Change both the source text and the key: because 
for POs, source is part of the key. And choose to Keep translations.
2. Fix the typo in Unreal. Make sure you have the same text in Unreal, and on Crowdin :)
3. Run the loc sync and choose `#4: full-sync`. You could only download translations
instead but then you'd lose the ability to check if it really worked, and risk finding 
out that it hasn't worked only the next time you update the source on Crowdin.
4. Check the Activity stream on Crowdin to make sure you don't have any changes in the 
lines where you fixed the typos. If all is done right, there will be none because the 
source and ket on Crowdin and in Unreal are the same even before you run the sync.
5. Open the Localization Dashboard and check that the translations for these lines 
are imported back to Unreal.


# Errors and logging
If everything goes as intended, the script will end with a list of tasks performed, 
their execution times and return codes. If all return codes are zeros (Return code: 0), 
then it all went well. Better reporting incoming :)

While it runs, the script reroutes the logs from Unreal Editor, and those usually 
contain a whole bunch of warnings and non-critical errors. Don't be afraid of that.

However, if a script crashes with an exception or if it prints that a task has failed, 
or if you see return code that isn't zero, then something's off. 
Logs are located under `Content/Python/logs`.