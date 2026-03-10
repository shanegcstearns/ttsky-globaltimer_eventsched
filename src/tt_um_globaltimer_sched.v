module tt_um_globaltimer_sched (
	ui_in,
	uo_out,
	uio_in,
	uio_out,
	uio_oe,
	ena,
	clk,
	rst_n
);
	input wire [7:0] ui_in;
	output wire [7:0] uo_out;
	input wire [7:0] uio_in;
	output wire [7:0] uio_out;
	output wire [7:0] uio_oe;
	input wire ena;
	input wire clk;
	input wire rst_n;
	wire rst_i = ~rst_n;
	wire night_en = ena & ui_in[7];
	wire wr_stb = ui_in[6];
	wire [1:0] event_sel = ui_in[5:4];
	wire [1:0] reg_sel = ui_in[3:2];
	wire [7:0] wr_data = uio_in;
	wire epoch_tick;
	wire epoch_end;
	wire [9:0] epoch_index;
	globaltimer_epoch #(
		.clk_speed_hz(10000000),
		.epoch_hz(100),
		.epoch_count_max(1000)
	) u_timer(
		.clk_i(clk),
		.rst_i(rst_i),
		.en_i(night_en),
		.epoch_tick_o(epoch_tick),
		.epoch_end_o(epoch_end),
		.epoch_index_o(epoch_index)
	);
	wire window_start_pulse;
	wire window_end_pulse;
	window_gen_pow2 #(.WINDOW_LEN_LOG2(8)) u_window(
		.clk_i(clk),
		.rst_i(rst_i),
		.en_i(night_en),
		.tick_i(epoch_tick),
		.window_start_o(window_start_pulse),
		.window_end_o(window_end_pulse)
	);
	wire event_active;
	wire [1:0] event_id;
	event_scheduler4_epoch u_sched(
		.clk_i(clk),
		.rst_i(rst_i),
		.wr_stb_i(wr_stb),
		.event_sel_i(event_sel),
		.reg_sel_i(reg_sel),
		.wr_data_i(wr_data),
		.epoch_i(epoch_index),
		.event_active_o(event_active),
		.event_id_o(event_id)
	);
	wire debug_serial;
	debug_shifter_small #(.FRAME_BITS(8)) u_dbg(
		.clk_i(clk),
		.rst_i(rst_i),
		.tick_i(epoch_tick),
		.load_i(epoch_end),
		.frame_i({event_active, event_id, window_end_pulse, epoch_end, epoch_index[2:0]}),
		.serial_o(debug_serial)
	);
	assign uo_out[0] = debug_serial;
	assign uo_out[1] = event_active;
	assign uo_out[3:2] = event_id;
	assign uo_out[4] = window_start_pulse;
	assign uo_out[5] = window_end_pulse;
	assign uo_out[6] = epoch_tick;
	assign uo_out[7] = epoch_end;
	assign uio_out = 8'h00;
	assign uio_oe = 8'h00;
endmodule
module globaltimer_epoch (
	clk_i,
	rst_i,
	en_i,
	epoch_tick_o,
	epoch_end_o,
	epoch_index_o
);
	parameter [31:0] clk_speed_hz = 10000000;
	parameter [31:0] epoch_hz = 100;
	parameter [31:0] epoch_count_max = 1000;
	input wire clk_i;
	input wire rst_i;
	input wire en_i;
	output wire epoch_tick_o;
	output reg epoch_end_o;
	output reg [9:0] epoch_index_o;
	localparam [31:0] CYCLES_PER_EPOCH = ((clk_speed_hz >= epoch_hz) && (epoch_hz >= 1) ? clk_speed_hz / epoch_hz : 1);
	localparam [31:0] DIV_W = (CYCLES_PER_EPOCH <= 1 ? 1 : $clog2(CYCLES_PER_EPOCH));
	reg [DIV_W - 1:0] div_q;
	wire tick = en_i && (div_q == (CYCLES_PER_EPOCH - 1));
	always @(posedge clk_i)
		if (rst_i) begin
			div_q <= 1'sb0;
			epoch_index_o <= 1'sb0;
			epoch_end_o <= 1'b0;
		end
		else begin
			epoch_end_o <= 1'b0;
			if (en_i) begin
				if (div_q == (CYCLES_PER_EPOCH - 1))
					div_q <= 1'sb0;
				else
					div_q <= div_q + 1'b1;
			end
			if (tick) begin
				if (epoch_index_o == (epoch_count_max - 1)) begin
					epoch_index_o <= 1'sb0;
					epoch_end_o <= 1'b1;
				end
				else
					epoch_index_o <= epoch_index_o + 10'd1;
			end
		end
	assign epoch_tick_o = tick;
