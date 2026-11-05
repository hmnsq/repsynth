// © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Harness for the Verilated co-simulation platform (P5.5, P5.11). It loads a static RV32 ELF exactly as
// a Linux loader would (every PT_LOAD segment at its address, .bss zeroed), places the trap stub at
// mtvec, starts the core at the ELF entry, and serves the program's write and exit system calls through
// the stub's mailbox, so the same binary that runs in QEMU user mode runs here unchanged.
//
// Usage: rs_tb <elf> <trap.bin> <stdout-file> <summary.json> <max-cycles> <start_pc|-> <stop_pc|-> [-- args...]
// The initial stack is laid out as Linux lays it out for a static program: argc, argv[], NULL, an empty
// environment, an empty auxiliary vector, then the strings. A boot stub at BOOT (also outside the
// program) loads sp and jumps to the ELF entry, as exec does. System calls served: openat (read only,
// host path), read, close, write, exit, exit_group.
// Counts: cycles from reset release to exit; retired instructions (the core's minstret event, which
// excludes trapping instructions such as ecall); and, when trigger addresses are given, the cycles and
// retired instructions between the first retirement of start_pc and the first retirement of stop_pc.
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <elf.h>
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

#include "Vrs_tb_top.h"
#include "verilated.h"

namespace {
const uint32_t MTVEC = 0x00001000u;
const uint32_t BOOT = 0x00000800u;
const uint32_t MAILBOX = 0xf1000000u;
const uint32_t STACK_TOP = 0x7ffff000u;
std::unordered_map<uint32_t, std::vector<uint8_t>> pages;  // 4 KiB pages, created on first touch
uint32_t mbox[16];  // 0 a0, 1 a1, 2 a2, 3 a7 (trigger), 4 return, 5 t5 save, 6 mcause, 7 mepc, 8 sp, 9 entry
std::vector<FILE *> files;
bool done = false;
int exit_code = -1;
std::string fault;
FILE *out = nullptr;
uint64_t out_bytes = 0;
uint64_t retired = 0, cycle = 0;
uint32_t start_pc = 0, stop_pc = 0;
bool have_triggers = false;
int64_t start_cycle = -1, stop_cycle = -1, start_ret = -1, stop_ret = -1;

uint8_t *byte_at(uint32_t a) {
  auto &p = pages[a >> 12];
  if (p.empty()) p.assign(4096, 0);
  return &p[a & 0xfffu];
}
uint32_t rd32(uint32_t a) {
  uint32_t v = 0;
  for (int i = 0; i < 4; i++) v |= (uint32_t)*byte_at(a + i) << (8 * i);
  return v;
}

void syscall() {
  uint32_t a0 = mbox[0], a1 = mbox[1], a2 = mbox[2], a7 = mbox[3], cause = mbox[6], epc = mbox[7];
  if (cause != 11) {  // 11: environment call from M-mode
    char b[128];
    snprintf(b, sizeof b, "trap mcause=%u mepc=0x%08x", cause, epc);
    fault = b;
    done = true;
    return;
  }
  if (a7 == 64) {  // write(fd, buf, len): fd 1 and 2 go to the stdout file
    for (uint32_t i = 0; i < a2; i++) fputc(*byte_at(a1 + i), out);
    out_bytes += a2;
    mbox[4] = a2;
    (void)a0;
  } else if (a7 == 56) {  // openat(dirfd, path, flags, mode): read-only
    std::string path;
    for (uint32_t i = 0; *byte_at(a1 + i) && i < 4096; i++) path.push_back((char)*byte_at(a1 + i));
    FILE *f = (a2 & 3u) == 0 ? fopen(path.c_str(), "rb") : nullptr;
    if (!f) { mbox[4] = (uint32_t)-2; return; }  // -ENOENT
    files.push_back(f);
    mbox[4] = (uint32_t)(files.size() - 1 + 3);
  } else if (a7 == 63) {  // read(fd, buf, n)
    uint32_t i = a0 - 3;
    if (a0 < 3 || i >= files.size() || !files[i]) { mbox[4] = (uint32_t)-9; return; }  // -EBADF
    uint32_t k = 0;
    int ch;
    while (k < a2 && (ch = fgetc(files[i])) != EOF) *byte_at(a1 + k++) = (uint8_t)ch;
    mbox[4] = k;
  } else if (a7 == 57) {  // close(fd)
    uint32_t i = a0 - 3;
    if (a0 >= 3 && i < files.size() && files[i]) { fclose(files[i]); files[i] = nullptr; mbox[4] = 0; }
    else mbox[4] = (uint32_t)-9;
  } else if (a7 == 93 || a7 == 94) {  // exit, exit_group
    exit_code = (int)a0;
    done = true;
  } else {
    char b[96];
    snprintf(b, sizeof b, "unsupported system call %u at mepc=0x%08x", a7, epc);
    fault = b;
    done = true;
  }
}

bool load_elf(const char *path, uint32_t &entry) {
  FILE *f = fopen(path, "rb");
  if (!f) return false;
  std::vector<uint8_t> d;
  uint8_t buf[65536];
  size_t n;
  while ((n = fread(buf, 1, sizeof buf, f)) > 0) d.insert(d.end(), buf, buf + n);
  fclose(f);
  if (d.size() < sizeof(Elf32_Ehdr)) return false;
  auto *eh = reinterpret_cast<Elf32_Ehdr *>(d.data());
  if (memcmp(eh->e_ident, ELFMAG, SELFMAG) != 0 || eh->e_ident[EI_CLASS] != ELFCLASS32 || eh->e_machine != EM_RISCV) return false;
  entry = eh->e_entry;
  for (int i = 0; i < eh->e_phnum; i++) {
    auto *ph = reinterpret_cast<Elf32_Phdr *>(d.data() + eh->e_phoff + i * eh->e_phentsize);
    if (ph->p_type != PT_LOAD) continue;
    for (uint32_t k = 0; k < ph->p_memsz; k++) *byte_at(ph->p_vaddr + k) = k < ph->p_filesz ? d[ph->p_offset + k] : 0;
  }
  return true;
}
}  // namespace

