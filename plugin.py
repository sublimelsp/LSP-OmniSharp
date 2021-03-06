from urllib.request import urlretrieve
from zipfile import ZipFile
import os
import shutil
import subprocess
import tempfile

from LSP.plugin import AbstractPlugin
from LSP.plugin import register_plugin
from LSP.plugin import unregister_plugin
from LSP.plugin.core.typing import Any, Dict, Optional, Tuple, List
import sublime
from sublime import version

URL = "https://github.com/OmniSharp/omnisharp-roslyn/releases/download/v{}/omnisharp-{}.zip"


def _platform_str() -> str:
    platform = sublime.platform()
    if platform == "osx":
        return "osx"
    elif platform == "windows":
        if sublime.arch() == "x64":
            return "win-x64"
        else:
            return "win-x86"
    else:
        if sublime.arch() == "x64":
            return "linux-x64"
        else:
            return "linux-x86"


class OmniSharp(AbstractPlugin):
    @classmethod
    def name(cls) -> str:
        return cls.__name__

    @classmethod
    def configuration(cls) -> Tuple[sublime.Settings, str]:
        settings, filename = super().configuration()
        settings.set("command", cls.get_command())
        return settings, filename

    @classmethod
    def version_str(cls) -> str:
        settings = sublime.load_settings("LSP-{}.sublime-settings".format(cls.name()))
        return str(settings.get("version"))

    @classmethod
    def installed_version_str(cls) -> str:
        filename = os.path.join(cls.basedir(), "VERSION")
        with open(filename, "r") as f:
            version = f.readline().strip()
            return version

    @classmethod
    def basedir(cls) -> str:
        return os.path.join(cls.storage_path(), "LSP-{}".format(cls.name()))

    @classmethod
    def binary_path(cls) -> str:
        return os.path.join(cls.basedir(), "OmniSharp.exe")

    @classmethod
    def get_command(cls) -> List[str]:
        return getattr(cls, "get_{}_command".format(sublime.platform()))()

    @classmethod
    def get_windows_command(cls) -> List[str]:
        return [cls.binary_path(), "--languageserver", "--verbose"]

    @classmethod
    def get_osx_command(cls) -> List[str]:
        return cls.get_linux_command()

    @classmethod
    def get_linux_command(cls) -> List[str]:
        return ["mono"] + cls.get_windows_command()

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
        shutil.rmtree(cls.basedir(), ignore_errors=True)
        temp_unpacked_location = os.path.join(sublime.cache_path(), "omnisharp")
        zipfile = os.path.join(sublime.cache_path(), "{}.zip".format(cls.name()))
        try:
            version = cls.version_str()
            urlretrieve(URL.format(version, _platform_str()), zipfile)
            with ZipFile(zipfile, "r") as f:
                f.extractall(sublime.cache_path())
            os.rename(os.path.join(sublime.cache_path(), "omnisharp"), cls.basedir())
            os.unlink(zipfile)
            with open(os.path.join(cls.basedir(), "VERSION"), "w") as fp:
                fp.write(version)
        except Exception:
            shutil.rmtree(cls.basedir(), ignore_errors=True)
            shutil.rmtree(temp_unpacked_location, ignore_errors=True)
            shutil.rmtree(zipfile, ignore_errors=True)
            raise

    # notification handlers

    def _print(self, sticky: bool, fmt: str, *args: Any) -> None:
        session = self.weaksession()
        if session:
            message = fmt.format(*args)
            if sticky:
                session.set_status_message_async(self.name(), message)
            else:
                session.erase_status_message_async(self.name())
                session.window.status_message(message)

    def m_o__MsBuildProjectDiagnostics(self, params: Any) -> None:
        self._print(True, "Compiled {}", params["FileName"])

    def m_o__ProjectConfiguration(self, params: Any) -> None:
        self._print(False, "Project configured")

    def m_o__UnresolvedDependencies(self, params: Any) -> None:
        self._print(False, "{} has unresolved dependencies", params["FileName"])

    def _get_assembly_name(self, params: Any) -> Optional[str]:
        project = params.get("MsBuildProject")
        if project:
            assembly_name = project.get("AssemblyName")
            if isinstance(assembly_name, str):
                return assembly_name
        return None

    def m_o__ProjectAdded(self, params: Any) -> None:
        assembly_name = self._get_assembly_name(params)
        if assembly_name:
            self._print(False, "Project added: {}", assembly_name)

    def m_o__ProjectChanged(self, params: Any) -> None:
        assembly_name = self._get_assembly_name(params)
        if assembly_name:
            self._print(False, "Project changed: {}", assembly_name)


def plugin_loaded() -> None:
    register_plugin(OmniSharp)


def plugin_unloaded() -> None:
    unregister_plugin(OmniSharp)
