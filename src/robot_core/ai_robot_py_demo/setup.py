from setuptools import find_packages, setup

package_name = "ai_robot_py_demo"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Yiyao Yang",
    maintainer_email="3077123336@qq.com",
    description="ai-robot 的 M0 Python 发布节点与单元测试基线。",
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "status_publisher = ai_robot_py_demo.status_publisher:main",
        ],
    },
)
