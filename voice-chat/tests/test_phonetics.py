"""Golden phonetic strings. A library upgrade that changes these must edit the pin on purpose."""

from app.phonetics.cantonese import cantonese_reading, converter_for
from app.phonetics.pipeline import annotate
from app.phonetics.putonghua import putonghua_reading
from app.scenarios import get_scenario

YUE_ORDER = "唔該，一杯熱啡，走甜。"
PIN_YUE_ORDER = "m4 goi1 jat1 bui1 jit6 fe1 zau2 tim4"
PIN_BILL = "maai4 daan1"
PIN_CMN_HELLO = "nín hǎo qǐng wèn nín yǒu yù dìng ma"
PIN_GB = "/kʊd aɪ ɡɛt ɐ kˈɒfi plˈiːz/"
PIN_US = "/kʊd aɪ ɡɛt ɐ kˈɔfi plˈiːz/"


def test_cantonese_order_and_bill():
    assert annotate(YUE_ORDER, "yue")["phonetic"] == PIN_YUE_ORDER
    assert annotate("埋單", "yue")["phonetic"] == PIN_BILL


def test_putonghua_hello_and_erhua():
    hello = annotate("您好，请问您有预订吗？", "cmn")
    assert hello["phonetic"] == PIN_CMN_HELLO
    assert hello["phonetic_complete"] is True
    erhua = annotate("这儿有一点儿吵", "cmn")["phonetic"]
    assert "zhèr" in erhua
    assert "yìdiǎnr" in erhua
    assert erhua == "zhèr yǒu yìdiǎnr chǎo"


def test_english_accents_differ_on_coffee():
    sentence = "Could I get a coffee, please?"
    gb = annotate(sentence, "en", accent="en-GB")
    us = annotate(sentence, "en", accent="en-US")
    assert gb["phonetic"] == PIN_GB
    assert us["phonetic"] == PIN_US
    assert gb["phonetic"] != us["phonetic"]
    assert "kˈɒfi" in gb["phonetic"]
    assert "kˈɔfi" in us["phonetic"]
    assert gb["phonetic_system"] == "ipa-rp"
    assert us["phonetic_system"] == "ipa-ga"
    assert gb["engine"] == "phonemizer"


def test_mixed_cantonese_and_english():
    phonetic = annotate("唔該一杯 latte", "yue", accent="en-GB")["phonetic"]
    assert phonetic.startswith("m4 goi1 jat1 bui1 ")
    assert "/lˈɑːteɪ/" in phonetic


def test_missing_reading_marks_incomplete():
    result = annotate("𠮷", "yue")
    assert result["phonetic"] == "·"
    assert result["phonetic_complete"] is False


def test_numeric_tone_keeps_u_umlaut():
    phonetic, complete, _ = putonghua_reading("女", "number", None)
    assert phonetic == "nü3"
    assert "v" not in phonetic
    assert complete is True


def test_jyutping_override_does_not_leak():
    cafe = get_scenario("hk-cha-chaan-teng")
    overridden, _, _ = cantonese_reading("單先生", cafe["jyutping_overrides"])
    default, _, _ = cantonese_reading("單先生", None)
    other, _, _ = cantonese_reading("單先生", get_scenario("london-directions")["jyutping_overrides"])
    assert overridden == "sin6 sin1 saang1"
    assert default == "daan1 sin1 saang1"
    assert other == default
    bill, _, _ = cantonese_reading("埋單", cafe["jyutping_overrides"])
    assert bill == "maai4 daan1"
    # A second converter does not mutate the default instance.
    assert converter_for(None).get_jyutping_text("單先生") == "daan1 sin1 saang1"


def test_pinyin_surname_override_does_not_leak():
    phrases = get_scenario("beijing-hotel-checkin")["pinyin_phrases"]
    shan, _, _ = putonghua_reading("单先生", "mark", phrases)
    plain, _, _ = putonghua_reading("单先生", "mark", None)
    assert shan.startswith("shàn")
    assert plain.startswith("dān")
