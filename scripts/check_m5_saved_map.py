#!/usr/bin/env python3
"""离线检查Nav2保存地图的YAML、图像路径、尺寸与完整性。"""

import argparse
import hashlib
from pathlib import Path

import yaml


class MapFileError(ValueError):
    pass


def _pgm_size(path):
    with path.open('rb') as stream:
        if stream.readline().strip() != b'P5':
            raise MapFileError('地图图像必须是P5 PGM')
        line = stream.readline()
        while line.startswith(b'#'):
            line = stream.readline()
        width, height = map(int, line.split())
        maximum = int(stream.readline())
    if maximum != 255:
        raise MapFileError('PGM灰度上限必须为255')
    return width, height


def validate(path):
    yaml_path = Path(path).resolve()
    data = yaml.safe_load(yaml_path.read_text(encoding='utf-8'))
    required = {'image', 'mode', 'resolution', 'origin', 'negate',
                'occupied_thresh', 'free_thresh'}
    if not isinstance(data, dict) or not required <= set(data):
        raise MapFileError('地图YAML字段不完整')
    image_path = (yaml_path.parent / data['image']).resolve()
    if image_path.parent != yaml_path.parent:
        raise MapFileError('地图图像越出YAML目录')
    if not image_path.is_file():
        raise MapFileError('地图图像不存在')
    width, height = _pgm_size(image_path)
    if width < 100 or height < 100:
        raise MapFileError('地图尺寸不足')
    if abs(float(data['resolution']) - 0.05) > 1e-6:
        raise MapFileError('地图分辨率不是0.05 m')
    if len(data['origin']) != 3:
        raise MapFileError('地图原点必须为[x,y,yaw]')
    if not 0.0 < float(data['free_thresh']) < float(data['occupied_thresh']) < 1.0:
        raise MapFileError('占用阈值无效')
    hashes = {}
    for item in (yaml_path, image_path):
        hashes[item.name] = hashlib.sha256(item.read_bytes()).hexdigest()
    return {'yaml': yaml_path, 'image': image_path, 'width': width,
            'height': height, 'resolution': float(data['resolution']), 'hashes': hashes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('map_yaml', type=Path)
    args = parser.parse_args()
    try:
        result = validate(args.map_yaml)
    except (OSError, yaml.YAMLError, TypeError, MapFileError) as error:
        print(f'M5-W4地图文件检查失败：{error}')
        return 1
    print('M5-W4地图文件检查通过')
    print(f"- 图像：{result['width']}x{result['height']}，分辨率{result['resolution']:.3f} m")
    for name, digest in result['hashes'].items():
        print(f'- SHA-256 {name}: {digest}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
