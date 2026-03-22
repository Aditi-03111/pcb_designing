"""Prompt-to-circuit synthesis using reusable building blocks."""

from __future__ import annotations

from typing import Any, Dict, Optional

from .block_library import (
    CircuitBuilder,
    add_555_timer,
    add_decoupling_cap,
    add_led_indicator,
    add_linear_regulator,
    add_minimal_mcu,
    add_mosfet_low_side_switch,
    add_opamp_buffer,
    add_output_header,
    add_power_input,
    add_rc_lowpass,
    add_voltage_divider,
)
from .prompt_parser import DesignIntent, parse_prompt


def synthesize_circuit(
    prompt: str,
    constraints: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Generate a deterministic circuit graph from a parsed prompt."""
    intent = parse_prompt(prompt, constraints)
    builder = CircuitBuilder()

    input_net = _input_net(intent)
    main_supply = _main_supply_net(intent)
    description = intent.title

    add_power_input(builder, net=input_net, label="Primary power input")

    synthesized = False

    if intent.wants_regulator:
        add_linear_regulator(
            builder,
            input_net=input_net,
            output_net=main_supply,
            output_voltage=_output_voltage_label(intent),
        )
        synthesized = True

    supply_for_logic = main_supply if intent.wants_regulator else input_net

    if intent.wants_timer:
        add_555_timer(builder, supply_net=supply_for_logic, output_net="TIMER_OUT")
        add_output_header(builder, signal_net="TIMER_OUT", label="Timer output")
        if intent.wants_led or "blink" in intent.normalized_prompt:
            add_led_indicator(builder, input_net="TIMER_OUT", label="Timer-driven LED")
        synthesized = True

    if intent.wants_mcu:
        add_minimal_mcu(builder, supply_net=supply_for_logic, io_net="GPIO_OUT", sensor_net="SENSE_IN")
        if intent.wants_led:
            add_led_indicator(builder, input_net="GPIO_OUT", label="MCU status LED")
        if intent.wants_sensor:
            add_output_header(builder, signal_net="SENSE_IN", label="Sensor input header")
        synthesized = True

    if intent.wants_switch:
        control_net = "GPIO_OUT" if intent.wants_mcu else "CTRL"
        if not intent.wants_mcu:
            add_output_header(builder, signal_net=control_net, label="Control input")
        load_supply = "12V" if (intent.supply_voltage or 0) >= 9 else supply_for_logic
        if load_supply != input_net:
            add_power_input(builder, net=load_supply, label="Load supply input")
        add_mosfet_low_side_switch(
            builder,
            control_net=control_net,
            supply_net=load_supply,
            switched_net="LOAD_RETURN",
        )
        synthesized = True

    if intent.wants_opamp:
        add_output_header(builder, signal_net="ANALOG_IN", label="Analog input")
        add_opamp_buffer(builder, input_net="ANALOG_IN", output_net="BUFFER_OUT", supply_net=supply_for_logic)
        add_output_header(builder, signal_net="BUFFER_OUT", label="Buffered output")
        synthesized = True

    if intent.wants_divider:
        add_output_header(builder, signal_net=input_net, label="Divider input")
        add_voltage_divider(builder, input_net=input_net, output_net="DIV_OUT")
        add_output_header(builder, signal_net="DIV_OUT", label="Divider output")
        synthesized = True

    if intent.wants_filter:
        add_output_header(builder, signal_net=input_net, label="Filter input")
        add_rc_lowpass(builder, input_net=input_net, output_net="FILTER_OUT")
        add_output_header(builder, signal_net="FILTER_OUT", label="Filtered output")
        synthesized = True

    if intent.wants_led and not any(family in intent.families for family in ("timer", "mcu")):
        add_led_indicator(builder, input_net=supply_for_logic, label="Power/status LED")
        synthesized = True

    if intent.wants_sensor and not intent.wants_mcu and not intent.wants_opamp:
        add_output_header(builder, signal_net="SENSOR_SIG", label="Sensor signal")
        add_rc_lowpass(builder, input_net="SENSOR_SIG", output_net="FILTER_OUT")
        add_output_header(builder, signal_net="FILTER_OUT", label="Filtered sensor output")
        synthesized = True

    if not synthesized:
        add_voltage_divider(builder, input_net=input_net, output_net="NODE_A")
        add_rc_lowpass(builder, input_net="NODE_A", output_net="NODE_B")
        add_led_indicator(builder, input_net="NODE_B", label="Generic activity LED")
        add_output_header(builder, signal_net="NODE_B", label="Signal output")

    add_decoupling_cap(builder, power_net=supply_for_logic, gnd_net="GND")

    return builder.build(
        description=description,
        metadata={
            "generation_mode": "synthesized",
            "intent": intent.as_dict(),
            "source": "block_library_v1",
        },
    )


def _input_net(intent: DesignIntent) -> str:
    voltage = intent.supply_voltage
    if voltage is None:
        return "VCC"
    if abs(voltage - 12.0) < 0.2:
        return "12V"
    if abs(voltage - 9.0) < 0.2:
        return "9V"
    if abs(voltage - 5.0) < 0.2:
        return "5V"
    if abs(voltage - 3.3) < 0.2:
        return "3V3"
    return "VIN"


def _main_supply_net(intent: DesignIntent) -> str:
    if intent.output_voltage is not None:
        if abs(intent.output_voltage - 3.3) < 0.2:
            return "3V3"
        if abs(intent.output_voltage - 5.0) < 0.2:
            return "5V"
        return "VOUT"
    if intent.wants_regulator:
        return "3V3"
    return _input_net(intent)


def _output_voltage_label(intent: DesignIntent) -> str:
    if intent.output_voltage is None:
        return "3.3V"
    return f"{intent.output_voltage:g}V"
