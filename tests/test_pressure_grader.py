from app.scoring.pressure_grader import grade_pressure


def test_grade_a_plus():
    assert grade_pressure(duration=25, event_count=200, density=8, max_gap=40) == "A+"


def test_grade_a():
    assert grade_pressure(duration=15, event_count=120, density=8, max_gap=50) == "A"


def test_grade_a_minus():
    assert grade_pressure(duration=12, event_count=80, density=7.5, max_gap=55) == "A-"


def test_grade_b_plus():
    assert grade_pressure(duration=6, event_count=30, density=5.5, max_gap=80) == "B+"


def test_grade_c():
    assert grade_pressure(duration=3, event_count=5, density=1.5, max_gap=200) == "C"


def test_grade_reject():
    assert grade_pressure(duration=20, event_count=100, density=5, max_gap=400) == "REJECT"


def test_grade_none_max_gap():
    assert grade_pressure(duration=20, event_count=100, density=8, max_gap=None) == "C"
