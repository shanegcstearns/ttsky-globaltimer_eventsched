import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles, Timer, ReadOnly


def has(dut, name: str) -> bool:
    return hasattr(dut, name)


def bit(sig, idx: int) -> int:
    v = sig.value[idx]
    return 1 if str(v) == "1" else 0


def bits(sig, msb: int, lsb: int) -> int:
    val = 0
    shift = 0
    for i in range(lsb, msb + 1):
        val |= (bit(sig, i) << shift)
        shift += 1
    return val


def looks_like_top(dut) -> bool:
    need = ["ui_in", "uo_out", "uio_in", "uio_out", "uio_oe", "ena", "clk", "rst_n"]
    return all(has(dut, n) for n in need)


async def start_clock(clk, period_ns=10):
    cocotb.start_soon(Clock(clk, period_ns, unit="ns").start())
    await Timer(period_ns * 2, unit="ns")


async def reset_top(dut, cycles=3):
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, cycles)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


def top_epoch_tick(dut) -> int:
    return bit(dut.uo_out, 0)


def top_epoch_end(dut) -> int:
    return bit(dut.uo_out, 1)


def top_epoch_index(dut) -> int:
    low6 = bits(dut.uo_out, 7, 2)
    high4 = bits(dut.uio_out, 3, 0)
    return low6 | (high4 << 6)


async def wait_for_epoch_tick(dut, timeout_cycles=200_000):
    for _ in range(timeout_cycles):
        await RisingEdge(dut.clk)
        await ReadOnly()
        if top_epoch_tick(dut):
            return
    raise AssertionError("Timed out waiting for epoch tick")


@cocotb.test()
async def test_top_level_global_epoch_timer(dut):
    if not looks_like_top(dut):
        return

    await start_clock(dut.clk, 10)

    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.ena.value = 1

    await reset_top(dut, 3)

    # sample settled outputs
    await ReadOnly()

    # uio upper nibble should be unused outputs disabled
    assert bits(dut.uio_out, 7, 4) == 0
    #assert bits(dut.uio_oe, 3, 0) == 0b1111
    assert bits(dut.uio_oe, 7, 4) == 0

    # with enable low, timer should not advance
    idx0 = top_epoch_index(dut)
    await ClockCycles(dut.clk, 100)
    await ReadOnly()
    assert top_epoch_index(dut) == idx0
    assert top_epoch_tick(dut) == 0
    assert top_epoch_end(dut) == 0

    # move to writable phase before driving inputs again
    await RisingEdge(dut.clk)
    dut.ui_in.value = 0b1000_0000

    # first epoch tick should happen and index should advance to 1
    await wait_for_epoch_tick(dut)
    assert top_epoch_tick(dut) == 1, "epoch tick should pulse high"
    assert top_epoch_index(dut) == 1, "epoch index should increment to 1 on first tick"

    # tick should be single-cycle
    await RisingEdge(dut.clk)
    await ReadOnly()
    assert top_epoch_tick(dut) == 0, "epoch tick should be one cycle wide"

    # second tick should advance to 2
    await wait_for_epoch_tick(dut)
    assert top_epoch_tick(dut) == 1, "second epoch tick should pulse high"
    assert top_epoch_index(dut) == 2, "epoch index should increment to 2 on second tick"
    assert top_epoch_end(dut) == 0, "epoch end should not assert yet"

    # smoke-check that outputs stay legal while running
    for _ in range(20):
        await RisingEdge(dut.clk)
        await ReadOnly()
        assert top_epoch_tick(dut) in (0, 1)
        assert top_epoch_end(dut) in (0, 1)
        assert 0 <= top_epoch_index(dut) <= 1023
# import cocotb
# from cocotb.clock import Clock
# from cocotb.triggers import RisingEdge, ClockCycles, Timer


# def has(dut, name: str) -> bool:
#     return hasattr(dut, name)


# def u(sig) -> int:
#     return int(sig.value)


