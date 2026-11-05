/* © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Linker script for picolibc programs run as static Linux user programs in
 * QEMU user mode. Load and virtual addresses are equal, so the loader places
 * every segment where it runs. Defines the symbols picolibc's TLS helpers use.
 */
ENTRY(_start)
SECTIONS
{
	. = 0x10000;
	.text : { *(.text.init) *(.text.unlikely .text.unlikely.*) *(.text.startup .text.startup.*) *(.text .text.*) }
	.rodata : { *(.rodata .rodata.*) *(.srodata .srodata.*) }
	. = ALIGN(0x1000);
	.data : {
		*(.data .data.*)
		. = ALIGN(8);
		PROVIDE( __global_pointer$ = . + 0x800 );
		*(.sdata .sdata.* .sdata2.*)
	}
	.tdata : ALIGN_WITH_INPUT { *(.tdata .tdata.*) }
	PROVIDE( __tls_base = ADDR(.tdata) );
	PROVIDE( __tdata_source = LOADADDR(.tdata) );
	PROVIDE( __tdata_size = SIZEOF(.tdata) );
	.tbss : { *(.tbss .tbss.*) *(.tcommon) }
	PROVIDE( __tbss_offset = ADDR(.tbss) - ADDR(.tdata) );
	PROVIDE( __tbss_size = SIZEOF(.tbss) );
	PROVIDE( __tls_size = __tbss_offset + __tbss_size );
	PROVIDE( __tls_align = MAX(ALIGNOF(.tdata), ALIGNOF(.tbss)) );
	PROVIDE( __tls_size_align = (__tls_size + __tls_align - 1) & ~(__tls_align - 1) );
	.tbss_space (NOLOAD) : { . = ADDR(.tbss); . = . + SIZEOF(.tbss); }
	.bss : { *(.sbss .sbss.*) *(.bss .bss.*) *(COMMON) . = ALIGN(8); }
	PROVIDE( __heap_start = . );
	. = . + 0x10000;
	PROVIDE( __heap_end = . );
	PROVIDE( end = . );
	/DISCARD/ : { *(.note .note.*) *(.eh_frame .eh_frame.*) }
}
