#include <chrono>
#include <memory>

#include "ai_robot_cpp_demo/status_message.hpp"
#include "rclcpp/rclcpp.hpp"
#include "std_msgs/msg/string.hpp"

using namespace std::chrono_literals;

class StatusPublisher : public rclcpp::Node
{
public:
  StatusPublisher()
  : Node("cpp_status_publisher")
  {
    publisher_ = create_publisher<std_msgs::msg::String>("m0/cpp_status", 10);
    timer_ = create_wall_timer(500ms, [this]() {
      std_msgs::msg::String message;
      message.data = ai_robot_cpp_demo::make_status_message();
      publisher_->publish(message);
    });
  }

private:
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr publisher_;
  rclcpp::TimerBase::SharedPtr timer_;
};

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<StatusPublisher>());
  rclcpp::shutdown();
  return 0;
}