extern "C" unsigned int rs_mem_read(unsigned int a) {
  if ((a & 0xffffffc0u) == MAILBOX) return mbox[(a >> 2) & 15];
  return rd32(a);
}
extern "C" void rs_mem_write(unsigned int a, unsigned int v, unsigned int be) {
  if ((a & 0xffffffc0u) == MAILBOX) {
    unsigned i = (a >> 2) & 15;
    mbox[i] = v;
    if (i == 3) syscall();
    return;
  }
  for (int i = 0; i < 4; i++)
    if (be & (1u << i)) *byte_at(a + i) = (uint8_t)(v >> (8 * i));
}
extern "C" void rs_retire(unsigned int pc) {
  retired++;
  if (have_triggers) {
    if (pc == start_pc && start_cycle < 0) { start_cycle = (int64_t)cycle; start_ret = (int64_t)retired; }
    if (pc == stop_pc && stop_cycle < 0 && start_cycle >= 0) { stop_cycle = (int64_t)cycle; stop_ret = (int64_t)retired; }
  }
}
extern "C" void rs_bus_error(unsigned int a, unsigned int atop) {
  char b[96];
  snprintf(b, sizeof b, "atomic memory operation atop=0x%x at 0x%08x is not served", atop, a);
  fault = b;
  done = true;
}