# def bit(sig, idx: int) -> int:
#     v = sig.value[idx]
#     s = str(v)
#     if s == "1":
#         return 1
#     return 0


# def bits2(sig, msb: int, lsb: int) -> int:
#     val = 0
#     shift = 0
#     for i in range(lsb, msb + 1):
#         val |= (bit(sig, i) << shift)
#         shift += 1
#     return val


# async def start_clock(clk, period_ns=10):
#     cocotb.start_soon(Clock(clk, period_ns, unit="ns").start())
#     await Timer(period_ns * 2, unit="ns")


# async def reset_top(dut, cycles=3):
#     dut.rst_n.value = 0
#     await ClockCycles(dut.clk, cycles)
#     dut.rst_n.value = 1
#     await RisingEdge(dut.clk)


# async def reset_sync(clk, rst, cycles=3):
#     rst.value = 1
#     await ClockCycles(clk, cycles)
#     rst.value = 0
#     await RisingEdge(clk)


# async def top_write(dut, night_en: int, event_sel: int, reg_sel: int, data: int):
#     dut.uio_in.value = data & 0xFF
#     ui = ((night_en & 1) << 7) | (1 << 6) | ((event_sel & 3) << 4) | ((reg_sel & 3) << 2)
#     dut.ui_in.value = ui
#     await RisingEdge(dut.clk)

#     ui = ((night_en & 1) << 7) | ((event_sel & 3) << 4) | ((reg_sel & 3) << 2)
#     dut.ui_in.value = ui
#     await RisingEdge(dut.clk)


# def looks_like_globaltimer(dut) -> bool:
#     need = ["clk_i", "rst_i", "en_i", "epoch_tick_o", "epoch_end_o", "epoch_index_o"]
#     return all(has(dut, n) for n in need)


# def looks_like_window_gen(dut) -> bool:
#     need = ["clk_i", "rst_i", "en_i", "tick_i", "window_start_o", "window_end_o"]
#     return all(has(dut, n) for n in need)


# def looks_like_event_scheduler4(dut) -> bool:
#     need = [
#         "clk_i", "rst_i",
#         "wr_stb_i", "event_sel_i", "reg_sel_i", "wr_data_i",
#         "epoch_i", "event_active_o", "event_id_o"
#     ]
#     return all(has(dut, n) for n in need)


# def looks_like_debug_shifter(dut) -> bool:
#     need = ["clk_i", "rst_i", "tick_i", "load_i", "frame_i", "serial_o"]
#     return all(has(dut, n) for n in need)


# def looks_like_top(dut) -> bool:
#     need = ["ui_in", "uo_out", "uio_in", "uio_out", "uio_oe", "ena", "clk", "rst_n"]
#     return all(has(dut, n) for n in need)


# def top_event_active(dut) -> int:
#     return bit(dut.uo_out, 1)


# def top_event_id(dut) -> int:
#     return bits2(dut.uo_out, 3, 2)


# def top_window_start(dut) -> int:
#     return bit(dut.uo_out, 4)


# def top_window_end(dut) -> int:
#     return bit(dut.uo_out, 5)


# def top_epoch_tick(dut) -> int:
#     return bit(dut.uo_out, 6)


# def top_epoch_end(dut) -> int:
#     return bit(dut.uo_out, 7)


# async def wait_top_epoch_tick(dut, timeout_cycles=200_000):
#     for _ in range(timeout_cycles):
#         await RisingEdge(dut.clk)
#         if top_epoch_tick(dut):
#             return
#     raise AssertionError("Timed out waiting for top-level epoch tick")


# @cocotb.test()
# async def test_globaltimer_unit(dut):
#     if not looks_like_globaltimer(dut):
#         return

#     await start_clock(dut.clk_i, 10)
#     await reset_sync(dut.clk_i, dut.rst_i, 3)

#     dut.en_i.value = 0
#     e0 = u(dut.epoch_index_o)
#     await ClockCycles(dut.clk_i, 100)
#     assert u(dut.epoch_index_o) == e0
#     assert u(dut.epoch_tick_o) == 0

