from app.detector.block_relation import classify_block_relation


def test_first_block():
    assert classify_block_relation(None) == "FIRST_BLOCK"


def test_chained_continuation():
    assert classify_block_relation(5.0, "A") == "CHAINED_CONTINUATION"
    assert classify_block_relation(8.0, "A+") == "CHAINED_CONTINUATION"


def test_same_pressure_sequence():
    assert classify_block_relation(20.0, "B+") == "SAME_PRESSURE_SEQUENCE"


def test_same_session_recheck():
    assert classify_block_relation(60.0, "A") == "SAME_SESSION_RECHECK"


def test_new_session():
    assert classify_block_relation(120.0, "A") == "NEW_SESSION_SIGNAL"
