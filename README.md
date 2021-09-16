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

## Capabilities

OmniSharp can do a lot of cool things, like

- code completion
- signature help
- hover info
- some quality code actions
- formatting
- find references
- goto def
