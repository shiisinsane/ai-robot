from pathlib import Path

import pytest

from scripts.check_m5_saved_map import MapFileError, validate
from src.robot_core.ai_robot_sim.scripts.map_save_guard import resolve_map_base


def test_safe_map_name_stays_in_allowed_directory(tmp_path):
    assert resolve_map_base(tmp_path, 'm5_w4-map_01') == tmp_path / 'm5_w4-map_01'


@pytest.mark.parametrize('name', ('../escape', '/tmp/escape', 'nested/map', '.', '', 'a' * 65))
def test_rejects_unsafe_map_name(tmp_path, name):
    with pytest.raises(ValueError):
        resolve_map_base(tmp_path, name)


def _write_map(tmp_path, image='../outside.pgm'):
    yaml_path = tmp_path / 'map.yaml'
    yaml_path.write_text(
        f'image: {image}\nmode: trinary\nresolution: 0.05\n'
        'origin: [0.0, 0.0, 0.0]\nnegate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.25\n',
        encoding='utf-8')
    return yaml_path


def test_rejects_image_outside_map_directory(tmp_path):
    with pytest.raises(MapFileError, match='越出'):
        validate(_write_map(tmp_path))


def test_valid_saved_map_passes(tmp_path):
    image = tmp_path / 'map.pgm'
    image.write_bytes(b'P5\n100 101\n255\n' + bytes(100 * 101))
    result = validate(_write_map(tmp_path, 'map.pgm'))
    assert (result['width'], result['height']) == (100, 101)
    assert set(result['hashes']) == {'map.yaml', 'map.pgm'}
