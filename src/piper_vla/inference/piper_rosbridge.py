"""이 프로젝트가 rosbridge를 사용하지 않는 이유를 남기는 호환 모듈이다.

정확한 RoMaLab dev_e2e_piper 브랜치는 직접 ROS2 DDS 토픽을 제공한다. 실제 client는
ROS2 Humble 환경의 별도 adapter package로 구현하며 rosbridge 연결을 만들지 않는다.
"""
