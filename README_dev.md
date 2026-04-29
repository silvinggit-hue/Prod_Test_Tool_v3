# Prod_Test_Tool_v3

## 프로젝트 개요
`Prod_Test_Tool_v3`는 IP 카메라 생산/검사/운영 보조를 위한 데스크톱 툴이다.

이 프로젝트는 아래 기준으로 단계적으로 재구축되었다.

- `as_test_tool`의 인증 방식 / 제품 정보 구조 / 제어 방식 / 사용자 친화적 표시 방식을 계승
- `prod_test_tool_v2`는 구조(레이어, 상태관리, 화면 분리, worker 흐름)만 참고
- 구현 코드는 재사용하지 않고 새 구조로 재작성
- 단계별로 구현 → 실행/검증 → 통과 확인 후 다음 단계로 진행
- 프로그램 전체가 멈추지 않는 안정성을 최우선으로 설계

---

## 핵심 목표
- 100~200대 장비를 동시에 다룰 수 있는 생산용 툴
- 장비 1대 실패가 전체 프로그램을 멈추지 않는 구조
- 메인 UI / discovery / add-device / control / video / firmware를 분리된 관심사로 구성
- 일반 생산 직원이 한눈에 이해할 수 있는 단순하고 직관적인 UI 제공

---

## 폴더 기준
이 프로젝트는 아래처럼 **루트 바로 아래에 패키지들이 있는 구조**를 기준으로 한다.

```text
app/
application/
common/
config/
domain/
infra/
ui/
tests/
```

추가로 현재 프로젝트 루트에는 아래 자원이 함께 존재할 수 있다.

```text
PROD.ico
README.md
pyproject.toml
```

---

## 현재 구조 개요

### app
- 실행 진입점
- bootstrap
- runtime
- logging / 예외 hook / QApplication 초기화

### application
- supervisor
- registry
- actor
- scheduler
- poll coordinator
- firmware batch supervisor
- video coordinator
- 각 기능 orchestration

### common
- logging
- display name
- 공통 유틸

### config
- 앱 설정
- scheduler 설정
- UI 설정
- firmware 설정
- 상수 / 아이콘 경로 / 기본 운영값

### domain
- enum
- error
- model
- snapshot
- task / phase1 / firmware model

### infra
- network
- connect/auth
- info/status/control repository
- discovery / setip / reset
- firmware repository
- video profile repository

### ui
- main
- panels
- discovery
- add_device
- video
- firmware
- delegates / mappers / table model

### tests
- smoke / unit / integration

---

## 개발 원칙
이 프로젝트는 아래 원칙으로 진행한다.

1. 한 번에 전체를 크게 만들지 않는다
2. Step 단위로 쪼개서 구현한다
3. 각 Step은 반드시 테스트 가능한 상태여야 한다
4. 기존 동작을 깨지 않는 선에서 기능을 확장한다
5. UI는 개발자 기준이 아니라 **일반 생산 직원 기준**으로 설계한다
6. 장비/영상/펌웨어 실패는 개별 단위로 격리한다
7. 메인 프로그램 전체 크래시는 허용하지 않는다

---

# Step 진행 총정리

---

## Step 0 — 프로젝트 뼈대 + 최소 실행 골격

### 목적
Step 0의 목표는 아래를 만족하는 최소 실행 골격을 만드는 것이다.

- 프로젝트 뼈대 생성
- 최소 실행 가능한 app entry
- bootstrap
- logging 초기화
- 전역 예외 hook
- 빈 메인 윈도우 실행
- smoke test 1개

### 주요 결과
- `app/main.py`
- `app/bootstrap.py`
- `app/runtime.py`
- `config/constants.py`
- `common/logging/logging_config.py`
- `tests/smoke/test_bootstrap_smoke.py`
- `pyproject.toml`

### 핵심 정리
- `Bootstrap.build()`로 앱 객체와 메인 윈도우를 조립하는 구조 확립
- console + file logging 기본 구성
- root handler 중복 방지
- 전역 예외 hook 연결
- PyQt5 기준 최소 실행 확인

### 상태
- 완료

---

## Step 1 — 공통 설정 / 도메인 모델 / 표시명 / 오류 타입

### 목적
앱 전역에서 사용하는 설정값, enum, snapshot, 표시명 규칙을 고정한다.

