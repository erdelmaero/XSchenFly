"""VHF radio page on the MCDU's ATC COMM key (ToLiss).

The ATC COMM key opens a page drawn by the driver instead of the ToLiss CPDLC page (CPDLC stays reachable via
MCDU MENU -> ATSU). It shows and controls VHF1/VHF2:

    LSK1L/2L  swap active <-> standby of VHF1/VHF2
    LSK1R/2R  scratchpad -> standby of VHF1/VHF2 (empty scratchpad: copy the standby into it)
    LSK4L/4R  TRANSMIT on VHF1/VHF2, Garmin style: the new TX radio is heard, the old TX radio is switched off
    LSK5L/5R  LISTEN (monitor) toggle for the radio that is not TX; the TX radio is always heard

The scratchpad is the driver's own (digits, '.', CLR); keys typed here never reach the ToLiss scratchpad.
ATC COMM again or any page key (FPLN, PERF, MENU ...) leaves the page; the page key is passed on to ToLiss.

Display source are the X-Plane datarefs that VATSIM clients (xPilot) read, so the page shows what VATSIM uses.
Controls are ToLiss commands, so the ToLiss ACP/RMP stays consistent. Pure logic: no USB, no UDP.
"""

RA = "sim/cockpit2/radios/actuators/"
FREQ = {1: RA + "com1_frequency_hz_833", 2: RA + "com2_frequency_hz_833"}  # kHz, e.g. 121800
STBY = {1: RA + "com1_standby_frequency_hz_833", 2: RA + "com2_standby_frequency_hz_833"}
LISTEN = {1: RA + "audio_selection_com1", 2: RA + "audio_selection_com2"}  # 0/1
TX = RA + "audio_com_selection"  # 6 = com1, 7 = com2 (DataRefs.txt)
TX_VALUE = {1: 6, 2: 7}

RADIO_DATAREFS = [FREQ[1], FREQ[2], STBY[1], STBY[2], LISTEN[1], LISTEN[2], TX]

# ToLiss commands (registered by the ToLiss plugin, descriptions from its binary)
CMD_TX = {1: "AirbusFBW/ACP1/VHF1Press", 2: "AirbusFBW/ACP1/VHF2Press"}  # "Press VHF1 talk button on ACP1"
CMD_LISTEN = {1: "AirbusFBW/ListenVHF1", 2: "AirbusFBW/ListenVHF2"}  # "Toggling monitoring of VHF1"
CMD_SWAP = {1: "sim/radios/com1_standy_flip", 2: "sim/radios/com2_standy_flip"}  # also handled by ToLiss


# Verified in the sim (ToLiss A320neo, X-Plane 12.4.3, Web API): writing comN_standby_frequency_hz_833 is adopted by
# the ToLiss RMP (VHF1 = RMP1, VHF2 = RMP2) and stays; comN_standy_flip swaps exactly; ACP1/VHFnPress sets
# audio_com_selection 6/7 but does NOT switch listening on (done here); ListenVHFn toggles audio_selection_comN.
def stby_actions(radio, khz):
    """Actions that set the standby frequency of a radio."""
    return [("dref", STBY[radio], khz)]


def swap_actions(radio):
    return [("cmd", CMD_SWAP[radio])]


PAGE_KEYS = {"DIRTO", "PROG", "PERF", "INIT", "DATA", "FPLN", "RADNAV", "FUEL", "SEC-FPLN", "MENU", "AIRPORT"}
PASS_KEYS = {"BRT", "DIM", "EMTYR", "PURSER"}  # work as usual while the page is shown
DIGITS = {f"KEY{i}": str(i) for i in range(10)}

# last two kHz digits of valid channels (25 kHz and 8.33 kHz channel names)
VALID_ENDINGS = {0, 5, 10, 15, 25, 30, 35, 40, 50, 55, 60, 65, 75, 80, 85, 90}
FREQ_MIN, FREQ_MAX = 118000, 136990

LINES, CHARS = 14, 24


def parse_freq(text):
    """'121.8', '121.80', '121.800', '1218', '12180', '121800' -> 121800 (kHz); None if invalid."""
    text = text.strip()
    if text.count(".") > 1:
        return None
    if "." in text:
        mhz, dec = text.split(".")
    else:
        mhz, dec = text[:3], text[3:]
    if len(mhz) != 3 or len(dec) > 3 or not mhz.isdigit() or (dec and not dec.isdigit()):
        return None
    khz = int(mhz) * 1000 + int(dec.ljust(3, "0") or 0)
    if not FREQ_MIN <= khz <= FREQ_MAX or khz % 100 not in VALID_ENDINGS:
        return None
    return khz