int main(int argc, char **argv) {
  if (argc < 8) {
    fprintf(stderr, "usage: %s <elf> <trap.bin> <stdout-file> <summary.json> <max-cycles> <start_pc|-> <stop_pc|-> [-- args...]\n", argv[0]);
    return 2;
  }
  uint32_t entry = 0;
  if (!load_elf(argv[1], entry)) { fprintf(stderr, "cannot load ELF %s\n", argv[1]); return 2; }
  // The stub file holds the boot stub at offset 0 and the trap stub at offset MTVEC - BOOT.
  FILE *t = fopen(argv[2], "rb");
  if (!t) { fprintf(stderr, "cannot open %s\n", argv[2]); return 2; }
  int c, k = 0;
  while ((c = fgetc(t)) != EOF) *byte_at(BOOT + k++) = (uint8_t)c;
  fclose(t);
  out = fopen(argv[3], "wb");
  uint64_t max_cycles = strtoull(argv[5], nullptr, 0);
  if (strcmp(argv[6], "-") != 0 && strcmp(argv[7], "-") != 0) {
    start_pc = strtoul(argv[6], nullptr, 0); stop_pc = strtoul(argv[7], nullptr, 0); have_triggers = true;
  }
  // Program arguments: argv[0] is the ELF path, then everything after "--".
  std::vector<std::string> pargs{argv[1]};
  for (int i = 8; i < argc; i++) {
    if (i == 8 && strcmp(argv[i], "--") == 0) continue;
    pargs.push_back(argv[i]);
  }
  uint32_t sp = STACK_TOP;
  std::vector<uint32_t> ptrs;
  for (auto &a : pargs) {
    sp -= (uint32_t)a.size() + 1;
    for (size_t i = 0; i <= a.size(); i++) *byte_at(sp + (uint32_t)i) = i < a.size() ? (uint8_t)a[i] : 0;
    ptrs.push_back(sp);
  }
  sp &= ~15u;
  std::vector<uint32_t> words{(uint32_t)pargs.size()};
  for (auto p : ptrs) words.push_back(p);
  words.push_back(0);                 // end of argv
  words.push_back(0);                 // empty environment
  words.push_back(0); words.push_back(0);  // AT_NULL
  sp -= (uint32_t)(4 * words.size());
  sp &= ~15u;
  for (size_t i = 0; i < words.size(); i++)
    for (int b = 0; b < 4; b++) *byte_at(sp + 4 * (uint32_t)i + b) = (uint8_t)(words[i] >> (8 * b));
  mbox[8] = sp;
  mbox[9] = entry;

  auto ctx = std::make_unique<VerilatedContext>();
  ctx->commandArgs(argc, argv);
  auto top = std::make_unique<Vrs_tb_top>(ctx.get());
  top->boot_addr_i = BOOT;
  top->mtvec_addr_i = MTVEC;
  top->clk_i = 0;
  top->rst_ni = 0;
  for (int i = 0; i < 10; i++) { top->clk_i = !top->clk_i; top->eval(); }
  top->rst_ni = 1;
  top->eval();
  while (!done && cycle < max_cycles) {
    top->clk_i = 1; top->eval();
    top->clk_i = 0; top->eval();
    cycle++;
  }
  top->final();
  fclose(out);
  FILE *s = fopen(argv[4], "w");
  fprintf(s, "{\n  \"entry\": \"0x%08x\",\n  \"finished\": %s,\n  \"exit_code\": %d,\n  \"fault\": \"%s\",\n", entry,
          done && fault.empty() ? "true" : "false", exit_code, fault.c_str());
  fprintf(s, "  \"cycles\": %llu,\n  \"retired\": %llu,\n  \"stdout_bytes\": %llu,\n  \"mcycle\": %llu,\n",
          (unsigned long long)cycle, (unsigned long long)retired, (unsigned long long)out_bytes,
          (unsigned long long)top->mcycle_o);
  if (have_triggers)
    fprintf(s, "  \"start_pc\": \"0x%08x\",\n  \"stop_pc\": \"0x%08x\",\n  \"region_cycles\": %lld,\n  \"region_retired\": %lld,\n",
            start_pc, stop_pc, (start_cycle >= 0 && stop_cycle >= 0) ? (long long)(stop_cycle - start_cycle) : -1LL,
            (start_ret >= 0 && stop_ret >= 0) ? (long long)(stop_ret - start_ret) : -1LL);
  fprintf(s, "  \"max_cycles\": %llu\n}\n", (unsigned long long)max_cycles);
  fclose(s);
  if (!fault.empty()) { fprintf(stderr, "FAULT %s\n", fault.c_str()); return 3; }
  if (!done) { fprintf(stderr, "did not finish within %llu cycles\n", (unsigned long long)max_cycles); return 4; }
  return exit_code == 0 ? 0 : 1;
}
