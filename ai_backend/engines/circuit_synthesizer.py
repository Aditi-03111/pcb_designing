"""Prompt-to-circuit synthesis using reusable building blocks."""

from __future__ import annotations

from typing import Any, Dict, Optional

from .block_library import (
    CircuitBuilder,
    add_555_timer,
    add_button_input,
    add_comparator_stage,
    add_decoupling_cap,
    add_input_protection,
    add_led_indicator,
    add_linear_regulator,
    add_minimal_mcu,
    add_mosfet_low_side_switch,
    add_opamp_buffer,
    add_output_header,
    add_power_input,
    add_rc_lowpass,
    add_relay_driver,
    add_usb_power_entry,
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
    simple_led_circuit = _is_simple_led_circuit(intent)
    simple_divider_circuit = _is_simple_divider_circuit(intent)
    simple_rc_filter_circuit = _is_simple_rc_filter_circuit(intent)
    simple_usb_utility_board = _is_simple_usb_utility_board(intent)
    simple_regulator_board = _is_simple_regulator_board(intent)
    simple_opamp_board = _is_simple_opamp_board(intent)
    simple_timer_board = _is_simple_timer_board(intent)
    simple_switch_board = _is_simple_switch_board(intent)
    simple_comparator_board = _is_simple_comparator_board(intent)
    simple_relay_board = _is_simple_relay_board(intent)
    simple_protection_board = _is_simple_protection_board(intent)
    simple_button_board = _is_simple_button_board(intent)
    simple_passive_signal_circuit = simple_divider_circuit or simple_rc_filter_circuit

    if simple_led_circuit:
        return _build_simple_led_circuit(builder, intent, input_net)
    if simple_divider_circuit:
        return _build_simple_divider_circuit(builder, intent)
    if simple_rc_filter_circuit:
        return _build_simple_rc_filter_circuit(builder, intent)
    if simple_usb_utility_board:
        return _build_simple_usb_utility_board(builder, intent)
    if simple_regulator_board:
        return _build_simple_regulator_board(builder, intent, input_net, main_supply)
    if simple_opamp_board:
        return _build_simple_opamp_board(builder, intent, input_net)
    if simple_timer_board:
        return _build_simple_timer_board(builder, intent, input_net)
    if simple_switch_board:
        return _build_simple_switch_board(builder, intent, input_net)
    if simple_comparator_board:
        return _build_simple_comparator_board(builder, intent, input_net)
    if simple_relay_board:
        return _build_simple_relay_board(builder, intent, input_net)
    if simple_protection_board:
        return _build_simple_protection_board(builder, intent, input_net)
    if simple_button_board:
        return _build_simple_button_board(builder, intent, input_net)

    if intent.wants_usb:
        add_usb_power_entry(builder, vbus_net=input_net)
    elif not simple_passive_signal_circuit:
        add_power_input(builder, net=input_net, label="Primary power input")

    if intent.wants_protection and not simple_led_circuit and not simple_passive_signal_circuit:
        protected_net = "VIN_PROTECTED"
        add_input_protection(builder, input_net=input_net, protected_net=protected_net)
        input_net = protected_net
        if not intent.wants_regulator:
            main_supply = protected_net
        add_output_header(builder, signal_net=protected_net, label="Protected output")
        synthesized = True

    synthesized = False

    if simple_led_circuit:
        add_led_indicator(builder, input_net=input_net, label="Indicator LED")
        synthesized = True

    if intent.wants_regulator:
        add_linear_regulator(
            builder,
            input_net=input_net,
            output_net=main_supply,
            output_voltage=_output_voltage_label(intent),
        )
        if any(token in intent.normalized_prompt for token in ("output", "header", "board", "rail")):
            add_output_header(builder, signal_net=main_supply, label="Regulated output")
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
        if intent.wants_mcu:
            control_net = "GPIO_OUT"
        elif intent.wants_comparator:
            control_net = "CMP_OUT"
        else:
            control_net = "CTRL"
        if not intent.wants_mcu and not intent.wants_comparator:
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

    if intent.wants_comparator:
        add_output_header(builder, signal_net="SENSE_IN", label="Comparator input")
        add_comparator_stage(builder, input_net="SENSE_IN", output_net="CMP_OUT", supply_net=supply_for_logic)
        add_output_header(builder, signal_net="CMP_OUT", label="Comparator output")
        synthesized = True

    if intent.wants_relay:
        if intent.wants_mcu:
            control_net = "GPIO_OUT"
        elif intent.wants_comparator:
            control_net = "CMP_OUT"
        else:
            control_net = "RELAY_CTRL"
        if not intent.wants_mcu and not intent.wants_comparator:
            add_output_header(builder, signal_net=control_net, label="Relay control input")
        add_relay_driver(builder, control_net=control_net, supply_net=("12V" if (intent.supply_voltage or 0) >= 9 else supply_for_logic))
        synthesized = True

    if intent.wants_usb and not any(family in intent.families for family in ("regulator", "mcu", "relay", "switch")):
        add_output_header(builder, signal_net=supply_for_logic, label="USB power output")
        synthesized = True

    if intent.wants_button:
        add_button_input(builder, output_net="BTN_OUT", supply_net=supply_for_logic)
        synthesized = True

    if intent.wants_divider and not intent.wants_comparator:
        divider_input_net = "VIN" if simple_passive_signal_circuit else input_net
        add_output_header(
            builder,
            signal_net=divider_input_net,
            label="Input header" if simple_passive_signal_circuit else "Divider input",
        )
        add_voltage_divider(builder, input_net=divider_input_net, output_net="DIV_OUT")
        add_output_header(
            builder,
            signal_net="DIV_OUT",
            label="Output header" if simple_passive_signal_circuit else "Divider output",
        )
        synthesized = True

    if intent.wants_filter:
        filter_input_net = "VIN" if simple_passive_signal_circuit else input_net
        add_output_header(
            builder,
            signal_net=filter_input_net,
            label="Input header" if simple_passive_signal_circuit else "Filter input",
        )
        add_rc_lowpass(builder, input_net=filter_input_net, output_net="FILTER_OUT")
        add_output_header(builder, signal_net="FILTER_OUT", label="Filtered output")
        synthesized = True

    if intent.wants_led and not simple_led_circuit and not any(family in intent.families for family in ("timer", "mcu")):
        add_led_indicator(builder, input_net=supply_for_logic, label="Power/status LED")
        synthesized = True

    if intent.wants_sensor and not intent.wants_mcu and not intent.wants_opamp and not intent.wants_comparator:
        add_output_header(builder, signal_net="SENSOR_SIG", label="Sensor signal")
        add_rc_lowpass(builder, input_net="SENSOR_SIG", output_net="FILTER_OUT")
        add_output_header(builder, signal_net="FILTER_OUT", label="Filtered sensor output")
        synthesized = True

    if not synthesized:
        add_voltage_divider(builder, input_net=input_net, output_net="NODE_A")
        add_rc_lowpass(builder, input_net="NODE_A", output_net="NODE_B")
        add_led_indicator(builder, input_net="NODE_B", label="Generic activity LED")
        add_output_header(builder, signal_net="NODE_B", label="Signal output")

    if _needs_decoupling(intent):
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
        if "battery_powered" in intent.notes:
            return "VBAT"
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


def _is_simple_led_circuit(intent: DesignIntent) -> bool:
    prompt = intent.normalized_prompt
    return (
        intent.families == ["led"]
        and ("battery" in prompt or "resistor" in prompt or "current-limiting" in prompt or "current limiting" in prompt)
    )


def _is_simple_divider_circuit(intent: DesignIntent) -> bool:
    families = set(intent.families)
    if not intent.wants_divider or not families:
        return False
    return families.issubset({"divider", "connector"}) and not any(
        (
            intent.wants_regulator,
            intent.wants_mcu,
            intent.wants_led,
            intent.wants_switch,
            intent.wants_opamp,
            intent.wants_comparator,
            intent.wants_relay,
            intent.wants_protection,
            intent.wants_usb,
            intent.wants_button,
            intent.wants_timer,
        )
    )


def _is_simple_rc_filter_circuit(intent: DesignIntent) -> bool:
    families = set(intent.families)
    if not intent.wants_filter or not families:
        return False
    return families.issubset({"filter", "connector"}) and not any(
        (
            intent.wants_regulator,
            intent.wants_mcu,
            intent.wants_led,
            intent.wants_switch,
            intent.wants_opamp,
            intent.wants_comparator,
            intent.wants_relay,
            intent.wants_protection,
            intent.wants_usb,
            intent.wants_button,
            intent.wants_timer,
        )
    )


def _is_simple_passive_signal_circuit(intent: DesignIntent) -> bool:
    return _is_simple_divider_circuit(intent) or _is_simple_rc_filter_circuit(intent)


def _is_simple_usb_utility_board(intent: DesignIntent) -> bool:
    families = set(intent.families)
    if not intent.wants_usb or not families:
        return False
    return families.issubset({"usb", "led", "connector"}) and not any(
        (
            intent.wants_regulator,
            intent.wants_mcu,
            intent.wants_switch,
            intent.wants_opamp,
            intent.wants_comparator,
            intent.wants_relay,
            intent.wants_protection,
            intent.wants_button,
            intent.wants_timer,
            intent.wants_divider,
            intent.wants_filter,
        )
    )


def _build_simple_led_circuit(builder: CircuitBuilder, intent: DesignIntent, input_net: str) -> Dict[str, Any]:
    add_power_input(builder, net=input_net, label="Battery input")
    add_led_indicator(builder, input_net=input_net, label="Indicator LED")
    return _validated_simple_build(
        builder,
        intent,
        required_prefixes={"J", "R", "D"},
        forbidden_prefixes={"U", "Q", "K", "F", "SW"},
    )


def _build_simple_divider_circuit(builder: CircuitBuilder, intent: DesignIntent) -> Dict[str, Any]:
    add_output_header(builder, signal_net="VIN", label="Input header")
    add_voltage_divider(builder, input_net="VIN", output_net="DIV_OUT")
    add_output_header(builder, signal_net="DIV_OUT", label="Output header")
    return _validated_simple_build(
        builder,
        intent,
        required_prefixes={"J", "R"},
        forbidden_prefixes={"U", "Q", "K", "F", "SW", "D"},
    )


def _build_simple_rc_filter_circuit(builder: CircuitBuilder, intent: DesignIntent) -> Dict[str, Any]:
    add_output_header(builder, signal_net="VIN", label="Input header")
    add_rc_lowpass(builder, input_net="VIN", output_net="FILTER_OUT")
    add_output_header(builder, signal_net="FILTER_OUT", label="Output header")
    return _validated_simple_build(
        builder,
        intent,
        required_prefixes={"J", "R", "C"},
        forbidden_prefixes={"U", "Q", "K", "F", "SW", "D"},
    )


def _build_simple_usb_utility_board(builder: CircuitBuilder, intent: DesignIntent) -> Dict[str, Any]:
    add_usb_power_entry(builder, vbus_net="5V")
    add_led_indicator(builder, input_net="5V", label="Status LED")
    add_decoupling_cap(builder, power_net="5V", gnd_net="GND")
    add_output_header(builder, signal_net="5V", label="USB power output")
    return _validated_simple_build(
        builder,
        intent,
        required_prefixes={"J", "R", "C", "D"},
        forbidden_prefixes={"U", "Q", "K", "F", "SW"},
    )


def _validated_simple_build(
    builder: CircuitBuilder,
    intent: DesignIntent,
    required_prefixes: set[str],
    forbidden_prefixes: set[str],
) -> Dict[str, Any]:
    data = builder.build(
        description=intent.title,
        metadata={
            "generation_mode": "synthesized",
            "intent": intent.as_dict(),
            "source": "block_library_v1",
        },
    )
    prefixes = {_ref_prefix(component.get("ref", "")) for component in data.get("components", [])}
    if not required_prefixes.issubset(prefixes):
        return None
    if prefixes & forbidden_prefixes:
        return None
    return data


def _ref_prefix(ref: str) -> str:
    chars = []
    for ch in ref:
        if ch.isalpha():
            chars.append(ch)
        else:
            break
    return "".join(chars) or ref[:1]


def _is_simple_regulator_board(intent: DesignIntent) -> bool:
    families = set(intent.families)
    return intent.wants_regulator and families.issubset({"regulator", "led", "connector"}) and not any(
        (intent.wants_mcu, intent.wants_switch, intent.wants_opamp, intent.wants_comparator, intent.wants_relay, intent.wants_protection, intent.wants_usb, intent.wants_button, intent.wants_divider, intent.wants_filter, intent.wants_timer)
    )


def _is_simple_opamp_board(intent: DesignIntent) -> bool:
    families = set(intent.families)
    return intent.wants_opamp and families.issubset({"opamp", "sensor", "connector"}) and not any(
        (intent.wants_regulator, intent.wants_mcu, intent.wants_led, intent.wants_switch, intent.wants_comparator, intent.wants_relay, intent.wants_protection, intent.wants_usb, intent.wants_button, intent.wants_divider, intent.wants_filter, intent.wants_timer)
    )


def _is_simple_timer_board(intent: DesignIntent) -> bool:
    families = set(intent.families)
    return intent.wants_timer and families.issubset({"timer", "led", "connector"}) and not any(
        (intent.wants_regulator, intent.wants_mcu, intent.wants_switch, intent.wants_opamp, intent.wants_comparator, intent.wants_relay, intent.wants_protection, intent.wants_usb, intent.wants_button, intent.wants_divider, intent.wants_filter)
    )


def _is_simple_switch_board(intent: DesignIntent) -> bool:
    families = set(intent.families)
    return intent.wants_switch and families.issubset({"switch", "connector", "led"}) and not any(
        (intent.wants_regulator, intent.wants_mcu, intent.wants_opamp, intent.wants_comparator, intent.wants_relay, intent.wants_protection, intent.wants_usb, intent.wants_button, intent.wants_divider, intent.wants_filter, intent.wants_timer)
    )


def _is_simple_comparator_board(intent: DesignIntent) -> bool:
    families = set(intent.families)
    return intent.wants_comparator and families.issubset({"comparator", "sensor", "connector", "divider"}) and not any(
        (intent.wants_regulator, intent.wants_mcu, intent.wants_led, intent.wants_switch, intent.wants_opamp, intent.wants_relay, intent.wants_protection, intent.wants_usb, intent.wants_button, intent.wants_filter, intent.wants_timer)
    )


def _is_simple_relay_board(intent: DesignIntent) -> bool:
    families = set(intent.families)
    return intent.wants_relay and families.issubset({"relay", "connector"}) and not any(
        (intent.wants_regulator, intent.wants_mcu, intent.wants_led, intent.wants_switch, intent.wants_opamp, intent.wants_comparator, intent.wants_protection, intent.wants_usb, intent.wants_button, intent.wants_divider, intent.wants_filter, intent.wants_timer)
    )


def _is_simple_protection_board(intent: DesignIntent) -> bool:
    families = set(intent.families)
    return intent.wants_protection and families.issubset({"protection", "connector"}) and not any(
        (intent.wants_regulator, intent.wants_mcu, intent.wants_led, intent.wants_switch, intent.wants_opamp, intent.wants_comparator, intent.wants_relay, intent.wants_usb, intent.wants_button, intent.wants_divider, intent.wants_filter, intent.wants_timer)
    )


def _is_simple_button_board(intent: DesignIntent) -> bool:
    families = set(intent.families)
    return intent.wants_button and families.issubset({"button", "connector"}) and not any(
        (intent.wants_regulator, intent.wants_mcu, intent.wants_led, intent.wants_switch, intent.wants_opamp, intent.wants_comparator, intent.wants_relay, intent.wants_protection, intent.wants_usb, intent.wants_divider, intent.wants_filter, intent.wants_timer)
    )


def _build_simple_regulator_board(builder: CircuitBuilder, intent: DesignIntent, input_net: str, main_supply: str) -> Dict[str, Any]:
    add_power_input(builder, net=input_net, label="Power input")
    add_linear_regulator(builder, input_net=input_net, output_net=main_supply, output_voltage=_output_voltage_label(intent))
    add_output_header(builder, signal_net=main_supply, label="Regulated output")
    if intent.wants_led:
        add_led_indicator(builder, input_net=main_supply, label="Status LED")
    return _validated_simple_build(builder, intent, {"J", "U", "C"}, {"Q", "K", "F", "SW"})


def _build_simple_opamp_board(builder: CircuitBuilder, intent: DesignIntent, input_net: str) -> Dict[str, Any]:
    supply_net = "5V" if intent.supply_voltage is None else _input_net(intent)
    add_power_input(builder, net=supply_net, label="Power input")
    add_output_header(builder, signal_net="ANALOG_IN", label="Analog input")
    add_opamp_buffer(builder, input_net="ANALOG_IN", output_net="BUFFER_OUT", supply_net=supply_net)
    add_output_header(builder, signal_net="BUFFER_OUT", label="Buffered output")
    return _validated_simple_build(builder, intent, {"J", "U", "C"}, {"Q", "K", "F", "SW"})


def _build_simple_timer_board(builder: CircuitBuilder, intent: DesignIntent, input_net: str) -> Dict[str, Any]:
    add_power_input(builder, net=input_net, label="Power input")
    add_555_timer(builder, supply_net=input_net, output_net="TIMER_OUT")
    add_output_header(builder, signal_net="TIMER_OUT", label="Timer output")
    if intent.wants_led or "blink" in intent.normalized_prompt:
        add_led_indicator(builder, input_net="TIMER_OUT", label="Timer-driven LED")
    return _validated_simple_build(builder, intent, {"J", "U", "R", "C"}, {"Q", "K", "F", "SW"})


def _build_simple_switch_board(builder: CircuitBuilder, intent: DesignIntent, input_net: str) -> Dict[str, Any]:
    load_supply = "12V" if (intent.supply_voltage or 0) >= 9 else input_net
    add_power_input(builder, net=load_supply, label="Load supply input")
    add_output_header(builder, signal_net="CTRL", label="Control input")
    add_mosfet_low_side_switch(builder, control_net="CTRL", supply_net=load_supply, switched_net="LOAD_RETURN")
    if intent.wants_led:
        add_led_indicator(builder, input_net="CTRL", label="Control/status LED")
    return _validated_simple_build(builder, intent, {"J", "Q", "R"}, {"U", "K", "F", "SW"})


def _build_simple_comparator_board(builder: CircuitBuilder, intent: DesignIntent, input_net: str) -> Dict[str, Any]:
    supply_net = "5V" if intent.supply_voltage is None else _input_net(intent)
    add_power_input(builder, net=supply_net, label="Power input")
    add_output_header(builder, signal_net="SENSE_IN", label="Comparator input")
    add_comparator_stage(builder, input_net="SENSE_IN", output_net="CMP_OUT", supply_net=supply_net)
    add_output_header(builder, signal_net="CMP_OUT", label="Comparator output")
    return _validated_simple_build(builder, intent, {"J", "U", "R", "C"}, {"Q", "K", "F", "SW"})


def _build_simple_relay_board(builder: CircuitBuilder, intent: DesignIntent, input_net: str) -> Dict[str, Any]:
    supply_net = "12V" if (intent.supply_voltage or 0) >= 9 else input_net
    add_power_input(builder, net=supply_net, label="Power input")
    add_output_header(builder, signal_net="RELAY_CTRL", label="Relay control input")
    add_relay_driver(builder, control_net="RELAY_CTRL", supply_net=supply_net)
    return _validated_simple_build(builder, intent, {"J", "K", "Q", "R", "D"}, {"U", "F", "SW"})


def _build_simple_protection_board(builder: CircuitBuilder, intent: DesignIntent, input_net: str) -> Dict[str, Any]:
    add_power_input(builder, net=input_net, label="Power input")
    add_input_protection(builder, input_net=input_net, protected_net="VIN_PROTECTED")
    add_output_header(builder, signal_net="VIN_PROTECTED", label="Protected output")
    return _validated_simple_build(builder, intent, {"J", "F", "D"}, {"U", "Q", "K", "SW"})


def _build_simple_button_board(builder: CircuitBuilder, intent: DesignIntent, input_net: str) -> Dict[str, Any]:
    supply_net = "5V" if intent.supply_voltage is None else _input_net(intent)
    add_power_input(builder, net=supply_net, label="Logic supply")
    add_button_input(builder, output_net="BTN_OUT", supply_net=supply_net)
    return _validated_simple_build(builder, intent, {"J", "SW", "R"}, {"U", "Q", "K", "F", "D"})


def _needs_decoupling(intent: DesignIntent) -> bool:
    return any(
        (
            intent.wants_regulator,
            intent.wants_mcu,
            intent.wants_timer,
            intent.wants_opamp,
            intent.wants_comparator,
            intent.wants_switch,
            intent.wants_relay,
            intent.wants_button,
            intent.wants_protection,
            intent.wants_usb,
        )
    )
