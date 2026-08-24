# moracano backend & AI
![Moracano iOS 앱 음성 분석 데모](docs/assets/moracano-demo.gif)

Moracano는 방언의 단어뿐 아니라 **말할 때 나타나는 높낮이, 길이, 리듬**을 기록하는
온디바이스 음성 AI 프로젝트입니다. 특히 backend & AI 파트는 공공 데이터와 사용자 음성 기록 바탕으로 억양 특성을 시각화하기 위한 데이터를 제공합니다.

사용자가 제시된 방언 문장을 읽으면 On device AI 모델이 음성을 음절 단위로 나누고, 각 음절의 억양과 길이,
리듬을 분석합니다. 분석 결과는 화면에서 글자의 움직임, 진동, 원본 음성으로 표현되며 이후 하나의 구조화된
`Dialect Root`(뿌리 방언)로 저장됩니다.

모든 핵심 분석은 iPhone에서 on device로 실행됩니다.

## 온디바이스 AI 한눈에 보기

![Moracano 온디바이스 음성 AI 처리 단계](docs/assets/moracano-on-device-ai-pipeline-ko.svg)

## AI가 음성을 처리하는 방법

### 1. 알고 있는 문장에서 음절 위치 찾기

Moracano는 사용자가 읽을 제시문을 DB에서 조회하여 사용자에게 제공합니다. 따라서 사용자가 말하는 시점에 이미 알고 있는 문장을 어떻게 발음했는지 분석합니다. 음성 분석은 다음과 같이 이루어 집니다.

wav2vec2 기반 Korean Jamo CTC 모델이 녹음 속 한글 자모의 위치를 찾고, 이를 제시문과 비교해 각 음절의 시작점과 끝점을 계산합니다. 이 과정을 **강제정렬**이라고 합니다.

즉, 무슨 말을 했는지 추측하는 AI 모델이 아니라, **알고 있는 문장을 언제 어떻게
발음했는지 찾는 AI 모델**입니다.

<details>
<summary>강제정렬 기술 세부사항</summary>

- 녹음을 16kHz mono Float32로 맞추고 발화별 음량을 정규화합니다.
- 한글 완성형을 초성·중성·종성 자모로 분해해 `Kkonjeong/wav2vec2-base-korean`의 자모
  vocabulary에 매핑합니다. 이 방식은 `쫌`, `괜`, `걍` 같은 완성형 OOV 문제를 피합니다.
- wav2vec2 CTC의 `log_probs (T, 56)`와 제시문 토큰을 dynamic programming으로 정렬합니다.
- CTC onset이 실제 시작점보다 늦어지는 경향을 줄이기 위해 20ms 보정을 적용합니다.
- 각 음절의 끝은 다음 음절 시작점까지 확장합니다. 마지막 음절은 intensity가 구간 peak보다 20dB
  낮아지는 지점을 발화 끝으로 사용합니다.

구현: `src/moracano_ai/align.py`, `src/moracano_ai/prosody.py`

</details>

### 2. 화자에 맞춰 억양과 리듬 분석하기

사람마다 기본 목소리 높이가 다르므로 음성에 같은 탐색 범위를 적용하면 실제보다 음높이가 두 배 높거나 낮게 측정되는 `octave jump` 문제가 발생할 수 있습니다.

Moracano는 음높이를 두 번 측정합니다. 첫 번째 측정으로 화자의 대략적인 음역을 찾고, 두 번째 측정에서는 그 화자에게 맞는 범위로 다시 분석합니다.

또한 단순한 Hz 값 대신 각 화자의 중앙 음높이를 기준으로 얼마나 올라가고 내려갔는지를 **반음 단위**로 계산합니다. 따라서 목소리가 낮은 사람과 높은 사람도 같은 기준에서 억양을 비교할 수 있습니다. 그리고 짧은 음절과 긴 음절은 같은 변화량도 다르게 들릴 수 있으므로 음절 길이도 함께 고려합니다.

Moracano가 한 번의 발화에서 계산하는 특징은 9개입니다.

