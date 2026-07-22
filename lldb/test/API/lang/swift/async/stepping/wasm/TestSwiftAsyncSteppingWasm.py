"""
Swift async step-over across an `await` on Wasm via WasmKit is not yet supported.

`thread step-over` on a line containing `await` does not advance past the suspension
to the next source line in the same function: it descends into the awaited callee
(and, for deeper cases, into the cooperative-executor runtime
`taskInvokeWithExclusionValue`, Actor.cpp) instead of following the logical async
edge. Straight-line step-over WITHIN an async function already works; only stepping
across the suspension is broken.

This is an LLDB Swift-language-runtime limitation, not a WasmKit gap:

  - The async step plans live in the shared plugin
    (SwiftLanguageRuntimeNames.cpp: CreateRunThroughTaskSwitchThreadPlan /
    GetStepThroughTrampolinePlan). ThreadWasm/ProcessWasm do not override step-plan
    creation, so those plans are reached, not gated off.
  - They read the continuation function pointer and async context and depend on
    task/continuation metadata that embedded Swift omits to minimise binary size.
    The equivalent native test TestSwiftAsyncStepOver.py is @skipEmbeddedSwift for
    the same reason (llvm-project commit be12e00c5bfc).

The test asserts the DESIRED behavior (step-over on the await line stays in
`caller()` and advances to `return a + b`) and is marked expectedFailure. When async
step-over across suspensions is implemented for Wasm/embedded Swift it will XPASS,
signalling that this xfail should be removed.
"""

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


class TestSwiftAsyncSteppingWasm(TestBase):
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
    @expectedFailureAll(
        bugnumber="Async step-over across await unsupported for embedded Swift; see module docstring."
    )
    def test_async_step_over_await(self):
        """`thread step-over` on an `await` line advances past the suspension, staying in caller()."""
        wasmkit = _find_wasmkit()
        if not wasmkit:
            self.skipTest("WasmKit not found (set WASMKIT or add to PATH)")

        wasm_path = self._compile_wasm()

        self.runCmd("settings set platform.plugin.wasm.runtime-path %s" % wasmkit)
        self.runCmd("settings set -- platform.plugin.wasm.port-arg --debugger-port=")
        self.runCmd("settings set platform.plugin.wasm.runtime-args run")

        target = self.dbg.CreateTarget(wasm_path)
        self.assertTrue(target, VALID_TARGET)

        bp = target.BreakpointCreateBySourceRegex(
            "step-over here", lldb.SBFileSpec("main.swift")
        )

        launch_info = target.GetLaunchInfo()
        error = lldb.SBError()
        process = target.Launch(launch_info, error)
        self.assertSuccess(error, "Launch failed")
        self.assertState(process.GetState(), lldb.eStateStopped)

        threads = lldbutil.get_threads_stopped_at_breakpoint(process, bp)
        self.assertEqual(len(threads), 1)
        thread = threads[0]

        desired_line = line_number("main.swift", "desired landing")
        thread.StepOver()

        frame0 = thread.GetFrameAtIndex(0)
        self.assertIn("caller", frame0.GetFunctionName(),
                      "step-over on await should stay in caller(), not descend into leaf()")
        self.assertEqual(frame0.GetLineEntry().GetLine(), desired_line,
                         "step-over on await should advance to the line after the await")