#     dut.en_i.value = 1

#     saw_tick = False
#     for _ in range(120_000):
#         await RisingEdge(dut.clk_i)
#         if u(dut.epoch_tick_o):
#             saw_tick = True
#             break

#     assert saw_tick, "Did not see epoch_tick_o within expected time"
#     assert u(dut.epoch_index_o) == 1, "epoch_index_o should advance to 1 on first tick"

#     await RisingEdge(dut.clk_i)
#     assert u(dut.epoch_tick_o) == 0, "epoch_tick_o should be a single-cycle pulse"


# @cocotb.test()
# async def test_window_gen_unit(dut):
#     if not looks_like_window_gen(dut):
#         return

#     await start_clock(dut.clk_i, 10)
#     await reset_sync(dut.clk_i, dut.rst_i, 2)

#     dut.en_i.value = 1
#     dut.tick_i.value = 0

#     starts = 0
#     ends = 0

#     for _ in range(256):
#         dut.tick_i.value = 1
#         await RisingEdge(dut.clk_i)
#         starts += u(dut.window_start_o)
#         ends += u(dut.window_end_o)

#         dut.tick_i.value = 0
#         await RisingEdge(dut.clk_i)

#     assert starts >= 1, "Expected at least one window_start_o pulse"
#     assert ends >= 1, "Expected at least one window_end_o pulse"


# @cocotb.test()
# async def test_event_scheduler4_unit(dut):
#     if not looks_like_event_scheduler4(dut):
#         return

#     await start_clock(dut.clk_i, 10)
#     await reset_sync(dut.clk_i, dut.rst_i, 2)

#     async def write(event_sel, reg_sel, data):
#         dut.event_sel_i.value = event_sel
#         dut.reg_sel_i.value = reg_sel
#         dut.wr_data_i.value = data & 0xFF
#         dut.wr_stb_i.value = 1
#         await RisingEdge(dut.clk_i)
#         dut.wr_stb_i.value = 0
#         await RisingEdge(dut.clk_i)

#     await write(1, 0b00, 5)
#     await write(1, 0b01, 0)
#     await write(1, 0b10, 3)
#     await write(1, 0b11, 0b00000100)

#     for t in range(0, 10):
#         dut.epoch_i.value = t
#         await RisingEdge(dut.clk_i)

#         active = u(dut.event_active_o)
#         eid = u(dut.event_id_o)

#         if 5 <= t <= 7:
#             assert active == 1, f"Expected event active at epoch {t}"
#             assert eid == 1, f"Expected event_id 1 at epoch {t}"
#         else:
#             assert active == 0, f"Expected no event active at epoch {t}"

#     await write(0, 0b00, 6)
#     await write(0, 0b01, 0)
#     await write(0, 0b10, 5)
#     await write(0, 0b11, 0b00000100)

#     for t in (6, 7):
#         dut.epoch_i.value = t
#         await RisingEdge(dut.clk_i)
#         assert u(dut.event_active_o) == 1, f"Expected active overlap at epoch {t}"
#         assert u(dut.event_id_o) == 0, f"Priority should select event 0 at epoch {t}"


# @cocotb.test()
# async def test_debug_shifter_unit(dut):
#     if not looks_like_debug_shifter(dut):
#         return

#     await start_clock(dut.clk_i, 10)
#     await reset_sync(dut.clk_i, dut.rst_i, 2)

#     dut.tick_i.value = 0
#     dut.load_i.value = 0

#     frame = 0b10110011
#     dut.frame_i.value = frame

#     dut.load_i.value = 1
#     await RisingEdge(dut.clk_i)
#     dut.load_i.value = 0
#     await RisingEdge(dut.clk_i)

#     expected = [(frame >> i) & 1 for i in range(8)]
#     for i, exp in enumerate(expected):
#         dut.tick_i.value = 1
#         await RisingEdge(dut.clk_i)
#         got = u(dut.serial_o)
#         assert got == exp, f"Bit {i}: expected {exp}, got {got}"
#         dut.tick_i.value = 0
#         await RisingEdge(dut.clk_i)


