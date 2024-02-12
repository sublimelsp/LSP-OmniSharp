from urllib.request import urlretrieve
from zipfile import ZipFile
import os
import shutil

from LSP.plugin import AbstractPlugin
from LSP.plugin import ClientConfig
from LSP.plugin import register_plugin
from LSP.plugin import unregister_plugin
from LSP.plugin import WorkspaceFolder
from LSP.plugin.core.typing import Any, Optional, List, Mapping, Callable
from LSP.plugin.core.views import range_to_region  # TODO: not public API :(
import sublime

DEFAULT_VERSION = "1.39.11"
URL = "https://github.com/OmniSharp/omnisharp-roslyn/releases/download/v{}/{}"  # noqa: E501

OMNISHARP_ARCHIVE = {
    "windows": {
        "x64": "omnisharp-win-x64.zip",
    },
    "linux": {
        "x64": "omnisharp-linux-x64-net6.0.zip",
        "arm64": "omnisharp-linux-arm64-net6.0.zip",
    },
    "osx": {
        "x64": "omnisharp-osx-x64-net6.0.zip",
        "arm64": "omnisharp-osx-arm64-net6.0.zip",
    }
}

def _omnisharp_archive() -> str:
    platform = sublime.platform()
    arch = sublime.arch()
    try:
        return OMNISHARP_ARCHIVE[platform][arch]
    except KeyError:
        raise RuntimeError("{}-{} is not a supported combination.".format(platform, arch))


class OmniSharp(AbstractPlugin):
    @classmethod
    def name(cls) -> str:
        return cls.__name__

    @classmethod
    def get_settings(cls) -> sublime.Settings:
        return sublime.load_settings(
            "LSP-{}.sublime-settings".format(cls.name())
        )

    @classmethod
    def version_str(cls) -> str:
        settings = cls.get_settings().get("settings")
        version = DEFAULT_VERSION
        if settings is not None:
            version = settings.get("omnisharp.version")
            if version is None:
                version = DEFAULT_VERSION
        return version

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
        platform = sublime.platform()
        if platform == "windows":
            return os.path.join(cls.basedir(), "OmniSharp.exe")
        else:
            return os.path.join(cls.basedir(), "OmniSharp")

    @classmethod
    def get_command(cls) -> List[str]:
        settings = cls.get_settings()
        cmd = settings.get("command")
        if isinstance(cmd, list):
            return cmd
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
        return cls.get_windows_command()

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
        platform = sublime.platform()
        shutil.rmtree(cls.basedir(), ignore_errors=True)
        os.makedirs(cls.basedir(), exist_ok=True)
        zipfile = os.path.join(cls.basedir(), "omnisharp.zip")
        try:
            version = cls.version_str()
            archive_url = URL.format(version, _omnisharp_archive())
            print("Fetching: {}".format(archive_url))
            urlretrieve(archive_url, zipfile)
            with ZipFile(zipfile, "r") as f:
                f.extractall(cls.basedir())
            os.unlink(zipfile)

            if platform != "windows":
                os.chmod(cls.binary_path(), 0o744)

            with open(os.path.join(cls.basedir(), "VERSION"), "w") as fp:
                fp.write(version)

        except Exception:
            shutil.rmtree(cls.basedir(), ignore_errors=True)
            raise

    @classmethod
    def on_pre_start(
        cls,
        window: sublime.Window,
        initiating_view: sublime.View,
        workspace_folders: List[WorkspaceFolder],
        configuration: ClientConfig
    ) -> Optional[str]:
        configuration.command = cls.get_command()
        return None

    # -- commands from the server that should be handled client-side ----------

    def on_pre_server_command(
        self,
        command: Mapping[str, Any],
        done_callback: Callable[[], None]
    ) -> bool:
        name = command["command"]
        if name == "omnisharp/client/findReferences":
            return self._handle_quick_references(command["arguments"], done_callback)
        return False

    def _handle_quick_references(self, arguments: List[Any], done_callback: Callable[[], None]) -> bool:
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