### 주요 내용
- 공통 설정 파일 구성
- display name mapping 1차본
- 장비 상태 / 앱 모드 / firmware 상태 enum 정리
- snapshot / batch model / task model 정리
- 오류 타입 정리

### 반영된 운영 기준
- 기본 펌웨어: `admin / 123`
- TTA: `admin / !camera1108`
- Security 3.0: `TruenTest / !Camera1108`

### 주요 결과
- `config/app_settings.py`
- `config/scheduler_settings.py`
- `config/ui_settings.py`
- `config/firmware_settings.py`
- `domain/enums/*`
- `domain/errors/*`
- `domain/models/*`
- `common/display/*`

### 상태
- 완료

---

## Step 2 — 공통 네트워크 + 인증 + 비밀번호 변경 + Security 3.0

### 목적
실장비 1대 기준으로 최종적으로 `ReadParam(SYS_VERSION)`까지 성공하는 연결 축을 만든다.

### 주요 내용
- base candidate 처리
- root path candidate 처리
- auth scheme 처리 (`none`, `basic`, `digest`)
- 초기화/운영 비밀번호 판단
- 자동 비밀번호 변경
- Security 3.0 bootstrap
- 최종 `SYS_VERSION` read 성공

### 핵심 특징
- probe 우선 평가
- fallback 에러 덮어쓰기 방지
- 초기화 직후 경로와 이미 변경된 장비 직접 접속 경로 분리
- factory reset 후보 반영
- transport miss / auth fail / policy fail 구분

### 주요 결과
- `infra/network/http_client.py`
- `infra/network/digest_auth.py`
- `infra/network/session_factory.py`
- `infra/network/camera_http_client.py`
- `infra/network/probe.py`
- `infra/network/security3.py`
- `application/services/connect_service.py`
- `scripts/phase1_connect_smoke.py`

### 상태
- 완료

---

## Step 3 — info / status / control / firmware repository

### 목적
Step 2 연결 결과를 바탕으로 실제 장비 정보 조회 / 상태 조회 / 제어 / firmware 단건 repository를 구성한다.

### 주요 내용
- info repository
- status repository
- control repository
- video profile repository
- firmware repository

### 핵심 특징
- `Phase1Response`, `CameraHttpClient` 재사용
- repository 단위로 관심사 분리
- 이후 actor/scheduler/UI에서 재사용 가능한 구조 확보

### 주요 결과
- `infra/device/info_repository.py`
- `infra/device/status_repository.py`
- `infra/device/control_repository.py`
- `infra/device/video_profile_repository.py`
- `infra/firmware/firmware_repository.py`

### 상태
- 완료

---

## Step 4 — DeviceRegistry / DeviceActor / TaskScheduler / PollCoordinator / UiUpdateBus / AppSupervisor

### 목적
메인 런타임의 백엔드 실행 구조를 고정한다.

### 주요 내용
- `DeviceRegistry`
- `DeviceActor`
- `TaskScheduler`
- `PollCoordinator`
- `UiUpdateBus`
- `AppSupervisor`

### 핵심 특징
- per-device inflight = 1
- connect prerequisite 반영
- registry가 canonical snapshot 저장소 역할
- hot / warm polling 분리
- lane / priority 기반 scheduler
- UI 갱신은 batch / debounce 구조

### 주요 결과
- `application/core/device_session.py`
- `application/core/device_registry.py`
- `application/core/device_actor.py`
- `application/core/task_scheduler.py`
- `application/core/poll_coordinator.py`
- `application/core/ui_update_bus.py`
- `application/core/app_supervisor.py`
- `application/core/command_factory.py`

### 상태
- 완료

---

## Step 5 — 메인 UI 최소 버전

### 목적
백엔드와 연결되는 최소 GUI 흐름을 확보한다.

### 주요 내용
- device table
- connect panel
- info summary
- status summary
- control panel 핵심 버튼
- log / result panel
- supervisor / registry / ui update bus 연결

### 핵심 특징
- snapshot 기반 렌더링
- table 중심 운영
- connect → row update → info/status 반영 → control → log/result 흐름

### 주요 결과
- `ui/main/*`
- `ui/panels/*`
- `ui/mappers/*`
- `ui/delegates/*`

### 상태
- 완료

