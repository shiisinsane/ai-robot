from ai_robot_py_demo.status_publisher import make_status_message


def test_make_status_message():
    assert make_status_message() == "ai-robot M0 Python node ready"