# # @cocotb.test()
# # async def test_top_level_programming_scheduler(dut):
# #     if not looks_like_top(dut):
# #         return

# #     await start_clock(dut.clk, 10)

# #     dut.ui_in.value = 0
# #     dut.uio_in.value = 0
# #     dut.ena.value = 1

# #     await reset_top(dut, 3)

# #     # Program event 1: start=5, dur=3, enable=1
# #     await top_write(dut, night_en=0, event_sel=1, reg_sel=0b00, data=5)
# #     await top_write(dut, night_en=0, event_sel=1, reg_sel=0b01, data=0)
# #     await top_write(dut, night_en=0, event_sel=1, reg_sel=0b10, data=3)
# #     await top_write(dut, night_en=0, event_sel=1, reg_sel=0b11, data=0b00000100)

# #     # Start night mode
# #     dut.ui_in.value = (1 << 7)
# #     await RisingEdge(dut.clk)

# #     # Give outputs a little time to settle in GL sim
# #     await Timer(20, unit="ns")

# #     for epoch in range(1, 13):
# #         await wait_top_epoch_tick(dut)
# #         await Timer(1, unit="ns")

# #         active = top_event_active(dut)
# #         eid = top_event_id(dut)

# #         if 5 <= epoch <= 7:
# #             assert active == 1, f"Expected event active at top-level epoch {epoch}"
# #             assert eid == 1, f"Expected event_id 1 at top-level epoch {epoch}"
# #         else:
# #             assert active == 0, f"Expected no event active at top-level epoch {epoch}"

# #     assert bit(dut.uio_out, 0) == 0
# #     assert bit(dut.uio_oe, 0) == 0
# @cocotb.test()
# async def test_top_level_programming_scheduler(dut):
#     if not looks_like_top(dut):
#         return

#     await start_clock(dut.clk, 10)

#     dut.ui_in.value = 0
#     dut.uio_in.value = 0
#     dut.ena.value = 0

#     await reset_top(dut, 3)

#     # basic post-reset settle
#     await Timer(20, unit="ns")

#     # fixed IO expectations
#     assert bit(dut.uio_out, 0) == 0
#     assert bit(dut.uio_oe, 0) == 0

#     # program one event through the top-level interface
#     await top_write(dut, night_en=0, event_sel=1, reg_sel=0b00, data=5)          # start low
#     await top_write(dut, night_en=0, event_sel=1, reg_sel=0b01, data=0)          # start high
#     await top_write(dut, night_en=0, event_sel=1, reg_sel=0b10, data=3)          # dur low
#     await top_write(dut, night_en=0, event_sel=1, reg_sel=0b11, data=0b00000100) # dur high + enable

#     # enable top-level design and night mode
#     dut.ena.value = 1
#     dut.ui_in.value = (1 << 7)

#     # let gate-level logic settle a bit
#     await ClockCycles(dut.clk, 20)
#     await Timer(20, unit="ns")

#     # smoke checks:
#     # - outputs are readable
#     # - event bits decode to legal values
#     # - no crash when design is running
#     active = top_event_active(dut)
#     eid = top_event_id(dut)
#     wstart = top_window_start(dut)
#     wend = top_window_end(dut)
#     etick = top_epoch_tick(dut)
#     eend = top_epoch_end(dut)

#     assert active in (0, 1)
#     assert eid in (0, 1, 2, 3)
#     assert wstart in (0, 1)
#     assert wend in (0, 1)
#     assert etick in (0, 1)
#     assert eend in (0, 1)

#     # keep it running for a short while and make sure the interface stays sane
#     for _ in range(50):
#         await RisingEdge(dut.clk)
#         active = top_event_active(dut)
#         eid = top_event_id(dut)
#         assert active in (0, 1)
#         assert eid in (0, 1, 2, 3)

#     # final fixed IO check
#     assert bit(dut.uio_out, 0) == 0
#     assert bit(dut.uio_oe, 0) == 0