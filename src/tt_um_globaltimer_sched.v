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

    input  wire [7:0] ui_in;
    output wire [7:0] uo_out;
    input  wire [7:0] uio_in;
    output wire [7:0] uio_out;
    output wire [7:0] uio_oe;
    input  wire       ena;
    input  wire       clk;
    input  wire       rst_n;

    // Simple global epoch timer only
    // ui_in[7] = enable
    // uo_out[0] = epoch tick pulse
    // uo_out[1] = epoch end pulse
    // uo_out[7:2] = epoch_index[5:0]
    // uio_out[3:0] = epoch_index[9:6]

    localparam integer CLK_SPEED_HZ    = 10000000;
    localparam integer EPOCH_HZ        = 100;
    localparam integer EPOCH_COUNT_MAX = 1000;
    localparam integer CYCLES_PER_EPOCH = CLK_SPEED_HZ / EPOCH_HZ;

    function integer clog2;
        input integer value;
        integer i;
        begin
            value = value - 1;
            for (i = 0; value > 0; i = i + 1)
                value = value >> 1;
            clog2 = i;
        end
    endfunction

    localparam integer DIV_W = (CYCLES_PER_EPOCH <= 1) ? 1 : clog2(CYCLES_PER_EPOCH);

    wire night_en;
    reg  [DIV_W-1:0] div_q;
    reg  [9:0] epoch_index_q;
    reg  epoch_tick_q;
    reg  epoch_end_q;

    assign night_en = ena & ui_in[7];

    always @(posedge clk) begin
        if (!rst_n) begin
            div_q         <= {DIV_W{1'b0}};
            epoch_index_q <= 10'd0;
            epoch_tick_q  <= 1'b0;
            epoch_end_q   <= 1'b0;
        end else begin
            epoch_tick_q <= 1'b0;
            epoch_end_q  <= 1'b0;

            if (night_en) begin
                if (div_q == CYCLES_PER_EPOCH - 1) begin
                    div_q        <= {DIV_W{1'b0}};
                    epoch_tick_q <= 1'b1;

                    if (epoch_index_q == EPOCH_COUNT_MAX - 1) begin
                        epoch_index_q <= 10'd0;
                        epoch_end_q   <= 1'b1;
                    end else begin
                        epoch_index_q <= epoch_index_q + 10'd1;
                    end
                end else begin
                    div_q <= div_q + {{(DIV_W-1){1'b0}}, 1'b1};
                end
            end
        end
    end

    assign uo_out[0] = epoch_tick_q;
    assign uo_out[1] = epoch_end_q;
    assign uo_out[7:2] = epoch_index_q[5:0];

    assign uio_out[3:0] = epoch_index_q[9:6];
    assign uio_out[7:4] = 4'b0000;

    assign uio_oe[3:0] = 4'b1111;
    assign uio_oe[7:4] = 4'b0000;

    wire _unused_ok = &{1'b0, uio_in, ui_in[6:0]};

endmodule
