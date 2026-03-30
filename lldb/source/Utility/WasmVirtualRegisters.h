//===----------------------------------------------------------------------===//
//
// Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

#ifndef LLDB_SOURCE_UTILITY_WASM_VIRTUAL_REGISTERS_H
#define LLDB_SOURCE_UTILITY_WASM_VIRTUAL_REGISTERS_H

#include "lldb/lldb-private.h"

namespace lldb_private {

// LLDB doesn't have an address space to represents WebAssembly locals,
// globals and operand stacks. We encode these elements into virtual
// registers:
//
//   | tag: 2 bits | index: 30 bits |
//
// Where tag is:
//    0: Not a Wasm location
//    1: Local
//    2: Global
//    3: Operand stack value
enum WasmVirtualRegisterKinds {
  eWasmTagNotAWasmLocation = 0,
  eWasmTagLocal = 1,
  eWasmTagGlobal = 2,
  eWasmTagOperandStack = 3,
};

static const uint32_t kWasmVirtualRegisterTagMask = 0x03;
static const uint32_t kWasmVirtualRegisterIndexMask = 0x3fffffff;
static const uint32_t kWasmVirtualRegisterTagShift = 30;

inline uint32_t GetWasmVirtualRegisterTag(size_t reg) {
  return (reg >> kWasmVirtualRegisterTagShift) & kWasmVirtualRegisterTagMask;
}

inline uint32_t GetWasmVirtualRegisterIndex(size_t reg) {
  return reg & kWasmVirtualRegisterIndexMask;
}

inline uint32_t GetWasmRegister(uint8_t tag, uint32_t index) {
  return ((tag & kWasmVirtualRegisterTagMask) << kWasmVirtualRegisterTagShift) |
         (index & kWasmVirtualRegisterIndexMask);
}

namespace wasm {

/// Each WebAssembly module has separated address spaces for Code and Memory.
enum WasmAddressType : uint8_t { Memory = 0x00, Object = 0x01, Invalid = 0xff };

/// For the purpose of debugging, we can represent all these separated 32-bit
/// address spaces with a single virtual 64-bit address space. The
/// wasm_addr_t provides this encoding using bitfields.
struct wasm_addr_t {
  uint64_t offset : 32;
  uint64_t module_id : 30;
  uint64_t type : 2;

  wasm_addr_t(lldb::addr_t addr)
      : offset(addr & 0x00000000ffffffff),
        module_id((addr & 0x00ffffff00000000) >> 32), type(addr >> 62) {}

  wasm_addr_t(WasmAddressType type, uint32_t module_id, uint32_t offset)
      : offset(offset), module_id(module_id), type(type) {}

  WasmAddressType GetType() const { return static_cast<WasmAddressType>(type); }
  uint32_t GetModuleID() const { return module_id; }
  uint32_t GetOffset() const { return offset; }

  operator lldb::addr_t() { return *(uint64_t *)this; }
};

static_assert(sizeof(wasm_addr_t) == 8, "");

} // namespace wasm

} // namespace lldb_private

#endif
