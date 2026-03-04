
module tt_um_globaltimer_sched (
    input wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input wire ena,
    input wire clk,
    input wire rst_n
);

  // reset and enable
  wire rst_i = ~rst_n;
  wire night_en = ena & ui_in[7];

  // write interface
  wire wr_stb = ui_in[6];
  wire [1:0] event_sel = ui_in[5:4];
  wire [1:0] reg_sel = ui_in[3:2];
  wire [7:0] wr_data = uio_in;

  // global timer (epoch domain)
  wire epoch_tick;
  wire epoch_end;
  wire [9:0]  epoch_index;

  globaltimer_epoch #(
    .clk_speed_hz    (10_000_000),
    .epoch_hz        (100),
    .epoch_count_max (1000)
  ) u_timer (
    .clk_i        (clk),
    .rst_i        (rst_i),
    .en_i         (night_en),
    .epoch_tick_o (epoch_tick),
    .epoch_end_o  (epoch_end),
    .epoch_index_o(epoch_index)
  );

  // window generator (256 epochs)
  wire window_start_pulse, window_end_pulse;

  window_gen_pow2 #(
    .WINDOW_LEN_LOG2(8) // 256
  ) u_window (
    .clk_i          (clk),
    .rst_i          (rst_i),
    .en_i           (night_en),
    .tick_i         (epoch_tick),
    .window_start_o (window_start_pulse),
    .window_end_o   (window_end_pulse)
  );

  // 4-event scheduler in epoch units
  wire       event_active;
  wire [1:0] event_id;

  event_scheduler4_epoch u_sched (
    .clk_i          (clk),
    .rst_i          (rst_i),
    .wr_stb_i       (wr_stb),
    .event_sel_i    (event_sel),
    .reg_sel_i      (reg_sel),
    .wr_data_i      (wr_data),
    .epoch_i        (epoch_index),
    .event_active_o (event_active),
    .event_id_o     (event_id)
  );

  // Debug serial: 8-bit frame, shifts at epoch_tick, loads on epoch_end
  // Frame example:
  //   [7]   = event_active
  //   [6:5] = event_id
  //   [4]   = window_end
  //   [3]   = epoch_end (also load trigger)
  //   [2:0] = epoch_index[2:0] (tiny moving signature)
  wire debug_serial;

  debug_shifter_small #(
    .FRAME_BITS(8)
  ) u_dbg (
    .clk_i    (clk),
    .rst_i    (rst_i),
    .tick_i   (epoch_tick),
    .load_i   (epoch_end),
    .frame_i  ({ event_active, event_id, window_end_pulse, epoch_end, epoch_index[2:0] }),
    .serial_o (debug_serial)
  );

  // outputs
  assign uo_out[0] = debug_serial;
  assign uo_out[1] = event_active;
  assign uo_out[3:2] = event_id;
  assign uo_out[4] = window_start_pulse;
  assign uo_out[5] = window_end_pulse;
  assign uo_out[6] = epoch_tick;
  assign uo_out[7] = epoch_end;

  assign uio_out = 8'h00;
  assign uio_oe  = 8'h00; 

endmodule

////////////////////////////////////////////////////////////////
//global epoch timer

//example usage for sensing:
// always_ff @(posedge clk)
//   if(epoch_tick)
//       sensor_sample <= sensor_input;

