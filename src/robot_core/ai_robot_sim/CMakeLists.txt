cmake_minimum_required(VERSION 3.8)
project(ai_robot_sim)

find_package(ament_cmake REQUIRED)

install(DIRECTORY config launch worlds
  DESTINATION share/${PROJECT_NAME}
)

install(PROGRAMS scripts/cmd_vel_safety_filter.py
  DESTINATION lib/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(test_sim_assets test/test_sim_assets.py)
  ament_add_pytest_test(test_cmd_vel_safety_filter test/test_cmd_vel_safety_filter.py)
endif()

ament_package()
