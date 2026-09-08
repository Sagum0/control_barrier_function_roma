# cbf_base_tf

`config/base_cam_extrinsics.yaml`은 형식 확인용 placeholder다. 실측에는
`scripts/measure_base_cam.py`가 만든 YAML 경로를 `extrinsics`로 넘긴다.

```bash
colcon build --packages-select cbf_base_tf
source install/setup.bash
ros2 launch cbf_base_tf base_tf.launch.py extrinsics:=/absolute/path/to/base_cam_extrinsics.yaml
```
