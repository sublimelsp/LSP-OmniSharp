from urllib.request import urlretrieve
from zipfile import ZipFile
import os
import shutil

from LSP.plugin import AbstractPlugin
from LSP.plugin import register_plugin
from LSP.plugin import unregister_plugin
from LSP.plugin.core.typing import Any, Optional, Tuple, List, Mapping, Callable  # noqa: E501
from LSP.plugin.core.views import range_to_region  # TODO: not public API :(
import sublime

VERSION = "1.37.11"
URL = "https://github.com/OmniSharp/omnisharp-roslyn/releases/download/v{}/omnisharp-{}.zip"  # noqa: E501


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
        return VERSION

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
        if sublime.platform() == "windows":
            return os.path.join(cls.basedir(), "OmniSharp.exe")
        else:
            return os.path.join(cls.basedir(), "omnisharp", "OmniSharp.exe")

    @classmethod
    def get_command(cls) -> List[str]:
        return getattr(cls, "get_{}_command".format(sublime.platform()))()

    @classmethod
    def get_windows_command(cls) -> List[str]:
        return [cls.binary_path(), "--languageserver"]

    @classmethod
    def get_osx_command(cls) -> List[str]:
        return cls.get_linux_command()

    @classmethod
    def mono_bin_path(cls) -> str:
        return os.path.join(cls.basedir(), "bin", "mono")

    @classmethod
    def mono_config_path(cls) -> str:
        return os.path.join(cls.basedir(), "etc", "config")

    @classmethod
    def get_linux_command(cls) -> List[str]:
        return [
            cls.mono_bin_path(),
            "--assembly-loader=strict",
            "--config",
            cls.mono_config_path()
        ] + cls.get_windows_command()

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
        os.makedirs(cls.basedir(), exist_ok=True)
        zipfile = os.path.join(cls.basedir(), "omnisharp.zip")
        try:
            version = cls.version_str()
            urlretrieve(URL.format(version, _platform_str()), zipfile)
            with ZipFile(zipfile, "r") as f:
                f.extractall(cls.basedir())
            os.unlink(zipfile)
            if sublime.platform() != "windows":
                os.chmod(cls.mono_bin_path(), 0o744)
            with open(os.path.join(cls.basedir(), "VERSION"), "w") as fp:
                fp.write(version)
        except Exception:
            shutil.rmtree(cls.basedir(), ignore_errors=True)
            raise

    # -- commands from the server that should be handled client-side ----------

    def on_pre_server_command(
        self,
        command: Mapping[str, Any],
        done_callback: Callable[[], None]
    ) -> bool:
        name = command["command"]
        if name == "omnisharp/client/findReferences":
            return self._handle_quick_references(
                command["arguments"],
                done_callback
            )
        return False

    def _handle_quick_references(
        self,
        arguments: List[Any],
        done_callback: Callable[[], None]
    ) -> bool:
        session = self.weaksession()
        if not session:
            return False
        sb = session.get_session_buffer_for_uri_async(arguments[0]["uri"])
        if not sb:
            return False
        for sv in sb.session_views:
            if not sv.view.is_valid():
                continue
            region = range_to_region(arguments[0]["range"], sv.view)
            args = {"point": region.a}
            session.window.run_command("lsp_symbol_references", args)
            done_callback()
            return True
        return False

    # --- custom notification handlers ----------------------------------------

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
