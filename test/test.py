# SPDX-FileCopyrightText: © 2024 Tiny Tapeout
# SPDX-License-Identifier: Apache-2.0

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles


def bit_is_1(sig, idx: int) -> bool:
    return str(sig.value[idx]) == "1"


def bit_is_0(sig, idx: int) -> bool:
    return str(sig.value[idx]) == "0"


def bit_known(sig, idx: int) -> bool:
    s = str(sig.value[idx])
    return s in ("0", "1")


def get_epoch_tick(dut) -> int:
    return 1 if bit_is_1(dut.uo_out, 0) else 0


def get_epoch_end(dut) -> int:
    return 1 if bit_is_1(dut.uo_out, 1) else 0


def get_epoch_index(dut):
    bits = []

    # low 6 bits from uo_out[7:2]
    for i in range(2, 8):
        s = str(dut.uo_out.value[i])
        if s not in ("0", "1"):
            return None
        bits.append(int(s))

    # high 4 bits from uio_out[3:0]
    for i in range(0, 4):
        s = str(dut.uio_out.value[i])
        if s not in ("0", "1"):
            return None
        bits.append(int(s))

    val = 0
    for i, b in enumerate(bits):
        val |= (b << i)
    return val


@cocotb.test()
async def test_project(dut):
    dut._log.info("Start global epoch timer test")

    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Tie off power pins in GL sim if present
    if hasattr(dut, "VPWR"):
        dut.VPWR.value = 1
    if hasattr(dut, "VGND"):
        dut.VGND.value = 0
    if hasattr(dut, "VAPWR"):
        dut.VAPWR.value = 1
    if hasattr(dut, "VAGND"):
        dut.VAGND.value = 0

    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0

    # Reset
    dut._log.info("Reset")
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)

    # Only check bits we actually care about, and only if known
    for i in range(4):
        assert bit_known(dut.uio_oe, i), f"uio_oe[{i}] is not known after reset"
    for i in range(4, 8):
        assert bit_known(dut.uio_oe, i), f"uio_oe[{i}] is not known after reset"

    assert bit_is_1(dut.uio_oe, 0)
    assert bit_is_1(dut.uio_oe, 1)
    assert bit_is_1(dut.uio_oe, 2)
    assert bit_is_1(dut.uio_oe, 3)

    assert bit_is_0(dut.uio_oe, 4)
    assert bit_is_0(dut.uio_oe, 5)
    assert bit_is_0(dut.uio_oe, 6)
    assert bit_is_0(dut.uio_oe, 7)

    # With enable low, timer should not advance
    idx0 = get_epoch_index(dut)
    assert idx0 is not None, "epoch index unknown after reset"

    await ClockCycles(dut.clk, 100)

    idx1 = get_epoch_index(dut)
    assert idx1 is not None, "epoch index unknown while disabled"
    assert idx1 == idx0
    assert get_epoch_tick(dut) == 0
    assert get_epoch_end(dut) == 0

    # Enable timer through ui_in[7]
    dut.ui_in.value = 0x80

    # Wait for first epoch tick
    saw_tick = False
    for cyc in range(100500):
        await ClockCycles(dut.clk, 1)
        if get_epoch_tick(dut):
            dut._log.info(f"First tick seen at cycle offset {cyc}")
            saw_tick = True
            break

    assert saw_tick, "Did not see first epoch tick"

    idx = get_epoch_index(dut)
    assert idx is not None, "epoch index unknown at first tick"
    assert idx == 1, f"epoch index should be 1 on first tick, got {idx}"
    assert get_epoch_end(dut) == 0

    # Tick should be one cycle wide
    await ClockCycles(dut.clk, 1)
    assert get_epoch_tick(dut) == 0, "epoch tick should be one cycle wide"

    # Wait for second epoch tick
    saw_tick = False
    for cyc in range(100500):
        await ClockCycles(dut.clk, 1)
        if get_epoch_tick(dut):
            dut._log.info(f"Second tick seen at cycle offset {cyc}")
            saw_tick = True
            break

    assert saw_tick, "Did not see second epoch tick"

    idx = get_epoch_index(dut)
    assert idx is not None, "epoch index unknown at second tick"
    assert idx == 2, f"epoch index should be 2 on second tick, got {idx}"
    assert get_epoch_end(dut) == 0

    # Basic sanity while running
    for _ in range(20):
        await ClockCycles(dut.clk, 1)
        idx = get_epoch_index(dut)
        if idx is not None:
            assert 0 <= idx <= 1023
        assert get_epoch_tick(dut) in (0, 1)
        assert get_epoch_end(dut) in (0, 1)