| 구분 | 쉽게 설명한 의미 | 실제 필드 |
| --- | --- | --- |
| 음높이 | 평균 높이, 억양의 기복, 전체 음역 | `avg_pitch`, `pitch_std`, `pitch_range` |
| 문장 끝 억양 | 마지막 200ms가 올라가는지 내려가는지 | `pitch_slope_end` |
| 음절 | 실제로 정렬된 음절 수 | `syllable_count` |
| 발음 길이 | 평균 음절 길이와 음절별 길이 차이 | `avg_duration`, `duration_std` |
| 리듬 | 이웃한 음절 사이의 길이 변화 | `npvi` |
| 말하기 속도 | 1초 동안 발음한 음절 수 | `speaking_rate` |

<details>
<summary>운율 분석 기술 세부사항</summary>

첫 번째 F0 탐색은 60–700Hz 범위에서 수행합니다. 유성 프레임의 q25/q75로 화자별
`floor/ceiling`을 구한 뒤 F0를 다시 추출합니다. 피치 변화는 발화 중앙값 F0 기준 반음으로
변환합니다.

음절별 상승·하강·평탄 판정에는 음절 길이 `T`를 반영하는 't Hart glissando threshold를
사용합니다.

```text
0.16 / max(T, 0.08)^2
```

구현: `src/moracano_ai/features.py`, `src/moracano_ai/prosody.py`

</details>

### 3. 숫자를 사람이 이해할 수 있는 특징으로 바꾸기

계산된 음향 값은 사용자가 이해할 수 있는 세 가지 설명으로 변환됩니다.

| 분석 결과 | 의미 | 현재 기준 |
| --- | --- | --- |
| 상승 억양 | 문장 끝이 뚜렷하게 올라감 | `pitch_slope_end > 25 st/s` |
| 긴 음절 | 음절을 비교적 길게 발음함 | `avg_duration > 0.23s` |
| 강한 리듬 변화 | 이웃한 음절 사이의 길이 차이가 큼 | `nPVI > 76` |

Moracano는 AI-Hub 경상도 실제 발화 중 연령대를 균형 있게 구성한 600개 표본을 분석했습니다. 사전학습된 wav2vec2 모델로 음절 위치를 정렬하고, 각 음절의 피치·길이·리듬을 계산했습니다. 이후 실제 발화 분포의 상위 구간을 기준으로 상승 억양, 긴 음절, 강한 리듬 변화의 임계값을 보정했습니다.

정리하자면, 짧은 시간 안에 AI-Hub 3,000시간 전체를 학습하기에는 한계가 있어 딥러닝 강제정렬과 음향 분석, 통계 기반 규칙을 결합한 방식입니다.

구현: `src/moracano_ai/labels.py`, `scripts/calibrate_thresholds.py`

### 4. 분석 결과를 다감각 경험으로 바꾸기

Moracano는 분석 결과를 숫자와 그래프로만 보여주지 않습니다.

- **글자의 움직임**: 음절의 시작점과 길이는 글자가 나타나는 시간이 되고, 억양의 상승과 하강은
  움직이는 방향이 됩니다.
- **햅틱**: 음절 길이는 진동의 지속시간이 되고, 피치 변화는 진동의 질감과 강도 변화가 됩니다.
- **원본 음성**: 사용자는 자신의 실제 발화를 분석 결과와 함께 다시 들을 수 있습니다.
- **Dialect Root**: 지역, 제시문, 음절 타이밍, 피치, 길이, 리듬, 라벨과 AHAP 패턴을 하나의
  구조화된 결과로 연결합니다.

키네틱 타이포그래피와 햅틱은 **같은 음성에서 추출한 동일한 특징을 서로 다른 감각으로 표현한 결과**입니다.

`build_ahap_pattern()`의 출력은 Apple AHAP 구조이므로 iOS에서
`CHHapticPattern(dictionary:)`에 직접 전달할 수 있습니다.

구현: `src/moracano_ai/haptic.py`, `mocks/on-device-analysis-contract.json`

### ML 모델을 온디바이스 전환하기

```mermaid
flowchart LR
    A[Python 기준 모델] --> B[Core ML 변환]
    B --> C[int8 경량화]
    C --> D[iPhone 온디바이스 실행]
```

