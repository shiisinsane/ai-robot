from nav_cmd_vel_keepalive import command_is_fresh


def test_command_is_fresh_inside_timeout():
    assert command_is_fresh(10.0, 10.14)


def test_command_is_stale_at_timeout_boundary():
    assert not command_is_fresh(10.0, 10.15)


def test_missing_command_is_stale():
    assert not command_is_fresh(None, 10.0)