def fmt_freq(khz):
    if khz is None or khz <= 0:
        return "---.---"
    khz = int(khz)
    return f"{khz // 1000}.{khz % 1000:03d}"


class RadioPage:
    def __init__(self):
        self.active = False
        self.scratch = ""
        self.message = ""

    # ------------------------------------------------------------------ keys
    def handle_key(self, label, values):
        """Returns (consumed, actions). consumed=False: the key goes to ToLiss as usual.
        actions: ("cmd", command) or ("dref", dataref, value)."""
        if label == "ATC":
            self.active = not self.active
            self.message = ""
            return True, []
        if not self.active:
            return False, []
        if label in PAGE_KEYS:
            self.active = False
            return False, []
        if label in PASS_KEYS:
            return False, []

        self.message = ""
        if label in DIGITS:
            if len(self.scratch) < 7:
                self.scratch += DIGITS[label]
        elif label == "DOT":
            if "." not in self.scratch and len(self.scratch) < 7:
                self.scratch += "."
        elif label == "Clear":
            self.scratch = self.scratch[:-1]
        elif label in ("LSK1L", "LSK2L"):
            return True, swap_actions(int(label[3]))
        elif label in ("LSK1R", "LSK2R"):
            return True, self._enter_stby(int(label[3]), values)
        elif label == "LSK4L":
            return True, self._transmit(1, values)
        elif label == "LSK4R":
            return True, self._transmit(2, values)
        elif label == "LSK5L":
            return True, self._monitor(1, values)
        elif label == "LSK5R":
            return True, self._monitor(2, values)
        return True, []  # everything else is swallowed while the page is shown

    def _enter_stby(self, radio, values):
        if not self.scratch:
            stby = values.get(STBY[radio])
            if stby:
                self.scratch = fmt_freq(stby)
            return []
        khz = parse_freq(self.scratch)
        if khz is None:
            self.message = "FORMAT ERROR"
            return []
        self.scratch = ""
        return stby_actions(radio, khz)

    def _transmit(self, radio, values):
        other = 3 - radio
        tx = int(values.get(TX, 0))
        actions = []
        if tx != TX_VALUE[radio]:
            actions.append(("cmd", CMD_TX[radio]))
            if tx == TX_VALUE[other] and int(values.get(LISTEN[other], 0)):
                actions.append(("cmd", CMD_LISTEN[other]))  # old TX radio off (Garmin)
        if not int(values.get(LISTEN[radio], 0)):
            actions.append(("cmd", CMD_LISTEN[radio]))  # TX radio is always heard
        return actions

    def _monitor(self, radio, values):
        if int(values.get(TX, 0)) == TX_VALUE[radio]:
            self.message = "TX RADIO ALWAYS ON"
            return []
        return [("cmd", CMD_LISTEN[radio])]

    # ------------------------------------------------------------------ display
    def render(self, values):
        """Page in the driver's format: LINES lists of CHARS * [colour, small font, char]."""
        page = [[" "] * (CHARS * 3) for _ in range(LINES)]

        def put(line, col, text, color="W", small=0, right=False):
            if right:
                col = CHARS - len(text)
            for i, ch in enumerate(text):
                if 0 <= col + i < CHARS:
                    p = (col + i) * 3
                    page[line][p:p + 3] = [color, small, ch]

        put(0, (CHARS - 9) // 2, "VHF RADIO")
        tx = int(values.get(TX, 0))
        for radio in (1, 2):
            put(radio * 2 - 1, 1, f"VHF{radio} ACTIVE", small=1)
            put(radio * 2 - 1, 0, "STBY ", small=1, right=True)
            put(radio * 2, 0, "<" + fmt_freq(values.get(FREQ[radio])), "G")
            put(radio * 2, 0, fmt_freq(values.get(STBY[radio])) + ">", "B", right=True)
        put(7, 1, "TRANSMIT", small=1)
        put(9, 1, "LISTEN", small=1)
        for radio, right in ((1, False), (2, True)):
            sel = tx == TX_VALUE[radio]
            text = f"VHF{radio}" + ("*" if sel else " ")
            put(8, 0, text + ">" if right else "<" + text, "G" if sel else "B", right=right)
            on = bool(int(values.get(LISTEN[radio], 0)))
            text = f"VHF{radio} " + ("ON" if on else "OFF")
            put(10, 0, text + ">" if right else "<" + text, "G" if on else "B", right=right)
        if self.message:
            put(13, 0, self.message, "A")
        else:
            put(13, 0, self.scratch)
        return page