---

## Step 6 — discovery / add-device / setip / reset 보강

### 목적
이미 구현된 discovery/add-device 구조를 안정화하고, admin 기능을 정리한다.

### 주요 내용
- UDP discovery 보강
- packet parser 정리
- add selected / add all 흐름 안정화
- setip protocol / service 추가
- reset service 추가
- main controller 합류 경로 정리

### 핵심 특징
- discovery는 신규 구현보다 현재 코드 보강 중심
- UI는 복잡도를 늘리지 않고 단순화 유지
- 일반 생산 직원 기준의 직관적 버튼/상태 문구 유지

### 주요 결과
- `infra/discovery/*`
- `infra/reset/*`
- `application/services/discovery_service.py`
- `application/services/setip_service.py`
- `application/services/reset_service.py`
- `ui/discovery/*`

### 상태
- 완료

---

## Step 7 — Control 확장 / UI 탭 재구성

### 목적
기존 backend control capability를 생산용 UI로 끌어올린다.

### 주요 내용
- 메인 우측 영역을 `Connect` 아래 `System / Control` 탭으로 재구성
- `System` 탭: info + status
- `Control` 탭: 단일 제어 / 전체 제어 + 제어 섹터
- `Disconnect Selected` 추가
- v2 기준 추가 control 기능 이식

### 추가 반영 기능
- Air Wiper
- Secondary Video Setting
- Minimum Focus Length
- 485 Sensor
- Shock Sensor

### UI 섹터
- 제어 대상
- 렌즈 / PTZ
- 영상 / 필터
- 장비 설정
- 테스트 준비
- 시스템

### 핵심 특징
- backend 재설계가 아니라 UI 확장 중심
- 단일 제어 / 전체 제어 UX 명확화
- 생산 직원이 한눈에 기능 분류를 이해할 수 있게 구성

### 상태
- 완료

---

## Step 8 — Video Mode / 별도 창 / 10대 단위 스트림 표시

### 목적
별도 Video 창에서 장비 영상을 직관적으로 확인할 수 있게 한다.

### 주요 내용
- 메인에서 Video 창 열기
- 별도 `QMainWindow`로 video 운영
- checked / selected / focused 기준 target 해석
- 현재 페이지 10대만 스트림 활성화
- page 이동
- 더블클릭 fullscreen / ESC 해제
- 타일 오류 격리

### 핵심 특징
- 영상은 메인 내부가 아니라 별도 창
- 일반 장비 / TCS 멀티채널 RTSP profile 규칙 재사용
- single mode 기본 profile / batch mode 기본 profile 정책 반영
- 한 타일 오류가 전체 메인/비디오 창을 죽이지 않도록 설계

### 상태
- 완료

---

## Step 9 — Firmware Mode / 별도 창 / batch 운영

### 목적
펌웨어 작업을 메인과 분리된 별도 창에서 batch 단위로 수행한다.

### 핵심 운영 기준
- 일반 poll/control/connect와 섞지 않는다
- firmware 창은 메인과 별도 `QMainWindow`
- 선택 → 파일 지정 → 시작 → 상태 확인 → 실패 재시도 흐름이 직관적이어야 함
- 일부 장비 실패가 전체 batch나 전체 프로그램을 멈추면 안 됨

### 성공 판정 기준
이번 Step 9에서는 아래를 주 판정 로직에서 제거한다.

- before_version 읽기
- after_version 비교
- verifying 단계

대신 성공 기준은 아래다.

> 업로드 후 연결이 한 번 끊기고, 이후 5초 간격 reconnect polling에서 `ReadParam(SYS_VERSION)` API 요청이 성공하면 완료

### reconnect polling 기준
- 고정 대기 후 1회 확인 방식 사용 금지
- **5초 간격 polling**
- **180초 timeout**
- probe 기준은 단순 ping이 아니라 **`ReadParam(SYS_VERSION)` API 성공 여부**
- reconnect 성공 시 즉시 완료
- timeout 초과 시 실패

### 상태 흐름
- `queued`
- `upload_pending`
- `uploading`
- `rebooting`
- `reconnecting`
- `success`
- `failed`

### UI 문구 기준
- `대기`
- `업로드 준비`
- `업로드 중`
- `재부팅 중`
- `다시 연결 확인 중`
- `완료`
- `실패`

