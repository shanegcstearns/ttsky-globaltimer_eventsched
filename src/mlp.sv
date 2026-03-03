module mlp (
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: Input path
    output wire [7:0] uio_out,  // IOs: Output path
    output wire [7:0] uio_oe,   // IOs: Enable path (active high: 0=input, 1=output)
    input  wire       ena,      // always 1 when the design is powered, so you can ignore it
    input  wire       clk,      // clock
    input  wire       rst_n     // reset_n - low to reset
);

    logic [3:0] addr_sel;
    logic wr_pending;
    logic [3:0] wr_addr;

    logic signed [7:0] x0, x1, x2, x3;

    logic [0:0] busy, done, pred;
    logic signed [15:0] logit0, logit1;

    // weights and biases random, hardcoded for now
    logic signed [15:0] B0  = -16'sd5;
    logic signed [15:0] B1  =  16'sd1;

    logic signed [7:0]  W00 =  8'sd3;
    logic signed [7:0]  W01 = -8'sd2;
    logic signed [7:0]  W02 =  8'sd1;
    logic signed [7:0]  W03 =  8'sd4;

    logic signed [7:0]  W10 = -8'sd1;
    logic signed [7:0]  W11 =  8'sd3;
    logic signed [7:0]  W12 =  8'sd2;
    logic signed [7:0]  W13 = -8'sd2;


    // states
    logic [2:0] st;
    logic [2:0] ST_IDLE = 3'd0;
    logic [2:0] ST_O0_B = 3'd1;
    logic [2:0] ST_O0_0 = 3'd2;
    logic [2:0] ST_O0_1 = 3'd3;
    logic [2:0] ST_O0_2 = 3'd4;
    logic [2:0] ST_O0_3 = 3'd5;
    logic [2:0] ST_O1_B = 3'd6;

    logic out_sel; // 0 if computing logit0, 1 if computing logit1

    logic signed [23:0] acc;
    logic signed [7:0]  cur_x;
    logic signed [7:0]  cur_w;

    wire cmd_cycle, cmd_wr, cmd_start;
    wire [3:0] cmd_addr;

    assign {cmd_cycle, cmd_addr, cmd_wr, cmd_start} = ui_in[7:1];

    logic [7:0] rdata;

    always_comb begin
        rdata = 8'h00;
        case (addr_sel)
            4'h0: rdata = x0;
            4'h1: rdata = x1;
            4'h2: rdata = x2;
            4'h3: rdata = x3;

            4'h5: rdata = {5'b00000, pred, done, busy};

            4'h6: rdata = logit0[7:0];
            4'h7: rdata = logit0[15:8];
            4'h8: rdata = logit1[7:0];
            4'h9: rdata = logit1[15:8];

            4'hF: rdata = 8'hA1;
            default: rdata = 8'h00;
        endcase
    end

    assign uo_out = rdata;

    logic rst;
    assign rst = ~rst_n;

    always_ff @(posedge clk) begin
        if (rst) begin
            addr_sel   <= 4'h0;
            wr_pending <= 1'b0;
            wr_addr    <= 4'h0;

            x0 <= 8'sd0;
            x1 <= 8'sd0;
            x2 <= 8'sd0;
            x3 <= 8'sd0;

            busy   <= 1'b0;
            done   <= 1'b0;
            pred   <= 1'b0;
            logit0 <= 16'sd0;
            logit1 <= 16'sd0;

            st <= ST_IDLE;
            out_sel <= 1'b0;
            acc <= 24'sd0;
            cur_x <= 8'sd0;
            cur_w <= 8'sd0;
            end else begin
            if (cmd_cycle) begin
                addr_sel <= cmd_addr;

                if (cmd_wr) begin
                    wr_pending <= 1'b1;
                    wr_addr    <= cmd_addr;
                end

                if (cmd_start && !busy) begin
                    busy <= 1'b1;
                    done <= 1'b0;
                    out_sel <= 1'b0;
                    st <= ST_O0_B;
                end
            end else begin
                if (wr_pending) begin
                    wr_pending <= 1'b0;
                    case (wr_addr)
                        4'h0: x0 <= ui_in;
                        4'h1: x1 <= ui_in;
                        4'h2: x2 <= ui_in;
                        4'h3: x3 <= ui_in;
                        default: begin end
                    endcase
                end
            end

            //FSM
            if (busy) begin
                case (st)
                    ST_O0_B: begin
                        if (!out_sel) acc <= {{8{B0[15]}}, B0};
                        else          acc <= {{8{B1[15]}}, B1};
                        st <= ST_O0_0;
                    end

                    ST_O0_0: begin
                        cur_x <= x0;
                        if (!out_sel) cur_w <= W00;
                        else          cur_w <= W10;
                        acc <= acc + ({{8{cur_x[7]}}, cur_x} * {{8{cur_w[7]}}, cur_w});
                        st <= ST_O0_1;
                    end

                    ST_O0_1: begin
                        cur_x <= x1;
                        if (!out_sel) cur_w <= W01;
                        else          cur_w <= W11;
                        acc <= acc + ({{8{cur_x[7]}}, cur_x} * {{8{cur_w[7]}}, cur_w});
                        st <= ST_O0_2;
                    end

                    ST_O0_2: begin
                        cur_x <= x2;
                        if (!out_sel) cur_w <= W02;
                        else          cur_w <= W12;
                        acc <= acc + ({{8{cur_x[7]}}, cur_x} * {{8{cur_w[7]}}, cur_w});
                        st <= ST_O0_3;
                    end

                    ST_O0_3: begin
                        cur_x <= x3;
                        if (!out_sel) cur_w <= W03;
                        else          cur_w <= W13;
                        acc <= acc + ({{8{cur_x[7]}}, cur_x} * {{8{cur_w[7]}}, cur_w});

                        if (!out_sel) begin
                            out_sel <= 1'b1;
                            st <= ST_O1_B;
                        end else begin
                            st <= ST_IDLE;
                        end
                    end

                    ST_O1_B: begin
                        logit0 <= acc[15:0];
                        acc <= {{8{B1[15]}}, B1};
                        st <= ST_O0_0;
                    end

                    ST_IDLE: begin
                        logit1 <= acc[15:0];
                        pred <= (acc[15:0] > logit0) ? 1'b1 : 1'b0;

                        busy <= 1'b0;
                        done <= 1'b1;
                        st <= ST_IDLE;
                    end

                    default: st <= ST_IDLE;
                endcase
            end
        end
    end

    assign uio_out = 8'b0;
    assign uio_oe  = 8'b0;

endmodule