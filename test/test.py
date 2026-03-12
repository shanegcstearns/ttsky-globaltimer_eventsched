import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles


def top_epoch_tick(dut) -> int:
    return (int(dut.uo_out.value) >> 0) & 1


def top_epoch_end(dut) -> int:
    return (int(dut.uo_out.value) >> 1) & 1


def top_epoch_index(dut) -> int:
    uo = int(dut.uo_out.value)
    uio = int(dut.uio_out.value)
    low6 = (uo >> 2) & 0x3F
    high4 = uio & 0xF
    return low6 | (high4 << 6)


@cocotb.test()
async def test_project(dut):
    dut._log.info("Start global epoch timer test")

    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0

    # Reset
    dut._log.info("Reset")
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)

    # Fixed IO checks
    assert ((int(dut.uio_out.value) >> 4) & 0xF) == 0
    assert (int(dut.uio_oe.value) & 0xF) == 0xF
    assert ((int(dut.uio_oe.value) >> 4) & 0xF) == 0

    # With ui_in[7]=0, timer should not advance
    idx0 = top_epoch_index(dut)
    await ClockCycles(dut.clk, 100)
    assert top_epoch_index(dut) == idx0
    assert top_epoch_tick(dut) == 0
    assert top_epoch_end(dut) == 0

    # Enable timer
    dut.ui_in.value = 0x80

    # Wait for first epoch tick
    saw_tick = False
    for cyc in range(100500):
        await ClockCycles(dut.clk, 1)
        if top_epoch_tick(dut):
            dut._log.info(f"First tick seen at cycle offset {cyc}")
            saw_tick = True
            break

    assert saw_tick, "Did not see first epoch tick"
    assert top_epoch_index(dut) == 1, "epoch index should be 1 on first tick"
    assert top_epoch_end(dut) == 0, "epoch_end should be low on first tick"

    # Tick should be one cycle wide
    await ClockCycles(dut.clk, 1)
    assert top_epoch_tick(dut) == 0, "epoch tick should be one cycle wide"

    # Wait for second epoch tick
    saw_tick = False
    for cyc in range(100500):
        await ClockCycles(dut.clk, 1)
        if top_epoch_tick(dut):
            dut._log.info(f"Second tick seen at cycle offset {cyc}")
            saw_tick = True
            break

    assert saw_tick, "Did not see second epoch tick"
    assert top_epoch_index(dut) == 2, "epoch index should be 2 on second tick"
    assert top_epoch_end(dut) == 0, "epoch_end should still be low"

    # Sanity check while running
    for _ in range(20):
        await ClockCycles(dut.clk, 1)
        assert top_epoch_tick(dut) in (0, 1)
        assert top_epoch_end(dut) in (0, 1)
        assert 0 <= top_epoch_index(dut) <= 1023