Python에서 검증한 wav2vec2 모델을 iOS용 Core ML 형식으로 변환한 뒤, 모델 가중치 대부분을
int8로 압축했습니다. 약 189MB였던 fp16 모델은 약 99MB로 줄었고, 음성 특징을 추출하는 앞부분과
최종 자모를 판별하는 `lm_head`는 정확도 저하를 줄이기 위해 fp16으로 유지했습니다.

| 항목 | 적용 내용 |
| --- | --- |
| 입력 | 16kHz 음성, 0.5~15초 |
| 출력 | 시간별 한글 자모 확률 |
| 실행 환경 | iOS 18, Core ML |
| 모델 크기 | fp16 약 189MB → int8 약 99MB |

녹음 길이를 억지로 고정하거나 빈 구간을 채우지 않고, 실제 길이를 유지하는 `RangeDim` 입력을
사용합니다. 음량 정규화도 모델 안에 포함해 Python과 iPhone이 같은 방식으로 음성을 처리하도록
했습니다. 경상도 방언 실발화 600개 기준으로 int8 모델을 검증한 결과 fp32 기준 모델과 비교해 음절 시작
프레임 98.6%, 최종 특징 라벨 99.3%의 일치율을 보였습니다.

변환: `scripts/export_coreml.py` · 경량화 비교: `src/moracano_ai/quant_sim.py`

## Backend

<p align="center">
  <img src="docs/assets/userflow.jpg" alt="Moracano 사용자 흐름" width="640">
</p>

저장 계층은 AI 파이프라인의 입력과 결과를 연결하는 보조 역할을 합니다.

- 기준 방언 사전과 제시문은 공개 읽기 전용 데이터로 제공합니다.
- 원본 사용자 음성은 소유자별 비공개 Storage에 저장합니다.
- 온디바이스 분석 결과는 `voices`에 기록합니다.
- 별도 AI 서버나 서비스 계정 키를 iOS 앱에 두지 않습니다.

### DB 구조

![Moracano 방언 아카이브 데이터 구조](docs/assets/moracano-live-schema-erd-ko.png)

| 테이블 | 저장하는 데이터와 역할 |
| --- | --- |
| `regions` | 사용자가 앱에서 선택하는 경상북도 시·군 정보 |
| `challenges` | 사용자가 읽을 제시문과 음절 수, 참여 지역 수 등의 도전 정보 |
| `auth.users` | 익명 로그인을 포함한 사용자 식별 정보 |
| `voices` | 사용자 녹음의 Storage 경로와 피치·길이·리듬·음절·햅틱 분석 결과 |
| `dialect_regions` | AI-Hub와 방언 사전 데이터의 출처 지역 및 상위·하위 지역 관계 |
| `lemmas` | 여러 방언 표현을 묶는 표준어 표제어 |
| `variants` | 표제어에 연결된 지역별 실제 방언 표현 |
| `utterances` | 방언 문장, 대응하는 표준어 문장, 출처 지역과 음절 정보 |
| `utterance_variants` | 하나의 발화 문장에 포함된 여러 방언 표현의 연결 관계 |
| `exposures` | 사용자에게 이미 노출한 발화 기록으로, 같은 문장의 반복 노출을 관리 |

### 원문 발화에서 사용자 제시 키워드 추출하기

> **한눈에 보는 예시** *(데이터 구조를 설명하기 위한 예시)*
>
> 원문 `"택시 한번 타보소"` → 방언 어절 `타보소` 선택 → `lemma: 타보세요`와
> `variant: 타보소 / 경북` 저장 → 다시 원문과 연결

즉, 사용자는 `타보세요`라는 하나의 기준 키워드에서 경북의 `타보소`처럼 지역마다 다른 표현과
그 표현이 실제로 사용된 문장을 함께 탐색할 수 있습니다.

`lemma`는 사용자에게 제시할 키워드의 **표준형**입니다. Moracano는 원문을 임의로 잘라 키워드를
추측하지 않고, AI-Hub 또는 검수된 corpus가 제공하는 어절 정렬 정보 `eojeol_list`를 사용합니다.

```mermaid
flowchart LR
    A[원문 발화와 eojeol_list] --> B[is_dialect가 true인 어절 선택]
    B --> C[standard를 lemma로 저장]
    B --> D[surface와 지역을 variant로 저장]
    C --> E[원문 utterance와 연결]
    D --> E
```

