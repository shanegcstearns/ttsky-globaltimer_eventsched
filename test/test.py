import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles, Timer

def has(dut, name: str) -> bool:
    return hasattr(dut, name)

def u(sig) -> int:
    return int(sig.value)

async def start_clock(dut, clk, period_ns=10):
    cocotb.start_soon(Clock(clk, period_ns, unit="ns").start())
    await Timer(period_ns * 2, unit="ns")

async def reset_top(dut, cycles=3):
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, cycles)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

async def reset_sync(dut, clk, rst, cycles=3):
    rst.value = 1
    await ClockCycles(clk, cycles)
    rst.value = 0
    await RisingEdge(clk)

async def top_write(dut, night_en: int, event_sel: int, reg_sel: int, data: int):
    dut.uio_in.value = data & 0xFF
    ui = ((night_en & 1) << 7) | (1 << 6) | ((event_sel & 3) << 4) | ((reg_sel & 3) << 2)
    dut.ui_in.value = ui
    await RisingEdge(dut.clk)
    ui = ((night_en & 1) << 7) | (0 << 6) | ((event_sel & 3) << 4) | ((reg_sel & 3) << 2)
    dut.ui_in.value = ui
    await RisingEdge(dut.clk)

def looks_like_globaltimer(dut) -> bool:
    need = ["clk_i", "rst_i", "en_i",
            "time_in_night_seconds_o", "epoch_index_o", "epoch_end_o", "epoch_tick_o"]
    return all(has(dut, n) for n in need)

def looks_like_window_gen(dut) -> bool:
    need = ["clk_i", "rst_i", "en_i", "sample_tick_i", "window_start_o", "window_end_o"]
    return all(has(dut, n) for n in need)

def looks_like_event_scheduler4(dut) -> bool:
    need = ["clk_i", "rst_i",
            "wr_stb_i", "event_sel_i", "reg_sel_i", "wr_data_i",
            "time_sec_i", "event_active_o", "event_id_o"]
    return all(has(dut, n) for n in need)

def looks_like_debug_shifter(dut) -> bool:
    need = ["clk_i", "rst_i", "tick_i", "load_i", "frame_i", "serial_o"]
    return all(has(dut, n) for n in need)

def looks_like_top(dut) -> bool:
    need = ["ui_in", "uo_out", "uio_in", "uio_out", "uio_oe", "ena", "clk", "rst_n"]
    return all(has(dut, n) for n in need)


# Verifies epoch tick generation and enable behavior of the global timer
@cocotb.test()
async def test_globaltimer_unit(dut):
    if not looks_like_globaltimer(dut):
        return 

    await start_clock(dut, dut.clk_i, 10)
    await reset_sync(dut, dut.clk_i, dut.rst_i, 3)

    dut.en_i.value = 0
    t0 = u(dut.time_in_night_seconds_o)
    e0 = u(dut.epoch_index_o)
    await ClockCycles(dut.clk_i, 50)
    assert u(dut.time_in_night_seconds_o) == t0
    assert u(dut.epoch_index_o) == e0

    dut.en_i.value = 1
    saw_tick = False
    for _ in range(5000):
        await RisingEdge(dut.clk_i)
        if u(dut.epoch_tick_o):
            saw_tick = True
            await RisingEdge(dut.clk_i)
            assert u(dut.epoch_tick_o) == 0
            break
    assert saw_tick


# Verifies window start/end pulses based on periodic sample ticks
@cocotb.test()
async def test_window_gen_unit(dut):
    if not looks_like_window_gen(dut):
        return

    await start_clock(dut, dut.clk_i, 10)
    await reset_sync(dut, dut.clk_i, dut.rst_i, 2)

    dut.en_i.value = 1
    dut.sample_tick_i.value = 0

    starts = 0
    ends = 0
    for _ in range(64):
        dut.sample_tick_i.value = 1
        await RisingEdge(dut.clk_i)
        starts += u(dut.window_start_o)
        ends += u(dut.window_end_o)
        dut.sample_tick_i.value = 0
        await RisingEdge(dut.clk_i)

    assert starts >= 1
    assert ends >= 1


