// © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
// SPDX-License-Identifier: CERN-OHL-S-2.0
// Co-simulation top (P5.5, P5.11): cv32e40x with the CV-X-IF coprocessor, memories served through
// DPI-C by the C++ harness (rs_tb_main.cpp). Both OBI ports grant at once and answer one cycle later.
module rs_tb_top (  // build with +define+RS_XIF for the coprocessor variant
  input  logic        clk_i,
  input  logic        rst_ni,
  input  logic [31:0] boot_addr_i,
  input  logic [31:0] mtvec_addr_i,
  output logic [63:0] mcycle_o
);
  import "DPI-C" function int unsigned rs_mem_read(input int unsigned addr);
  import "DPI-C" function void rs_mem_write(input int unsigned addr, input int unsigned data, input int unsigned be);
  import "DPI-C" function void rs_retire(input int unsigned pc);
  import "DPI-C" function void rs_bus_error(input int unsigned addr, input int unsigned atop);

  cv32e40x_if_xif #(.X_NUM_RS(2), .X_ID_WIDTH(4)) xif ();

  logic        instr_req, instr_gnt, instr_rvalid;
  logic [31:0] instr_addr, instr_rdata;
  logic        data_req, data_gnt, data_rvalid, data_we;
  logic [31:0] data_addr, data_wdata, data_rdata;
  logic [3:0]  data_be;
  logic [5:0]  data_atop;
  logic        pc_valid;
  logic [31:0] pc;

  cv32e40x_core #(
    .M_EXT(cv32e40x_pkg::M), .A_EXT(cv32e40x_pkg::A), .X_EXT(1'b1), .X_NUM_RS(2), .X_ID_WIDTH(4)
  ) core_i (
    .clk_i, .rst_ni, .scan_cg_en_i(1'b0), .boot_addr_i, .dm_exception_addr_i(32'h0), .dm_halt_addr_i(32'h0),
    .mhartid_i(32'h0), .mimpid_patch_i(4'h0), .mtvec_addr_i,
    .instr_req_o(instr_req), .instr_gnt_i(instr_gnt), .instr_rvalid_i(instr_rvalid), .instr_addr_o(instr_addr),
    .instr_memtype_o(), .instr_prot_o(), .instr_dbg_o(), .instr_rdata_i(instr_rdata), .instr_err_i(1'b0),
    .data_req_o(data_req), .data_gnt_i(data_gnt), .data_rvalid_i(data_rvalid), .data_addr_o(data_addr),
    .data_be_o(data_be), .data_we_o(data_we), .data_wdata_o(data_wdata), .data_memtype_o(), .data_prot_o(),
    .data_dbg_o(), .data_atop_o(data_atop), .data_rdata_i(data_rdata), .data_err_i(1'b0), .data_exokay_i(1'b1),
    .mcycle_o, .time_i(64'h0),
    .xif_compressed_if(xif), .xif_issue_if(xif), .xif_commit_if(xif), .xif_mem_if(xif),
    .xif_mem_result_if(xif), .xif_result_if(xif),
    .irq_i(32'h0), .wu_wfe_i(1'b0), .clic_irq_i(1'b0), .clic_irq_id_i('0), .clic_irq_level_i(8'h0),
    .clic_irq_priv_i(2'h0), .clic_irq_shv_i(1'b0), .fencei_flush_req_o(), .fencei_flush_ack_i(1'b1),
    .debug_req_i(1'b0), .debug_havereset_o(), .debug_running_o(), .debug_halted_o(),
    .debug_pc_valid_o(pc_valid), .debug_pc_o(pc), .fetch_enable_i(1'b1), .core_sleep_o()
  );

`ifdef RS_XIF
  // The generated coprocessor (P5.5).
  rs_xif_xayebt #(.X_ID_WIDTH(4)) coproc_i (
    .clk_i, .rst_ni, .xif_compressed_if(xif), .xif_issue_if(xif), .xif_commit_if(xif), .xif_mem_if(xif),
    .xif_mem_result_if(xif), .xif_result_if(xif)
  );
`else
  // The binary baseline core (P5.11): no coprocessor; every offload is refused at once, so an
  // instruction outside the base ISA traps as illegal.
  assign xif.compressed_ready = 1'b1;
  assign xif.compressed_resp  = '0;
  assign xif.issue_ready      = 1'b1;
  assign xif.issue_resp       = '0;
  assign xif.result_valid     = 1'b0;
  assign xif.result           = '0;
  assign xif.mem_valid        = 1'b0;
  assign xif.mem_req          = '0;
`endif

  // The core does not use the memory interface of the extension here.
  assign xif.mem_ready = 1'b1;
  assign xif.mem_resp = '0;
  assign xif.mem_result_valid = 1'b0;
  assign xif.mem_result = '0;

  assign instr_gnt = instr_req;
  assign data_gnt  = data_req;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      instr_rvalid <= 1'b0; data_rvalid <= 1'b0; instr_rdata <= '0; data_rdata <= '0;
    end else begin
      instr_rvalid <= instr_req;
      if (instr_req) instr_rdata <= rs_mem_read({instr_addr[31:2], 2'b00});
      data_rvalid <= data_req;
      if (data_req) begin
        if (data_atop != 6'h0) rs_bus_error(data_addr, {26'h0, data_atop});
        if (data_we) begin
          rs_mem_write({data_addr[31:2], 2'b00}, data_wdata, {28'h0, data_be});
          data_rdata <= '0;
        end else begin
          data_rdata <= rs_mem_read({data_addr[31:2], 2'b00});
        end
      end
      if (pc_valid) rs_retire(pc);
    end
  end
endmodule
