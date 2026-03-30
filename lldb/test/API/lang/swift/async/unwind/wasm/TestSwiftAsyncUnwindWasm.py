import lldb
import os
import subprocess
import shutil
from lldbsuite.test import configuration
from lldbsuite.test.plugins import swift
from lldbsuite.test.lldbtest import *
from lldbsuite.test.decorators import *
import lldbsuite.test.lldbutil as lldbutil


def _find_wasmkit():
    """Return the path to the wasmkit binary, or None."""
    path = os.environ.get("WASMKIT")
    if path and os.path.isfile(path):
        return path
    return shutil.which("wasmkit") or shutil.which("wasmkit-cli")


class TestSwiftAsyncUnwindWasm(TestBase):
    NO_DEBUG_INFO_TESTCASE = True

    def _compile_wasm(self):
        """Compile main.swift to an embedded a.wasm with DWARF via raw swiftc."""
        swiftc = configuration.swiftCompiler or swift.getSwiftCompiler()
        if not swiftc or not os.path.isfile(swiftc):
            self.skipTest("swiftc not found (pass --swift-compiler or set SWIFTC)")

        sysroot = os.environ.get("WASI_SYSROOT")
        if not sysroot or not os.path.isdir(sysroot):
            self.skipTest("WASI sysroot not found (set WASI_SYSROOT)")

        swift_res = os.environ.get("SWIFT_WASI_RESOURCE_DIR")
        if not swift_res or not os.path.isdir(swift_res):
            self.skipTest("Swift wasm resource dir not found (set SWIFT_WASI_RESOURCE_DIR)")

        concurrency = os.path.join(
            swift_res, "embedded", "wasm32-unknown-wasip1", "libswift_Concurrency.a")
        if not os.path.isfile(concurrency):
            self.skipTest("embedded libswift_Concurrency.a not found under resource dir")

        src = self.getSourcePath("main.swift")
        out = self.getBuildArtifact("a.wasm")
        cmd = [
            swiftc,
            "-parse-as-library", "-g", "-Onone",
            "-enable-experimental-feature", "Embedded", "-wmo",
            "-target", "wasm32-unknown-wasip1",
            "-sdk", sysroot,
            "-resource-dir", swift_res,
        ]
        clang_res = os.environ.get("WASI_RESOURCE_DIR", "")
        if clang_res and os.path.isdir(clang_res):
            cmd += ["-Xclang-linker", "-resource-dir=" + clang_res]
        cmd += ["-Xclang-linker", concurrency, "-o", out, src]
        subprocess.check_call(cmd)
        return out

    @swiftTest
    @skipIf(oslist=["windows"])
    def test_async_backtrace(self):
        """Async backtraces work for Swift on Wasm via WasmKit."""
        wasmkit = _find_wasmkit()
        if not wasmkit:
            self.skipTest("WasmKit not found (set WASMKIT or add to PATH)")

        wasm_path = self._compile_wasm()

        self.runCmd("settings set platform.plugin.wasm.runtime-path %s" % wasmkit)
        self.runCmd("settings set -- platform.plugin.wasm.port-arg --debugger-port=")
        self.runCmd("settings set platform.plugin.wasm.runtime-args run")

        target = self.dbg.CreateTarget(wasm_path)
        self.assertTrue(target, VALID_TARGET)
        self.assertEqual(target.GetPlatform().GetName(), "wasm")

        bp = target.BreakpointCreateBySourceRegex(
            "break here", lldb.SBFileSpec("main.swift")
        )

        launch_info = target.GetLaunchInfo()
        error = lldb.SBError()
        process = target.Launch(launch_info, error)
        self.assertSuccess(error, "Launch failed")
        self.assertState(process.GetState(), lldb.eStateStopped)

        threads = lldbutil.get_threads_stopped_at_breakpoint(process, bp)
        self.assertEqual(len(threads), 1)
        thread = threads[0]

        frame0 = thread.GetFrameAtIndex(0)
        self.assertTrue(frame0.IsValid())
        self.assertIn("inner", frame0.GetFunctionName())

        frame1 = thread.GetFrameAtIndex(1)
        self.assertTrue(frame1.IsValid())
        self.assertIn("outer", frame1.GetFunctionName())

        frame2 = thread.GetFrameAtIndex(2)
        self.assertTrue(frame2.IsValid())
        fn2 = frame2.GetFunctionName()
        self.assertTrue(
            "main" in fn2 or "Main" in fn2,
            "Expected main/Main in frame 2, got: %s" % fn2,
        )
