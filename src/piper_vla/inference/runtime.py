"""향후 ROS2 adapter의 20Hz action chunk 실행 상태를 담을 모듈이다.

정책 서버의 checkpoint 복원과 WebSocket 제공은 policy_server.py에 구현됐다. 로봇
발행 runtime은 서버 지연 측정과 안전 검증이 끝난 뒤 별도 ROS2 process로 구현한다.
"""
