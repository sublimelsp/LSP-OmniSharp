# LSP-OmniSharp

This is a helper package that automatically installs and updates
[OmniSharp](https://github.com/OmniSharp/omnisharp-roslyn) for you.

To use this package, you must have:

- The [LSP](https://packagecontrol.io/packages/LSP) package.
- The [.NET SDK](https://dotnet.microsoft.com/download). (The "Core" version **does not work on macOS**.)

## Applicable Selectors

This language server operates on views with the `source.cs` base scope.

## Installation Location

The server is installed in the $DATA/Package Storage/LSP-OmniSharp directory, where $DATA is the base data path of Sublime Text.
For instance, $DATA is `~/.config/sublime-text` on a Linux system. If you want to force a re-installation of the server,
you can delete the entire $DATA/Cache/LSP-OmniSharp directory.

Like any helper package, installation starts when you open a view that is suitable for this language server. In this
case, that means that when you open a view with the `source.cs` base scope, installation commences.

## Configuration

Configure OmniSharp by running `Preferences: LSP-OmniSharp Settings` from the Command Palette.

## Project Setting

The server will automatically find the the solution file from the folder you have opened in Sublime. If you have multiple solutions, or your solution is in another folder, you have to specify the solution file you wish to use in a `sublime-project`. 

1. Go to `File -> Open` and select the folder with your solution in it.

2. Go to `Project -> Save Project As` and save a `YOURPROJECTNAME.sublime-project` in desired location.

3. Open your `YOURPROJECTNAME.sublime-project` file that should now appear in the sidebar on the left

4. Enter the location to the `*.sln` file like below

```
{
    "folders":
    [
        {
            "follow_symlinks": true,
            "path": "."
        }
    ],
    "solution_file": "./testconsoleprj.sln"
}
```

Once the `YOURPROJECT.sublime-project` is set up and saved, the next time you open this project in sublime, OmniSharp will use the specified solution.

## Capabilities

OmniSharp can do a lot of cool things, like

- code completion
- signature help
- hover info
- some quality code actions
- formatting
- find references
- goto def
