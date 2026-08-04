cmake_minimum_required(VERSION 3.8)
project(ai_robot_description)

find_package(ament_cmake REQUIRED)

set(MODEL_CONFIG_SOURCE
  "${CMAKE_CURRENT_SOURCE_DIR}/../../../config/common/robot_model.yaml"
)
set(SENSOR_CONFIG_SOURCE
  "${CMAKE_CURRENT_SOURCE_DIR}/../../../config/common/sensor_model.yaml"
)
if(NOT EXISTS "${MODEL_CONFIG_SOURCE}")
  message(FATAL_ERROR "Missing authoritative model config: ${MODEL_CONFIG_SOURCE}")
endif()
if(NOT EXISTS "${SENSOR_CONFIG_SOURCE}")
  message(FATAL_ERROR "Missing authoritative sensor config: ${SENSOR_CONFIG_SOURCE}")
endif()

configure_file(
  "${MODEL_CONFIG_SOURCE}"
  "${CMAKE_CURRENT_BINARY_DIR}/robot_model.yaml"
  COPYONLY
)
configure_file(
  "${SENSOR_CONFIG_SOURCE}"
  "${CMAKE_CURRENT_BINARY_DIR}/sensor_model.yaml"
  COPYONLY
)

install(DIRECTORY launch urdf
  DESTINATION share/${PROJECT_NAME}
)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/robot_model.yaml"
  DESTINATION share/${PROJECT_NAME}/config
)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/sensor_model.yaml"
  DESTINATION share/${PROJECT_NAME}/config
)

if(BUILD_TESTING)
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(test_description test/test_description.py)
endif()

ament_package()
