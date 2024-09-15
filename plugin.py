from __future__ import annotations

import os
import shutil
import sublime

from pathlib import Path

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from typing import Any, Callable, Optional

from urllib.request import urlretrieve
from zipfile import ZipFile

from LSP.plugin import AbstractPlugin
from LSP.plugin import ClientConfig
from LSP.plugin import register_plugin
from LSP.plugin import unregister_plugin
from LSP.plugin import WorkspaceFolder
from LSP.plugin.core.views import range_to_region  # TODO: not public API :(

VERSION = "1.39.12"
URL = "https://github.com/OmniSharp/omnisharp-roslyn/releases/download/v{}/omnisharp-{}.zip"  # noqa: E501


def _platform_str() -> str:
    return {
        "osx": {
            "arm64": "osx-arm64-net6.0",
            "x64": "osx-x64-net6.0",
            "x32": "osx",
        },
        "linux": {
            "arm64": "linux-arm64-net6.0",
            "x64": "linux-x64-net6.0",
            "x32": "linux-x86-net6.0",
        },
        "windows": {
            "arm64": "win-arm64-net6.0",
            "x64": "win-x64-net6.0",
            "x32": "win-x86-net6.0",
        }
    }[sublime.platform()][sublime.arch()]


class OmniSharp(AbstractPlugin):
    @classmethod
    def name(cls) -> str:
        return cls.__name__

    @classmethod
    def get_settings(cls) -> sublime.Settings:
        return sublime.load_settings(f"LSP-{cls.name()}.sublime-settings")

    @classmethod
    def version_str(cls) -> str:
        return VERSION

    @classmethod
    def installed_version_str(cls) -> str:
        with open(cls.basedir() / "VERSION", "r") as f:
            version = f.readline().strip()
            return version

    @classmethod
    def basedir(cls) -> Path:
        return Path(cls.storage_path()) / f"LSP-{cls.name()}"

    @classmethod
    def binary_path(cls) -> Path:
        if sublime.platform() == "windows":
            return cls.basedir() / "OmniSharp.exe"
        else:
            return cls.basedir() / "OmniSharp"

    @classmethod
    def get_command(cls) -> list[str]:
        settings = cls.get_settings()
        cmd = settings.get("command")
        if isinstance(cmd, list):
            return cmd
        return [
            str(cls.binary_path()),
            "--languageserver",
            "--encoding", "utf-8",
            "--hostPID", str(os.getpid()),
        ]

    @classmethod
    def needs_update_or_installation(cls) -> bool:
        try:
            if cls.version_str() == cls.installed_version_str():
                return False
        except Exception:
            pass
        return True

    @classmethod
    def install_or_update(cls) -> None:
        basedir = cls.basedir()
        shutil.rmtree(basedir, ignore_errors=True)
        basedir.mkdir(parents=True, exist_ok=True)
        zipfile = basedir / "omnisharp.zip"
        try:
            version = cls.version_str()
            urlretrieve(URL.format(version, _platform_str()), zipfile)
            with ZipFile(zipfile, "r") as f:
                f.extractall(basedir)
            zipfile.unlink()
            if sublime.platform() != "windows":
                cls.binary_path().chmod(0o744)
            with open(basedir / "VERSION", "w") as fp:
                fp.write(version)
        except Exception:
            shutil.rmtree(basedir, ignore_errors=True)
            raise

    @classmethod
    def on_pre_start(
        cls,
        window: sublime.Window,
        initiating_view: sublime.View,
        workspace_folders: list[WorkspaceFolder],
        configuration: ClientConfig
    ) -> Optional[str]:
        configuration.command = cls.get_command()
        return None

    # -- commands from the server that should be handled client-side ----------

    def on_pre_server_command(
        self,
        command: dict[str, Any],
        done_callback: Callable[[], None]
    ) -> bool:
        name = command["command"]
        if name == "omnisharp/client/findReferences":
            return self._handle_quick_references(command["arguments"], done_callback)
        return False

    def _handle_quick_references(self, arguments: list[Any], done_callback: Callable[[], None]) -> bool:
        session = self.weaksession()
        if not session:
            return True
        sb = session.get_session_buffer_for_uri_async(arguments[0]["uri"])
        if not sb:
            return True
        for sv in sb.session_views:
            if not sv.view.is_valid():
                continue
            region = range_to_region(arguments[0]["range"], sv.view)
            args = {"point": region.a}
            sv.view.run_command("lsp_symbol_references", args)
            done_callback()
            return True
        return True

    # --- custom notification handlers ----------------------------------------

    def _print(self, sticky: bool, fmt: str, *args: Any) -> None:
        session = self.weaksession()
        if session:
            message = fmt.format(*args)
            if sticky:
                session.set_window_status_async(self.name(), message)
            else:
                session.erase_window_status_async(self.name())
                session.window.status_message(message)

    def m_o__msbuildprojectdiagnostics(self, params: Any) -> None:
        self._print(True, "Compiled {}", params["FileName"])

    def m_o__projectconfiguration(self, params: Any) -> None:
        self._print(False, "Project configured")

    def m_o__unresolveddependencies(self, params: Any) -> None:
        self._print(False, "{} has unresolved dependencies", params["FileName"])

    def _get_assembly_name(self, params: Any) -> Optional[str]:
        project = params.get("MsBuildProject")
        if project:
            assembly_name = project.get("AssemblyName")
            if isinstance(assembly_name, str):
                return assembly_name
        return None

    def m_o__projectadded(self, params: Any) -> None:
        assembly_name = self._get_assembly_name(params)
        if assembly_name:
            self._print(False, "Project added: {}", assembly_name)

    def m_o__projectchanged(self, params: Any) -> None:
        assembly_name = self._get_assembly_name(params)
        if assembly_name:
            self._print(False, "Project changed: {}", assembly_name)


def plugin_loaded() -> None:
    register_plugin(OmniSharp)


def plugin_unloaded() -> None:
    unregister_plugin(OmniSharp)
