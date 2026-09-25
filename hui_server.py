import mido
import time
import sys

# Force mido to use the macOS-native rtmidi backend
mido.set_backend('mido.backends.rtmidi')

# Name of your hardware device (Check Audio MIDI Setup if this differs)
XTOUCH_PORT_NAME = 'X-TOUCH COMPACT'
HUI_PORT_NAME = 'Python HUI'
FADER_COUNT = 8
HUI_FADER_CENTER_MSB = 64

def main():
    print("--- Behringer X-Touch Compact HUI Server ---")
    
    # 1. Create Virtual Ports for Pro Tools (DAW)
    try:
        hui_virtual_in = mido.open_input(HUI_PORT_NAME, virtual=True)
        hui_virtual_out = mido.open_output(HUI_PORT_NAME, virtual=True)
        print("[+] Virtual HUI ports created for Pro Tools.")
    except Exception as e:
        print(f"[-] Error creating virtual ports. Is python-rtmidi installed? {e}")
        sys.exit(1)

    # 2. Connect to the physical X-Touch Compact
    in_names = mido.get_input_names()
    out_names = mido.get_output_names()
    
    xt_in_name = next((n for n in in_names if XTOUCH_PORT_NAME in n), None)
    xt_out_name = next((n for n in out_names if XTOUCH_PORT_NAME in n), None)

    if not xt_in_name or not xt_out_name:
        print("[-] X-Touch Compact not found! Ensure it is connected and in MC Mode.")
        hui_virtual_in.close()
        hui_virtual_out.close()
        sys.exit(1)

    xtouch_in = mido.open_input(xt_in_name)
    xtouch_out = mido.open_output(xt_out_name)
    print(f"[+] Connected to hardware: {xt_in_name}")

    # --- State Variables ---
    current_hui_zone = 0
    fader_msb = [HUI_FADER_CENTER_MSB] * FADER_COUNT

    # --- Routing Callbacks ---

    def handle_xtouch_to_daw(msg):
        """Translates physical X-Touch movements (MCU) -> Pro Tools (HUI)"""
        
        # 1. Fader Movements (MCU Pitchbend -> HUI MSB/LSB CCs)
        if msg.type == 'pitchwheel':
            ch = msg.channel
            if 0 <= ch <= 7: # Only map the 8 channel faders
                # Convert pitchwheel (-8192 to 8191) to 14-bit unsigned (0-16383)
                val = msg.pitch + 8192
                msb = (val >> 7) & 0x7F
                lsb = val & 0x7F
                hui_virtual_out.send(mido.Message('control_change', channel=0, control=ch, value=msb))
                hui_virtual_out.send(mido.Message('control_change', channel=0, control=ch+32, value=lsb))

        # 2. Fader Touches & Buttons (MCU Notes -> HUI Zones/Ports)
        elif msg.type in ['note_on', 'note_off']:
            is_press = 1 if (msg.type == 'note_on' and msg.velocity > 0) else 0

            # Fader Touches (Notes 104-111)
            if 104 <= msg.note <= 111:
                fader_idx = msg.note - 104
                hui_virtual_out.send(mido.Message('control_change', channel=0, control=0x0F, value=fader_idx))
                hui_virtual_out.send(mido.Message('control_change', channel=0, control=0x2F, value=0x40 if is_press else 0x00))

            # Bank Left (46) / Bank Right (47)
            elif msg.note == 46 and is_press:
                hui_virtual_out.send(mido.Message('control_change', channel=0, control=0x0C, value=0x0A))
                hui_virtual_out.send(mido.Message('control_change', channel=0, control=0x2C, value=0x40))
                hui_virtual_out.send(mido.Message('control_change', channel=0, control=0x0C, value=0x0A))
                hui_virtual_out.send(mido.Message('control_change', channel=0, control=0x2C, value=0x00))
            elif msg.note == 47 and is_press:
                hui_virtual_out.send(mido.Message('control_change', channel=0, control=0x0C, value=0x0A))
                hui_virtual_out.send(mido.Message('control_change', channel=0, control=0x2C, value=0x41))
                hui_virtual_out.send(mido.Message('control_change', channel=0, control=0x0C, value=0x0A))
                hui_virtual_out.send(mido.Message('control_change', channel=0, control=0x2C, value=0x01))

            # Transport
            elif msg.note in [91, 92, 93, 94, 95]:
                port_map = {91: 0, 92: 1, 93: 2, 94: 3, 95: 4} # Rew, FF, Stop, Play, Rec
                port = port_map[msg.note]
                val = 0x40 + port if is_press else port
                hui_virtual_out.send(mido.Message('control_change', channel=0, control=0x0C, value=0x0E))
                hui_virtual_out.send(mido.Message('control_change', channel=0, control=0x2C, value=val))

        # 3. Rotaries 1-16
        elif msg.type == 'control_change':
            if 16 <= msg.control <= 23:
                # Top 8 Encoders -> HUI Track V-Pots (CC 64-71)
                hui_cc = msg.control - 16 + 0x40
                hui_virtual_out.send(mido.Message('control_change', channel=0, control=hui_cc, value=msg.value))
            else:
                # Encoders 9-16 (X-Touch Compact side encoders)
                # Pro Tools HUI doesn't natively map 16 rotaries to tracks.
                # We pass these through as standard CCs so you can "MIDI Learn" 
                # them manually to plugins or parameters inside Pro Tools.
                hui_virtual_out.send(msg)


    def handle_daw_to_xtouch(msg):
        """Translates Pro Tools automation (HUI) -> X-Touch Motors (MCU)"""
        nonlocal current_hui_zone, fader_msb

        # 1. HUI Heartbeat Ping (CRITICAL: PT drops connection without this)
        if msg.type == 'note_on' and msg.note == 0 and msg.velocity == 0:
            hui_virtual_out.send(mido.Message('note_on', channel=0, note=0, velocity=127))
            return

        elif msg.type == 'control_change':
            # 2. Fader MSB
            if 0 <= msg.control <= 7:
                fader_msb[msg.control] = msg.value

            # 3. Fader LSB (Triggers motor movement)
            elif 32 <= msg.control <= 39:
                ch = msg.control - 32
                val = (fader_msb[ch] << 7) | msg.value
                pb_val = val - 8192
                xtouch_out.send(mido.Message('pitchwheel', channel=ch, pitch=pb_val))

            # 4. Transport LEDs (Syncs hardware lights with DAW)
            elif msg.control == 0x0C:
                current_hui_zone = msg.value
            elif msg.control == 0x2C:
                if current_hui_zone == 0x0E: # Transport Zone
                    port = msg.value & 0x0F
                    is_on = (msg.value & 0x40) > 0
                    mcu_note_map = {0: 91, 1: 92, 2: 93, 3: 94, 4: 95}
                    if port in mcu_note_map:
                        vel = 127 if is_on else 0
                        xtouch_out.send(mido.Message('note_on', channel=0, note=mcu_note_map[port], velocity=vel))

    # Attach callbacks to ports
    xtouch_in.callback = handle_xtouch_to_daw
    hui_virtual_in.callback = handle_daw_to_xtouch

    print("[+] Server Active. Press Ctrl+C to terminate.")
    try:
        while True:
            time.sleep(1) # Keep daemon alive without burning CPU
    except KeyboardInterrupt:
        print("\nStopping HUI Server...")
        xtouch_in.close()
        xtouch_out.close()
        hui_virtual_in.close()
        hui_virtual_out.close()

if __name__ == '__main__':
    main()
