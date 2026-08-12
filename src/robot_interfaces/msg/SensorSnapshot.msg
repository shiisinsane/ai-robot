# 到点后的基础感知快照。它只表达已有公共数据的可用性和元数据，不表达语义识别结果。
std_msgs/Header header

bool scan_available
uint32 scan_sample_count
float32 scan_min_range_m

bool image_available
uint32 image_width
uint32 image_height
string image_encoding

bool pose_available
geometry_msgs/PoseWithCovarianceStamped pose
