# hermes-agent-company

*[English](README.md) · 한국어*

백그라운드 위임(delegation)을 **역할별로 특화된 서브에이전트들의 작은 회사**로
바꿔 주는 [Hermes](https://github.com/NousResearch/hermes-agent) 플러그인입니다 —
*기획자(planner), 코더(coder), 테스터(tester), 리뷰어(reviewer)* 를 메인 에이전트가
지휘합니다. 코딩 비중이 큰 역할은 [Codex CLI](https://github.com/openai/codex)
(데몬 스레드에서 `codex exec`)에서 돌고, 추론 위주 역할은 메인 모델에서 돕니다.
진행 상황은 실시간으로 채팅 UI로 흘러 들어옵니다 — 현재는 Discord이며, 코어는
플랫폼에 종속되지 않도록 설계돼 있습니다.

전부 **플러그인만으로 설치**됩니다 — **hermes를 포크할 필요가 없습니다.**
(이전 이름은 `subagent_coder`였으나, 단일 코더가 아니라 여러 역할이 협업하는
플러그인이 되었음을 반영해 이름을 바꿨습니다.)

## 역할(Roles)

`delegate_task_background`는 `role` 파라미터를 받습니다. 각 역할은 저마다의
지시문, 도구 모음, 모델 제공자를 가집니다:

| 역할 | 실행 위치 | 도구 | 목적 |
|---|---|---|---|
| `coder` *(기본값)* | Codex CLI | terminal, file | 코드 구현 / 변경 |
| `planner` | 메인 모델 | file (terminal 없음) | 조사한 뒤 구현 계획 작성 |
| `tester` | Codex CLI | terminal, file | 테스트 작성·실행, 통과/실패 보고 |
| `reviewer` | 메인 모델 | file, **pii** | 검토 + 배포 전 유출된 비밀정보/PII 스캔 |

메인 에이전트는 자신의 페르소나에 따라 역할을 고릅니다: 불명확하거나 큰 작업엔
`planner`, 명확한 구현엔 `coder`, 검증엔 `tester`, 그리고 **무엇이든 출시 전에
게이트를 걸기 위해** `reviewer`를 씁니다. 리뷰어의 `scan_pii` 도구는 hermes 자체의
편집(redaction) 엔진을 재사용해, 워크스페이스 전반에서 이메일·키·토큰·IP·실제
홈 경로를 찾아 표시합니다.

## 무엇을 더해 주는가

- **`delegate_task_background` 도구** (`role` 파라미터 포함) — 메인 턴을 막지 않고
  작업을 분리된(detached) 서브에이전트 실행으로 넘깁니다.
- **오케스트레이션 도구** — `coder_status`(실행 중/완료된 작업 + 남은 용량)와
  `cancel_coder`. 범위는 에이전트가 띄운 실행으로 한정되며, `/code` 슬래시 실행은
  제외됩니다.
- **완료 깨우기(Completion wake)** — 서브에이전트가 끝나면 합성된 내부 메시지가
  메인 세션에 주입되어, 에이전트가 깨어나 의존 후속 작업을 이어서 잡을 수
  있습니다. hermes 기본 완료 알림을 그대로 따르므로 — **폴링이 없습니다.**
- **`scan_pii` 도구** — 리뷰어 전용의 배포 전 비밀정보/PII 스캔.
- **`codex-exec` 모델 제공자** — Codex CLI를 OpenAI 채팅 완성(chat-completion)
  형태로 감쌉니다.
- **Discord 오버레이** — `/code <task>`로 결정론적 생성; 실행마다 전용 스레드에
  실시간·디바운스된 진행 상황 표시(planner/reviewer 같은 비-codex 역할 포함);
  후속 메시지는 같은 세션을 이어가고; `stop`/`cancel`로 종료합니다.

## 벤치마크: 단독 vs 협업

역할 편성이 단일 코더 대비 실제로 얼마나 값어치를 하는가? 같은 작업을 두 방식으로
돌렸습니다 — **단독**(코더 하나가 전부 처리) vs **협업**(planner → coder → tester
→ reviewer) — **같은 모델**로 돌려서 유일한 변수가 워크플로우가 되도록 했습니다.
시간, 토큰, 사람의 개입 횟수, 그리고 출력 품질(테스트, 숨은 엣지 케이스, 픽스처
데이터에 심어둔 비밀정보가 결과물로 유출됐는지)을 측정했습니다.

| 작업 | 단독 | 협업 | 결론 |
|---|---|---|---|
| **쉬움** — 작은 유틸리티 4개 | 테스트 16개 통과, 유출 0 · 토큰 ~107K · 9.5분 | 동일 품질 · 토큰 ~803K · 26분 | 협업 = **순수 오버헤드** (같은 결과에 토큰 약 7.5배) |
| **어려움 + 민감** — 까다로운 엣지 케이스(윤년, IPv4 옥텟)를 가진 검증기 6개 + 픽스처에 묻어둔 실제 같은 API 키 | **미완성**(검증기 1개 누락)에 **API 키가 테스트로 유출됨** · 토큰 ~184K · 4.4분 | **완성(6/6), 리뷰어가 키를 제거**, 테스트 85개 · 토큰 ~453K · 30분 | 비용 약 2.5배에도 협업 **승리** |

**핵심:** 협업 프리미엄(토큰 약 2.5~7.5배)이 *항상* 정당화되는 건 아닙니다. 쉽고
민감도 낮은 작업에서는 단일 코더가 같은 결과를 더 빠르고 싸게 냅니다. 어렵거나
민감한 작업에서는 특화된 **테스터**(누락을 잡음)와 **리뷰어**(유출된 비밀정보/PII를
잡음)가, 빠르지만 망가진 초안을 출시 가능한 결과물로 바꿔 주는 요소입니다.

> 셀당 실행 1회 — 통계적으로 엄밀하지 않은 방향성 지표입니다. 비용은 토큰 기준이며
> (Codex 사용량은 구독제로 청구됩니다).

## 요구 사항

- Hermes(`hermes-agent`) 설치.
- `PATH`에 `codex` CLI.
- `~/.codex/auth.json`의 Codex 인증(`codex login` 실행).
- Discord 기능용: hermes에 설정된 Discord 봇 토큰(`DISCORD_BOT_TOKEN`)과
  `discord.py`(hermes 메시징 의존성).

## 설치

```bash
hermes plugins install bykim0119/hermes-agent-company
hermes plugins enable agent_company
```

이 명령은 리포를 `~/.hermes/plugins/agent_company/`로 클론합니다. hermes는 다음
시작 시 이를 발견해 `register(ctx)`를 실행합니다.

업데이트 또는 제거:

```bash
hermes plugins update agent_company
hermes plugins remove agent_company
```

## 사용법

- **슬래시 명령:** `/code add a /health endpoint and a test for it`
- **자연어:** hermes에게 코딩 작업을 요청하면, `delegate_task_background`를 골라
  스레드를 엽니다.
- **역할:** 필요한 도움의 형태로 요청하세요 — 예: "먼저 계획 세워"(planner), "이제
  구현해"(coder), "테스트로 검증해"(tester), "게시 전에 유출 없는지 확인해"(reviewer).
- **후속:** 실행 스레드에 답장하면 — 같은 세션을 이어갑니다.
- **취소:** 스레드에 `stop`(또는 `cancel`)을 보냅니다.

## 여러 서브에이전트 오케스트레이션

여러 작업으로 이뤄진 일이라면, 메인 에이전트는 여러 서브에이전트를 돌리고 의존
작업을 연결할 수 있습니다:

- **독립** 작업은 병렬로 발사 — 한 턴에서 `delegate_task_background`를 여러 번
  호출합니다.
- **의존** 작업은, 자신이 의존하는 완료 깨우기가 도착한 뒤에만 위임됩니다:
  에이전트는 턴을 끝내고, 각 실행이 끝날 때 깨어나서, 다음 단계를 위임합니다.
- `coder_status`는 활성 실행과 남은 용량을 보고하며(용량은
  `HERMES_CODER_MAX_CONCURRENT`), `cancel_coder`는 잘못 가고 있는 실행을 멈춥니다.

> **용량 관련 참고:** 완료된 실행이 현재는 게이트웨이가 재시작될 때까지 동시 실행
> 상한에 계속 잡히므로, 여러 역할을 띄우는 긴 협업은 도중에 슬롯을 소진할 수
> 있습니다. 고쳐지기 전까지는 `delegation.coder.max_concurrent`를 올리세요(설정
> 변경은 재시작 없이 적용됩니다).

### 메커니즘 vs 에이전트의 역할

플러그인은 **메커니즘**(생성 / 관찰 / 취소 / 깨우기)과 **역할 카탈로그**를
제공합니다. *무엇을* 병렬화할지, 특정 단계에 *어떤 역할*을 쓸지는 **결정하지
않습니다** — 그것은 에이전트의 **페르소나 / 시스템 프롬프트**가 지배하며, 이는
당신의 hermes 설정(`~/.hermes/SOUL.md` 또는 그에 준하는 것)에 있고 **이 플러그인에
있지 않습니다.**

실제로 에이전트는 페르소나가 그렇게 시킬 때만 규율 있는 오케스트레이터로
동작합니다. 페르소나에 오케스트레이터 블록을 추가하세요, 예를 들면:

```text
코딩 작업이 주어지면, 너는 프로젝트 오케스트레이터다:
- 직접 코드를 쓰지 마라. delegate_task_background로 위임하고, 맞는 역할을 골라라:
  불명확/큰 작업엔 planner, 명확한 구현엔 coder, 검증엔 tester, 게시 전 유출된
  비밀정보/PII 확인엔 reviewer.
- 요청을 독립 작업과 의존 작업으로 나눠라. 독립 작업은 병렬로 발사하고(한 턴에서
  여러 번 호출); 의존 작업은 그것이 의존하는 완료 알림이 도착한 뒤에만 위임하라.
- 위임한 뒤에는 턴을 끝내고 기다려라 — 완료는 자동으로 도착한다. coder_status를
  루프로 폴링하지 마라; 사용자가 진행 상황을 묻거나 새 위임 전 용량을 확인할 때만
  호출하라.
- 실행이 끝나면 결과를 모아 검증한 뒤 보고하라. reviewer가 확인하기 전에는 절대
  게시하거나 제출하지 마라.
```

> 페르소나 파일은 당신의 hermes 설정의 일부이지 이 리포가 아닙니다. 플러그인을
> 업데이트해도(`hermes plugins update`) 바뀌지 않으니 — 페르소나는 당신 스스로
> 백업해 두세요.

## 설정

조정값은 다음 우선순위로 결정됩니다 **환경변수 → hermes `config.yaml`의
`delegation.coder.<key>` → 기본값**:

| 설정 | 환경변수 | 기본값 |
|---|---|---|
| 유휴 세션 타임아웃(초) | `HERMES_CODER_IDLE_TIMEOUT_S` | `7200` |
| 최대 동시 실행 수 | `HERMES_CODER_MAX_CONCURRENT` | `3` |
| 진행 디바운스(ms) | `HERMES_CODER_DEBOUNCE_MS` | `250` |
| Discord DM 허용 | `DISCORD_ALLOW_DMS` | `true` |

## 개발

이 패키지는 **플랫(flat) 레이아웃**입니다 — `__init__.py`와 그 형제 모듈들이 리포
루트에 있는데, 이는 `hermes plugins install`이 클론의 리포 루트에서 플러그인을
로드하기 때문입니다. 테스트는 그 플랫 패키지를 `agent_company`로 로드합니다
(`tests/conftest.py` 참고). `codex_*` 접두사 파일들은 Codex CLI를 감싸고,
역할/오케스트레이션 모듈은 `roles.py`, `orchestration.py`, `event_bus.py`,
`sessions.py`, `config.py`, `progress_formatter.py`입니다.

테스트는 hermes 기본 모듈(`run_agent`, `tools.*`, `gateway.*`)을 임포트하고
몽키패치하므로, hermes가 임포트 가능해야 합니다:

```bash
pip install -e ".[dev]"   # 또는 hermes-agent를 임포트 가능하게 해 두세요
pytest
```

## 라이선스

상위(upstream) hermes-agent 프로젝트를 참고하세요.