module globaltimer_epoch #(
  parameter int unsigned clk_speed_hz = 10_000_000, //clock speed
  parameter int unsigned epoch_hz = 100,        //sample rate
  parameter int unsigned epoch_count_max = 1000        //signal that goes high after certain number of samples
)(
  input  logic clk_i,
  input  logic rst_i,
  input  logic en_i,                             //when we "start" counting from
  output logic epoch_tick_o,                     //pulse every epoch, when we would sample for example
  output logic epoch_end_o,                      //pulse for 1 clk when epoch_index wraps (epoch_count_max-1 -> 0) 
  output logic [9:0] epoch_index_o                     //current epoch index, counts 0..epoch_count_max-1
);

  localparam int unsigned CYCLES_PER_EPOCH = (clk_speed_hz >= epoch_hz && epoch_hz >= 1) ? (clk_speed_hz / epoch_hz) : 1;
  localparam int unsigned DIV_W = (CYCLES_PER_EPOCH <= 1) ? 1 : $clog2(CYCLES_PER_EPOCH); //divider width

  logic [DIV_W-1:0] div_q;

  wire tick = en_i && (div_q == CYCLES_PER_EPOCH-1);

  always_ff @(posedge clk_i) begin
    if (rst_i) begin //sync reset
      div_q <= '0;
      epoch_index_o <= '0;
      epoch_end_o <= 1'b0;
    end else begin
      epoch_end_o <= 1'b0;

      if (en_i) begin
        if (div_q == CYCLES_PER_EPOCH-1) div_q <= '0;
        else div_q <= div_q + 1'b1;
      end

      if (tick) begin
        if (epoch_index_o == epoch_count_max-1) begin
          epoch_index_o <= '0;
          epoch_end_o  <= 1'b1;
        end else begin
          epoch_index_o <= epoch_index_o + 10'd1;
        end
      end
    end
  end

  assign epoch_tick_o = tick;

endmodule

//////////////////////////////////////////////////////////////////
// window generator with power of 2 length for hardware efficiency
// Example usage for computing rms motion:
// always_ff @(posedge clk) begin
//     if (window_start_o)
//         energy_sum <= 0;
//     else if (epoch_tick)
//         energy_sum <= energy_sum + sample*sample;
// end
// Example usage for triggering ML inferences:
// if (window_end_o)
//     run_inference <= 1;

