import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "devices"))

import mcdu_radio_page as rp

V = {  # VHF1 TX + listen, VHF2 not heard
    rp.FREQ[1]: 121800, rp.STBY[1]: 118705, rp.FREQ[2]: 122800, rp.STBY[2]: 121500,
    rp.TX: 6, rp.LISTEN[1]: 1, rp.LISTEN[2]: 0,
}


def text(page, line):
    return "".join(page[line][i * 3 + 2] for i in range(rp.CHARS))


def color_at(page, line, col):
    return page[line][col * 3]


def opened():
    p = rp.RadioPage()
    assert p.handle_key("ATC", V) == (True, [])
    return p


def test_parse_freq():
    for s in ("121.8", "121.80", "121.800", "1218", "12180", "121800"):
        assert rp.parse_freq(s) == 121800, s
    assert rp.parse_freq("118.705") == 118705
    assert rp.parse_freq("136.990") == 136990
    assert rp.parse_freq("121") == 121000
    for s in ("140.0", "117.975", "121.820", "121.8.0", "12.18", "121.8000", "", ".", "abc"):
        assert rp.parse_freq(s) is None, s


def test_inactive_passes_everything():
    p = rp.RadioPage()
    assert p.handle_key("LSK1L", V) == (False, [])
    assert p.handle_key("KEY1", V) == (False, [])


def test_atc_toggles_and_page_keys_exit():
    p = opened()
    assert p.active
    assert p.handle_key("FPLN", V) == (False, [])  # passed on to ToLiss
    assert not p.active
    p = opened()
    assert p.handle_key("ATC", V) == (True, [])
    assert not p.active


def test_pass_keys_keep_page():
    p = opened()
    assert p.handle_key("BRT", V) == (False, [])
    assert p.active


def test_letters_swallowed():
    p = opened()
    assert p.handle_key("KEYA", V) == (True, [])
    assert p.scratch == ""


def test_scratchpad_and_standby_entry():
    p = opened()
    for k in ("KEY1", "KEY2", "KEY1", "DOT", "KEY8"):
        assert p.handle_key(k, V)[0]
    assert p.scratch == "121.8"
    assert p.handle_key("LSK1R", V) == (True, [("dref", rp.STBY[1], 121800)])
    assert p.scratch == ""


def test_clear_and_format_error():
    p = opened()
    for k in ("KEY1", "KEY4", "KEY0", "Clear"):
        p.handle_key(k, V)
    assert p.scratch == "14"
    p.handle_key("KEY0", V)
    assert p.handle_key("LSK2R", V) == (True, [])
    assert p.message == "FORMAT ERROR"
    assert p.scratch == "140"
    assert text(p.render(V), 13).startswith("FORMAT ERROR")
    assert color_at(p.render(V), 13, 0) == "A"
    p.handle_key("Clear", V)  # any key clears the message
    assert p.message == ""


def test_empty_scratch_copies_standby():
    p = opened()
    assert p.handle_key("LSK2R", V) == (True, [])
    assert p.scratch == "121.500"


def test_swap():
    p = opened()
    assert p.handle_key("LSK2L", V) == (True, [("cmd", rp.CMD_SWAP[2])])


def test_transmit_garmin_switch():
    p = opened()
    # TX VHF1 -> VHF2: press VHF2, VHF1 listen off, VHF2 listen on
    assert p.handle_key("LSK4R", V)[1] == [("cmd", rp.CMD_TX[2]), ("cmd", rp.CMD_LISTEN[1]),
                                          ("cmd", rp.CMD_LISTEN[2])]


def test_transmit_old_radio_already_silent():
    p = opened()
    v = dict(V, **{rp.LISTEN[1]: 0, rp.LISTEN[2]: 1})
    assert p.handle_key("LSK4R", v)[1] == [("cmd", rp.CMD_TX[2])]


def test_transmit_same_radio_only_ensures_listen():
    p = opened()
    assert p.handle_key("LSK4L", V)[1] == []
    v = dict(V, **{rp.LISTEN[1]: 0})
    assert p.handle_key("LSK4L", v)[1] == [("cmd", rp.CMD_LISTEN[1])]


def test_monitor():
    p = opened()
    assert p.handle_key("LSK5R", V) == (True, [("cmd", rp.CMD_LISTEN[2])])
    assert p.handle_key("LSK5L", V) == (True, [])  # VHF1 is TX
    assert p.message == "TX RADIO ALWAYS ON"


def test_render():
    p = opened()
    page = p.render(V)
    assert len(page) == rp.LINES and all(len(line) == rp.CHARS * 3 for line in page)
    assert text(page, 0).strip() == "VHF RADIO"
    assert text(page, 2) == "<121.800" + " " * 8 + "118.705>"
    assert color_at(page, 2, 1) == "G" and color_at(page, 2, 23) == "B"
    assert text(page, 4).startswith("<122.800") and text(page, 4).endswith("121.500>")
    assert text(page, 8).startswith("<VHF1*") and text(page, 8).endswith("VHF2 >")
    assert color_at(page, 8, 0) == "G" and color_at(page, 8, 23) == "B"
    assert text(page, 10).startswith("<VHF1 ON") and text(page, 10).endswith("VHF2 OFF>")
    assert page[1][3 * 1 + 1] == 1  # labels small font


def test_render_without_values():
    page = opened().render({})
    assert "---.---" in text(page, 2)
