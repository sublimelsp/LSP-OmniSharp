from __future__ import annotations

from enum import IntEnum
from pathlib import Path
from typing import cast
from typing import TYPE_CHECKING
import ctypes
import os
import shutil

import sublime

if TYPE_CHECKING:
    from typing import Any

from urllib.request import urlretrieve
from zipfile import ZipFile

from LSP.plugin import command_handler
from LSP.plugin import LspPlugin
from LSP.plugin import notification_handler
from LSP.plugin import OnPreStartContext
from LSP.plugin import Promise
from LSP.plugin import range_to_region

VERSION = "1.40.0"
URL = "https://github.com/OmniSharp/omnisharp-roslyn/releases/download/v{}/omnisharp-{}.zip"


class ImageFileMachine(IntEnum):
    IMAGE_FILE_MACHINE_AMD64 = 0x8664
    IMAGE_FILE_MACHINE_ARM64 = 0xAA64
    IMAGE_FILE_MACHINE_I386 = 0x014C
    IMAGE_FILE_MACHINE_UNKNOWN = 0x0000

MACHINE_NAMES: dict[ImageFileMachine, str] = {
    ImageFileMachine.IMAGE_FILE_MACHINE_AMD64: "x64",
    ImageFileMachine.IMAGE_FILE_MACHINE_ARM64: "arm64",
    ImageFileMachine.IMAGE_FILE_MACHINE_I386: "x32",
    ImageFileMachine.IMAGE_FILE_MACHINE_UNKNOWN: "x64",
}


def get_host_arch() -> str:
    if sublime.platform() == "windows":
        kernel32 = ctypes.windll.kernel32
        c_ushort_p = ctypes.POINTER(ctypes.c_ushort)
        kernel32.IsWow64Process2.argtypes = (ctypes.c_void_p, c_ushort_p, c_ushort_p)
        process_machine = ctypes.c_ushort(0)
        native_machine  = ctypes.c_ushort(0)
        success = kernel32.IsWow64Process2(
            kernel32.GetCurrentProcess(), ctypes.byref(process_machine), ctypes.byref(native_machine))
        if success:
            return MACHINE_NAMES[cast(ImageFileMachine, native_machine.value)]
    return sublime.arch()


def _platform_str() -> str:
    return {
        "osx": {
            "arm64": "osx-arm64-net10.0",
            "x64": "osx-x64-net10.0",
            "x32": "osx",
        },
        "linux": {
            "arm64": "linux-arm64-net10.0",
            "x64": "linux-x64-net10.0",
            "x32": "linux-x86",
        },
        "windows": {
            "arm64": "win-arm64-net10.0",
            "x64": "win-x64-net10.0",
            "x32": "win-x86-net10.0",
        }
    }[sublime.platform()][get_host_arch()]


class OmniSharp(LspPlugin):
    @classmethod
    def on_pre_start_async(cls, context: OnPreStartContext) -> None:
        if cls.needs_update_or_installation():
            cls.install_or_update()
        context.variables.update({
            'host_pid': str(os.getpid()),
            'server_binary_path': str(cls.binary_path()),
        })

    @classmethod
    def installed_version_str(cls) -> str:
        with open(cls.plugin_storage_path / "VERSION", "r") as f:
            version = f.readline().strip()
            return version

    @classmethod
    def binary_path(cls) -> Path:
        if sublime.platform() == "windows":
            return cls.plugin_storage_path / "OmniSharp.exe"
        else:
            return cls.plugin_storage_path / "OmniSharp"

    @classmethod
    def needs_update_or_installation(cls) -> bool:
        try:
            if VERSION == cls.installed_version_str():
                return False
        except Exception:
            pass
        return True

    @classmethod
    def install_or_update(cls) -> None:
        basedir = cls.plugin_storage_path
        shutil.rmtree(basedir, ignore_errors=True)
        basedir.mkdir(parents=True, exist_ok=True)
        zipfile = basedir / "omnisharp.zip"
        try:
            version = VERSION
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

    # -- commands from the server that should be handled client-side ----------

    @command_handler("omnisharp/client/findReferences")
    def on_find_references(self, arguments: list[Any] | None) -> Promise[None]:
        if arguments:
            self._handle_quick_references(arguments)
        return Promise.resolve(None)

    def _handle_quick_references(self, arguments: list[Any]) -> None:
        session = self.weaksession()
        if not session:
            return
        sb = session.get_session_buffer_for_uri_async(arguments[0]["uri"])
        if not sb:
            return
        for sv in sb.session_views:
            if not sv.view.is_valid():
                continue
            region = range_to_region(sv.view, arguments[0]["range"])
            args = {"point": region.a}
            sv.view.run_command("lsp_symbol_references", args)
            return

    # --- custom notification handlers ----------------------------------------

    def _print(self, sticky: bool, fmt: str, *args: Any) -> None:
        session = self.weaksession()
        if session:
            message = fmt.format(*args)
            if sticky:
                session.set_config_status_async(message)
            else:
                session.set_config_status_async("")
                session.window.status_message(message)

    @notification_handler("o#/msbuildprojectdiagnostics")
    def on_msbuildprojectdiagnostics(self, params: Any) -> None:
        self._print(True, "Compiled {}", params["FileName"])

    @notification_handler("o#/projectconfiguration")
    def on_projectconfiguration(self, params: Any) -> None:
        self._print(False, "Project configured")

    @notification_handler("o#/unresolveddependencies")
    def on_unresolveddependencies(self, params: Any) -> None:
        self._print(False, "{} has unresolved dependencies", params["FileName"])

    def _get_assembly_name(self, params: Any) -> str | None:
        project = params.get("MsBuildProject")
        if project:
            assembly_name = project.get("AssemblyName")
            if isinstance(assembly_name, str):
                return assembly_name
        return None

    @notification_handler("o#/projectadded")
    def on_projectadded(self, params: Any) -> None:
        assembly_name = self._get_assembly_name(params)
        if assembly_name:
            self._print(False, "Project added: {}", assembly_name)

    @notification_handler("o#/projectchanged")
    def on_projectchanged(self, params: Any) -> None:
        assembly_name = self._get_assembly_name(params)
        if assembly_name:
            self._print(False, "Project changed: {}", assembly_name)


def plugin_loaded() -> None:
    OmniSharp.register()


def plugin_unloaded() -> None:
    OmniSharp.unregister()