endmodule
module window_gen_pow2 (
	clk_i,
	rst_i,
	en_i,
	tick_i,
	window_start_o,
	window_end_o
);
	parameter [31:0] WINDOW_LEN_LOG2 = 8;
	input wire clk_i;
	input wire rst_i;
	input wire en_i;
	input wire tick_i;
	output reg window_start_o;
	output reg window_end_o;
	reg [WINDOW_LEN_LOG2 - 1:0] wcnt_q;
	always @(posedge clk_i)
		if (rst_i) begin
			wcnt_q <= 1'sb0;
			window_start_o <= 1'b0;
			window_end_o <= 1'b0;
		end
		else begin
			window_start_o <= 1'b0;
			window_end_o <= 1'b0;
			if (en_i && tick_i) begin
				if (wcnt_q == {WINDOW_LEN_LOG2 {1'sb0}})
					window_start_o <= 1'b1;
				if (&wcnt_q)
					window_end_o <= 1'b1;
				wcnt_q <= wcnt_q + 1'b1;
			end
		end
endmodule
module event_scheduler4_epoch (
	clk_i,
	rst_i,
	wr_stb_i,
	event_sel_i,
	reg_sel_i,
	wr_data_i,
	epoch_i,
	event_active_o,
	event_id_o
);
	reg _sv2v_0;
	input wire clk_i;
	input wire rst_i;
	input wire wr_stb_i;
	input wire [1:0] event_sel_i;
	input wire [1:0] reg_sel_i;
	input wire [7:0] wr_data_i;
	input wire [9:0] epoch_i;
	output reg event_active_o;
	output reg [1:0] event_id_o;
	reg [9:0] start_q [0:3];
	reg [9:0] dur_q [0:3];
	reg en_q [0:3];
	integer k;
	always @(posedge clk_i)
		if (rst_i)
			for (k = 0; k < 4; k = k + 1)
				begin
					start_q[k] <= 10'd0;
					dur_q[k] <= 10'd0;
					en_q[k] <= 1'b0;
				end
		else if (wr_stb_i)
			(* full_case, parallel_case *)
			case (reg_sel_i)
				2'b00: start_q[event_sel_i][7:0] <= wr_data_i;
				2'b01: start_q[event_sel_i][9:8] <= wr_data_i[1:0];
				2'b10: dur_q[event_sel_i][7:0] <= wr_data_i;
				default: begin
					dur_q[event_sel_i][9:8] <= wr_data_i[1:0];
					en_q[event_sel_i] <= wr_data_i[2];
				end
			endcase
	reg [3:0] active_vec;
	wire [9:0] diff0;
	wire [9:0] diff1;
	wire [9:0] diff2;
	wire [9:0] diff3;
	assign diff0 = epoch_i - start_q[0];
	assign diff1 = epoch_i - start_q[1];
	assign diff2 = epoch_i - start_q[2];
	assign diff3 = epoch_i - start_q[3];
	always @(*) begin
		if (_sv2v_0)
			;
		active_vec[0] = (en_q[0] && (epoch_i >= start_q[0])) && (diff0 < dur_q[0]);
		active_vec[1] = (en_q[1] && (epoch_i >= start_q[1])) && (diff1 < dur_q[1]);
		active_vec[2] = (en_q[2] && (epoch_i >= start_q[2])) && (diff2 < dur_q[2]);
		active_vec[3] = (en_q[3] && (epoch_i >= start_q[3])) && (diff3 < dur_q[3]);
		event_active_o = |active_vec;
		if (active_vec[0])
			event_id_o = 2'd0;
		else if (active_vec[1])
			event_id_o = 2'd1;
		else if (active_vec[2])
			event_id_o = 2'd2;
		else if (active_vec[3])
			event_id_o = 2'd3;
		else
			event_id_o = 2'd0;
	end
	initial _sv2v_0 = 0;
endmodule
module debug_shifter_small (
	clk_i,
	rst_i,
	tick_i,
	load_i,
	frame_i,
	serial_o
);
	parameter [31:0] FRAME_BITS = 8;
	input wire clk_i;
	input wire rst_i;
	input wire tick_i;
	input wire load_i;
	input wire [FRAME_BITS - 1:0] frame_i;
	output reg serial_o;
	reg [FRAME_BITS - 1:0] shreg_q;
	reg [$clog2(FRAME_BITS + 1) - 1:0] cnt_q;
	reg busy_q;
	always @(posedge clk_i)
		if (rst_i) begin
			shreg_q <= 1'sb0;
			cnt_q <= 1'sb0;
			busy_q <= 1'b0;
			serial_o <= 1'b0;
		end
		else if (load_i) begin
			shreg_q <= frame_i;
			cnt_q <= FRAME_BITS[$clog2(FRAME_BITS + 1) - 1:0];
			busy_q <= 1'b1;
			serial_o <= frame_i[0];
		end
		else if (busy_q && tick_i) begin
			serial_o <= shreg_q[0];
			shreg_q <= {1'b0, shreg_q[FRAME_BITS - 1:1]};
			if (cnt_q == 1) begin
				cnt_q <= 1'sb0;
				busy_q <= 1'b0;
			end
			else
				cnt_q <= cnt_q - 1'b1;
		end
endmodule