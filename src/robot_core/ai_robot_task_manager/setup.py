from glob import glob
import os

from setuptools import find_packages, setup


package_name = 'ai_robot_task_manager'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='ai_robot maintainers',
    maintainer_email='maintainer@example.com',
    description='M6非AI结构化任务管理器。',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'task_manager = ai_robot_task_manager.task_manager:main',
        ],
    },
)