module window_gen_pow2 #(
  parameter int unsigned WINDOW_LEN_LOG2 = 8
)(
  input  logic clk_i,
  input  logic rst_i,
  input  logic en_i,
  input  logic tick_i,
  output logic window_start_o,
  output logic window_end_o
);

  logic [WINDOW_LEN_LOG2-1:0] wcnt_q;

  always_ff @(posedge clk_i) begin
    if (rst_i) begin
      wcnt_q <= '0;
      window_start_o <= 1'b0;
      window_end_o <= 1'b0;
    end else begin
      window_start_o <= 1'b0;
      window_end_o <= 1'b0;

      if (en_i && tick_i) begin
        if (wcnt_q == '0) window_start_o <= 1'b1;
        if (&wcnt_q) window_end_o <= 1'b1;
        wcnt_q <= wcnt_q + 1'b1; // wraps around
      end
    end
  end

endmodule


///////////////////////////////////////////////////////////////
// 4-event scheduler (epoch-based).
// event active if enable, time > start, and time < end
// Priority: 0 > 1 > 2 > 3

// Example usage for programming an event:
// Event 1
// Start = 30 seconds
// Duration = 10 seconds
// Enable = 1

// Step 1 — Write start low byte
// event_sel_i = 01
// reg_sel_i   = 00
// wr_data_i   = 30
// wr_stb_i    = 1

// Step 2 — Write start high bits
// event_sel_i = 01
// reg_sel_i   = 01
// wr_data_i   = 0
// wr_stb_i    = 1

// Step 3 — Write duration
// event_sel_i = 01
// reg_sel_i   = 10
// wr_data_i   = 10
// wr_stb_i    = 1

// Step 4 — Enable event
// event_sel_i = 01
// reg_sel_i   = 11
// wr_data_i   = 1
// wr_stb_i    = 1

// Example usage for sensing:
// always_ff @(posedge clk) begin
//     if (event_active_o && event_id_o == 2)
//         sensor_enable <= 1;
//     else
//         sensor_enable <= 0;
// end

// Example usage for triggering ML inferences:
// always_ff @(posedge clk) begin
//     if (event_active_o && event_id_o == 1 && window_end_o)
//         run_classifier <= 1;
//     else
//         run_classifier <= 0;
// end

module event_scheduler4_epoch (
  input logic clk_i,
  input logic rst_i,

  input logic wr_stb_i,       //allow writes
  input logic [1:0] event_sel_i,    
  input logic [1:0] reg_sel_i,
  input logic [7:0] wr_data_i,

  input logic [9:0] epoch_i,

  output logic event_active_o,
  output logic [1:0] event_id_o
);

  logic [9:0] start_q [0:3];
  logic [9:0] dur_q [0:3];
  logic en_q [0:3];

  integer k;
  always_ff @(posedge clk_i) begin
    if (rst_i) begin
      for (k = 0; k < 4; k = k + 1) begin
        start_q[k] <= 10'd0;
        dur_q[k] <= 10'd0;
        en_q[k] <= 1'b0;
      end
    end else if (wr_stb_i) begin
      unique case (reg_sel_i)
        2'b00: start_q[event_sel_i][7:0] <= wr_data_i;       // start_lo
        2'b01: start_q[event_sel_i][9:8] <= wr_data_i[1:0];  // start_hi (2 bits)
        2'b10: dur_q[event_sel_i][7:0] <= wr_data_i;         // dur_lo
        default: begin                                       // dur_hi_en
          dur_q[event_sel_i][9:8] <= wr_data_i[1:0];
          en_q[event_sel_i] <= wr_data_i[2];
        end
      endcase
    end
  end

  // active checks
  logic [3:0] active_vec;
  logic [9:0] diff0, diff1, diff2, diff3;

  assign diff0 = epoch_i - start_q[0];
  assign diff1 = epoch_i - start_q[1];
  assign diff2 = epoch_i - start_q[2];
  assign diff3 = epoch_i - start_q[3];

  always_comb begin
    active_vec[0] = en_q[0] && (epoch_i >= start_q[0]) && (diff0 < dur_q[0]);
    active_vec[1] = en_q[1] && (epoch_i >= start_q[1]) && (diff1 < dur_q[1]);
    active_vec[2] = en_q[2] && (epoch_i >= start_q[2]) && (diff2 < dur_q[2]);
    active_vec[3] = en_q[3] && (epoch_i >= start_q[3]) && (diff3 < dur_q[3]);

    event_active_o = |active_vec;

    if (active_vec[0]) event_id_o = 2'd0;
    else if (active_vec[1]) event_id_o = 2'd1;
    else if (active_vec[2]) event_id_o = 2'd2;
    else if (active_vec[3]) event_id_o = 2'd3;
    else event_id_o = 2'd0;
  end

endmodule


////////////////////////////////////////////////////////////////////////////
// Debug shifter: parallel load, then shift out serially on tick 
// Allows serial bitstream on one pin instead of parallel on many pins,
// to save IOs and cells.
module debug_shifter_small #(
  parameter int unsigned FRAME_BITS = 8
)(
  input logic clk_i,
  input logic rst_i,
  input logic tick_i,
  input logic load_i,
  input logic [FRAME_BITS-1:0] frame_i,
  output logic serial_o
);

  logic [FRAME_BITS-1:0] shreg_q;
  logic [$clog2(FRAME_BITS+1)-1:0] cnt_q;
  logic busy_q;

  always_ff @(posedge clk_i) begin
    if (rst_i) begin
      shreg_q  <= '0;
      cnt_q  <= '0;
      busy_q <= 1'b0;
      serial_o <= 1'b0;
    end else begin
      if (load_i) begin
        shreg_q <= frame_i;
        cnt_q <= FRAME_BITS[$clog2(FRAME_BITS+1)-1:0];
        busy_q <= 1'b1;
        serial_o <= frame_i[0];
      end else if (busy_q && tick_i) begin
        serial_o <= shreg_q[0];
        shreg_q <= {1'b0, shreg_q[FRAME_BITS-1:1]};
        if (cnt_q == 1) begin
          cnt_q <= '0;
          busy_q <= 1'b0;
        end else begin
          cnt_q <= cnt_q - 1'b1;
        end
      end
    end
  end

endmodule