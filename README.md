# x-touch-compact-hui-translator

Python MIDI translator for using a Behringer X-Touch Compact as a basic HUI
surface in Pro Tools.

## Requirements

- macOS with the X-Touch Compact connected by USB
- X-Touch Compact set to MC (Mackie Control) mode
- Python 3
- `mido` and `python-rtmidi`

Install the Python dependencies with:

```bash
python3 -m pip install mido python-rtmidi
```

## Setup

Run the translator:

```bash
python3 hui_server.py
```

In Pro Tools, configure the HUI control surface to use the virtual MIDI ports
named `Python HUI`. Select the port exposed as the Pro Tools input for MIDI
output from the translator, and the corresponding output for MIDI input to the
translator.

The translator supports the eight motorized faders, fader touch, channel
select/mute/solo/record-arm buttons, transport controls, bank left/right, and
the first eight track V-Pots. DAW feedback updates the corresponding X-Touch
button LEDs and fader motors. The remaining encoders are passed through as
ordinary MIDI CC messages for manual mapping.

## Use of AI
First draft have been generated using Google Gemini Pro 3.1 model with Extended Thinking.  
Refined using auto model on Github Copilot.  
Creator have checked and refined the generated code by himself.  