그리고 reconnecting 중에는:
- `다시 연결 확인 중 (1/36)`
- `다시 연결 확인 중 (2/36)`
처럼 현재 몇 번째 확인인지 표시한다.

### 현재 상태
- 설계 확정
- 구현 진행 중

---

## 현재 진행 상태 요약

### 완료된 단계
- Step 0
- Step 1
- Step 2
- Step 3
- Step 4
- Step 5
- Step 6
- Step 7
- Step 8

### 진행 중
- Step 9 Firmware Mode

---

## 현재 구현 구조 요약

### 메인 런타임
- `AppSupervisor`
- `TaskScheduler`
- `DeviceRegistry`
- `DeviceActor`
- `UiUpdateBus`
- `PollCoordinator`

### 메인 UI
- MainWindow
- discovery
- add-device
- connect
- info/status
- control
- video

### Video
- 별도 창
- 10대 단위 페이지
- double-click fullscreen
- 타일 단위 오류 격리

### Firmware
- 별도 창 방향 확정
- batch supervisor / reconnect polling 방식 확정
- 구현 진행 중

---

## 아이콘 정책
프로젝트 루트 최상위의 `PROD.ico`를 공통 아이콘으로 사용한다.

적용 범위:
- 앱 기본 아이콘
- 각 개별 창 아이콘
- 빌드 시 exe 아이콘

---

## 빌드
현재 기본 빌드는 아래 명령어를 기준으로 한다.

```bash
pyinstaller --noconfirm --clean --windowed --name Prod_Test_Tool_v3 --icon=PROD.ico app/main.py
```

onefile 빌드가 필요하면 아래를 사용한다.

```bash
pyinstaller --noconfirm --clean --onefile --windowed --name Prod_Test_Tool_v3 --icon=PROD.ico app/main.py
```

---

## 개발/운영 원칙 재확인
이 프로젝트는 아래 원칙을 계속 유지한다.

- 기능은 Step 단위로 추가한다
- 각 Step은 테스트 가능한 단위여야 한다
- 기존 동작을 가능한 한 깨지 않고 확장한다
- UI는 생산 직원 기준으로 단순하고 명확해야 한다
- 장비 1대 실패 / 타일 1개 실패 / job 1개 실패가 전체 프로그램을 멈추게 하면 안 된다
- 메인 / video / firmware는 서로 느슨하게 연결된 별도 운영 축으로 유지한다

---
## 다음 단계
다음 작업은 **Step 9 Firmware Mode 구현 완료**다.

목표:
- 메인에서 Firmware 창 열기
- 대상 장비 선택
- `.tus` 파일 선택
- batch 시작
- row 단위 상태 갱신
- 5초 간격 reconnect polling
- failed only retry
- 메인과 자연스러운 refresh 연동
"""

new = """## 현재 개발 상태
현재 기준으로 핵심 개발은 완료된 상태다.

완료 범위:
- main / backend / discovery / add-device / control / video / firmware 구조 구현
- 기본 실행 흐름과 생산용 UI 구성 완료
- 단계별 재구축 목표 달성

## 이후 진행 방향
이제부터는 **현장 테스트 중심 단계**로 진행한다.

주요 방향:
- 실제 생산 현장에서 장비 연결 / 제어 / 영상 / 펌웨어 동작 검증
- 현장 환경에서 발생하는 세부 오류 수정
- 운영 중 발견되는 예외 케이스 보강
- 생산 직원 요청 기반의 소규모 기능 추가
- UI 문구 / 버튼 배치 / 흐름의 사용성 미세 조정

## 운영 보강 원칙
이후 수정은 아래 원칙으로 진행한다.

- 기존 핵심 구조를 크게 흔들지 않는다
- 현장 이슈는 재현 가능하게 기록하고 단계적으로 반영한다
- 장비 1대 오류가 전체 프로그램에 영향 주지 않도록 유지한다
- 신규 기능은 실제 운영 필요성이 확인된 것부터 우선 반영한다
- UI 변경은 복잡도 증가보다 직관성 개선을 우선한다

## 비고
즉, 현재 프로젝트는 **신규 큰 구조 설계 단계가 아니라 운영 검증 / 오류 보정 / 기능 보강 단계**에 들어간 상태다.
"""