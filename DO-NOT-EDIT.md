# Don't edit this folder in place

In a project checkout this folder is a **git submodule**: a clone of
[xabk/ue-loc-tools](https://github.com/xabk/ue-loc-tools) pinned to one commit.
The project repo records only that commit id, never the file contents.

So an edit made here is invisible to the project repo, and the next
`git submodule update` throws it away. In a Perforce workspace it is worse: P4
has no idea this folder is a submodule, so an edited vendor file can be
submitted and will quietly fork that project's copy of the tools from upstream,
with nothing to warn you.

## Where things actually belong

| What | Where | Tracked by |
|---|---|---|
| Task code, libraries, the runner | here | this repo, shared by every project |
| `base.config.yaml`, `crowdin.config.yaml` | the folder **above** this one | the project repo (the secret one by nobody) |
| Project-specific tasks and one-offs | `../project/` | the project repo |

Start a project config from the templates rather than by copying another
project's:

```
uv run --project loctools loctools/loc-project.py           # creates both configs
uv run --project loctools loctools/loc-project.py --check   # validates them
```

`--check` is worth running before any upgrade: a config key that matches no
field is silently ignored, which is how several bugs survived for a year.

## Changing the tools themselves

Improvements are welcome — they just have to go upstream, not sideways. From
inside this folder:

```
git checkout main          # make sure you are not on a detached HEAD
<edit, then run the tests: uv run --extra test python -m pytest>
git commit -am "..."       # a real commit in ue-loc-tools
git push origin main       # or push a branch and open a PR
cd ..
git commit -am "Bump loctools"   # record the new pointer in the project repo
```

Two commits per change: one here, one in the project repo for the pointer.
Forget the second and the project stays pinned to the old commit — it shows up
as a modified `loctools` entry in `git status`.

To pull other people's improvements in:

```
git submodule update --remote --merge loctools
git commit -am "Bump loctools to <sha>"
```

If you have no GitHub access to this repo, don't work around it by editing
files here. Send the diff to whoever maintains the tools.
