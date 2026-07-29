#include "ai_robot_cpp_demo/status_message.hpp"
#include "gtest/gtest.h"

TEST(StatusMessage, DescribesReadyCppNode)
{
  EXPECT_EQ(ai_robot_cpp_demo::make_status_message(), "ai-robot M0 C++ node ready");
}
