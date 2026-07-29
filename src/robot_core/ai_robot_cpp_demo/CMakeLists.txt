cmake_minimum_required(VERSION 3.8)
project(ai_robot_cpp_demo)

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(std_msgs REQUIRED)

add_library(status_message src/status_message.cpp)
target_compile_features(status_message PUBLIC cxx_std_17)
target_include_directories(status_message PUBLIC
  "$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>"
  "$<INSTALL_INTERFACE:include>")

add_executable(status_publisher src/status_publisher.cpp)
target_compile_features(status_publisher PUBLIC cxx_std_17)
target_link_libraries(status_publisher status_message)
ament_target_dependencies(status_publisher rclcpp std_msgs)

install(TARGETS status_message status_publisher
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION lib/${PROJECT_NAME})
install(DIRECTORY include/ DESTINATION include)

if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_status_message test/test_status_message.cpp)
  target_link_libraries(test_status_message status_message)
endif()

ament_package()
