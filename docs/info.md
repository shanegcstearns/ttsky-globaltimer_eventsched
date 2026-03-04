<!---

This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

You can also include images in this folder and reference them in the markdown. Each image must be less than
512 kb in size, and the combined size of all images must be less than 1 MB.
-->
## How it works

This project implements a small hardware event scheduler built around an epoch based global timer.  
A clock divider generates periodic **epoch ticks** (e.g., 100 Hz), which increment an **epoch counter** representing time in the system.

Four programmable events can be configured with a **start epoch**, **duration**, and **enable bit**.  
When the current epoch falls within an event's programmed window, the scheduler asserts `event_active` and outputs the corresponding `event_id`. If multiple events overlap, a fixed priority scheme selects the lowest numbered event.

The design also includes a **power-of-two window generator** for periodic processing windows and a small **serial debug shifter** that streams internal status information out through a single pin.

## How to test

The project includes a **cocotb testbench** that verifies each module individually and then tests the full top-level design.

Run the simulation with:


## External hardware
No external hardware required or used

## GenAI Tools
Generative AI was used to create all modules except the basic epoch based global timer