# Verifies event programming, activation timing, and priority logic
@cocotb.test()
async def test_event_scheduler4_unit(dut):
    if not looks_like_event_scheduler4(dut):
        return

    await start_clock(dut, dut.clk_i, 10)
    await reset_sync(dut, dut.clk_i, dut.rst_i, 2)

    async def write(event_sel, reg_sel, data):
        dut.event_sel_i.value = event_sel
        dut.reg_sel_i.value = reg_sel
        dut.wr_data_i.value = data & 0xFF
        dut.wr_stb_i.value = 1
        await RisingEdge(dut.clk_i)
        dut.wr_stb_i.value = 0
        await RisingEdge(dut.clk_i)

    await write(1, 0b00, 5)
    await write(1, 0b01, 0)
    await write(1, 0b10, 3)
    await write(1, 0b11, 1)

    for t in range(0, 10):
        dut.time_sec_i.value = t
        await RisingEdge(dut.clk_i)
        active = u(dut.event_active_o)
        eid = u(dut.event_id_o)
        if 5 <= t <= 7:
            assert active == 1
            assert eid == 1
        else:
            assert active == 0

    await write(0, 0b00, 6)
    await write(0, 0b01, 0)
    await write(0, 0b10, 5)
    await write(0, 0b11, 1)

    for t in (6, 7):
        dut.time_sec_i.value = t
        await RisingEdge(dut.clk_i)
        assert u(dut.event_active_o) == 1
        assert u(dut.event_id_o) == 0


# Verifies debug frame loading and serial bit shifting behavior
@cocotb.test()
async def test_debug_shifter_unit(dut):
    if not looks_like_debug_shifter(dut):
        return

    await start_clock(dut, dut.clk_i, 10)
    await reset_sync(dut, dut.clk_i, dut.rst_i, 2)

    dut.tick_i.value = 0
    dut.load_i.value = 0

    frame = 0b10110011
    dut.frame_i.value = frame

    dut.load_i.value = 1
    await RisingEdge(dut.clk_i)
    dut.load_i.value = 0
    await RisingEdge(dut.clk_i)

    expected = [(frame >> i) & 1 for i in range(8)]
    for i, exp in enumerate(expected):
        dut.tick_i.value = 1
        await RisingEdge(dut.clk_i)
        got = u(dut.serial_o)
        assert got == exp
        dut.tick_i.value = 0
        await RisingEdge(dut.clk_i)


# Verifies top-level programming interface and event activation behavior
@cocotb.test()
async def test_top_level_programming_scheduler(dut):

    need = ["ui_in", "uo_out", "uio_in", "uio_out", "uio_oe", "ena", "clk", "rst_n"]
    if not all(hasattr(dut, n) for n in need):
        return

    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await Timer(50, unit="ns")

    dut.ena.value = 1
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 3)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    async def write(event_sel, reg_sel, data, night_en=0):
        dut.uio_in.value = data & 0xFF
        ui = ((night_en & 1) << 7) | (1 << 6) | ((event_sel & 3) << 4) | ((reg_sel & 3) << 2)
        dut.ui_in.value = ui
        await RisingEdge(dut.clk)
        ui = ((night_en & 1) << 7) | (0 << 6) | ((event_sel & 3) << 4) | ((reg_sel & 3) << 2)
        dut.ui_in.value = ui
        await RisingEdge(dut.clk)

    await write(1, 0b00, 5)
    await write(1, 0b01, 0)
    await write(1, 0b10, 3)
    await write(1, 0b11, 0b00000100)

    dut.ui_in.value = (1 << 7)

    # if not (hasattr(dut, "u_timer") and hasattr(dut.u_timer, "epoch_index_o")):
    #     raise AssertionError("Can't access dut.u_timer.epoch_index_o")

    def get_event_active_id():
        out = int(dut.uo_out.value)
        event_active = (out >> 1) & 1
        event_id = (out >> 2) & 0x3
        return event_active, event_id

    for epoch in range(0, 12):
        # dut.u_timer.epoch_index_o.value = epoch
        await RisingEdge(dut.clk)

        active, eid = get_event_active_id()
        if 5 <= epoch <= 7:
            assert active == 1
            assert eid == 1
        else:
            assert active == 0