각 어절에는 표준형 `standard`, 실제 방언형 `surface`, 방언 여부 `is_dialect`가 들어 있습니다.
이 중 `is_dialect=true`인 어절만 선택하며, `standard`는 전 지역에서 공유하는 `lemmas`에,
`surface + region_code`는 지역별 표현인 `variants`에 저장합니다. 이후 두 값을 원문
`utterances`와 연결해 **어떤 문장에서 어떤 방언 표현이 사용됐는지** 다시 확인할 수 있게 합니다.

중복은 `standard_form`이 같은 lemma와 `lemma + surface + region`이 같은 variant를 하나로
합쳐 방지합니다. 또한 AI-Hub·검수 데이터와 사용자 발화의 등장 횟수를 별도로 집계하므로,
향후 자주 등장하거나 데이터가 부족한 키워드를 제시문 후보로 선택할 수 있습니다.

현재 구현은 자유 문장에서 새 표제어를 추론하는 NLP 모델이 아니라, **검증된 어절 정보를 같은
규칙으로 정규화하는 재현 가능한 데이터 파이프라인**입니다.

구현: `scripts/seed_challenge_sentences.py`

## 주요 코드

| 경로 | 역할 |
| --- | --- |
| `src/moracano_ai/align.py` | wav2vec2 CTC 추론과 음절 강제정렬 |
| `src/moracano_ai/prosody.py` | 화자 맞춤 F0, intensity, 반음·glissando·nPVI 계산 |
| `src/moracano_ai/features.py` | 음절 트렌드와 9개 발화 특징 계산 |
| `src/moracano_ai/labels.py` | 실측 임계값 기반 운율 특징 설명 |
| `src/moracano_ai/haptic.py` | 음절 운율을 Apple AHAP으로 변환 |
| `src/moracano_ai/spec.py` | Python–Swift 공통 상수와 허용 오차 |
| `src/moracano_ai/service.py` | 로컬 검증용 `/analyze`; 프로덕션 서버가 아님 |
| `scripts/export_coreml.py` | fp16/int8 Core ML 패키지와 명세 export |
| `scripts/validate_alignment.py` | AI-Hub–MFA 정렬 품질 검증 |
| `scripts/compare_parity.py` | Python–Swift 결과 비교 |
| `scripts/seed_challenge_sentences.py` | 정렬된 corpus를 lemma/variant 사전으로 정규화 |

## 구현 상세

- `direction.py`의 `pca_coord`는 `avg_pitch`와 `npvi`를 정규화한 placeholder입니다. 학습된
  유사도 모델이나 PCA가 아닙니다.
- lemma/variant 생성은 정렬된 `eojeol_list` 기반 정규화입니다.
- 현재 라벨 기준은 대화체 AI-Hub 분포를 사용합니다. 실제 제시문 낭독 데이터가 충분히 쌓이면 다시 조정해야 합니다.
- Python FastAPI는 기준 파이프라인 검증용이며 프로덕션에 배포하지 않습니다.

## 실행과 테스트

```bash
uv sync
uv run pytest tests/
```

로컬 기준 파이프라인을 HTTP로 확인할 때만 FastAPI를 실행합니다.

```bash
uv run uvicorn moracano_ai.service:app
```

Core ML 변환은 `coremltools 9.0`과 지원되는 Torch 버전을 사용하는 격리 환경에서 실행합니다.
생성되는 `artifacts/coreml/` 모델 패키지는 Git에 포함하지 않습니다.

```bash
uv run --isolated --no-project \
  --with torch==2.7.1 \
  --with transformers==4.46.3 \
  --with coremltools==9.0 \
  --with "numpy<2.3" \
  --with soundfile \
  python scripts/export_coreml.py --out artifacts/coreml
```

## AI 문서

- [AI 파이프라인 요약](docs/ai/README.md)
- [온디바이스 계약과 알고리즘 명세](docs/ai/plan.md)
- [실험·모델 선택·검증 기록](docs/ai/progress.md)
- [Track 1 기획과 평가기준](docs/spec.md)
