## 2026-08-22 — AI 모듈 아키텍처 설계 확정

JunctionX Korea 2026 · moracano(경상북도 방언 Dialect Root) 프로젝트의 AI 분석 파이프라인을 처음부터
설계했다. 원래 3갈래(ASR / Prosody Analyzer / Voice Embedding) 아키텍처에서 시작해, 3일 해커톤 스코프에
맞춰 프로소디 단일 갈래로 축소했다.

- **5개 기능 블록으로 정리**: ① 탐색·추천(단어 랭킹, 예시문장 선택) ② Acoustic Speech Analysis(음절
  분할, 피치/길이/리듬 추출) ③ Dialect Root 생성(라벨 생성, Similar Voices, PCA 뿌리 방향) ④ Voice
  Experience(음성재생/억양시각화/햅틱, 순수 렌더링) ⑤ 구조화된 아카이브 & 공개 인프라(Supabase 저장 +
  조회 API/MCP).
- **ASR 제거** (`docs/adr/0001`): 프롬프트 텍스트가 이미 정해져 있으므로 사용자 발화를 전사할 필요 없이,
  음향 에너지/피치 피크로 음절 경계만 직접 탐지하는 방식으로 대체. 사투리→표준어 오보정 리스크도 함께
  해소됨.
- **Voice Embedding 제거** (`docs/adr/0002`): Similar Voices와 PCA 뿌리 방향의 입력을 임베딩 벡터에서
  이미 계산되는 프로소디 특징 벡터(평균피치/피치표준편차/평균길이/길이표준편차)로 대체. 이 시점부터
  파이프라인에 딥러닝 모델이 하나도 남지 않음 — 전부 신호처리(`librosa`/`parselmouth`) + 통계(PCA 1회
  피팅) + 규칙(임계값)으로 구성.
- **역할 분담(AI 1명 + 백엔드 1명)**: AI가 블록1·2·3의 계산 로직(+AI-Hub 전처리)을 함수/FastAPI 서비스로
  만들고, 백엔드는 Supabase 스키마·Storage·CRUD·오케스트레이션을 담당. 경계면은 `analyze` 응답 JSON
  스키마 하나로 고정 — 이것만 먼저 합의하면 두 사람이 즉시 병렬 작업 가능.

### 기능 명세서 (Notion 원본 기준)

| 기능명 | API |
|---|---|
| 1. 방언 Challenge | `/api/challenges/today` |
| 2. 녹음 전 지역 입력 (지도 UX) | (음성 CRUD시 통합) |
| 3-1. 음성 녹음 | `/api/voices` |
| 3-2. 음성 저장 (CRUD) | `/api/voices/{id}` |
| 3-3. 음성 분석 (Pitch, Duration, Rhythm) | `/api/voices/{id}/analyze` |
| 4-1. 뿌리 생성 | (API 없음 — 3-3 응답을 클라이언트에서 규칙 계산) |
| 4-2. 햅틱 표현 | (API 없음 — 3-3 응답을 클라이언트에서 렌더링) |

기능명 앞자리 번호는 위 5블록의 ①②③④에 대응한다: 1→블록①, 3-1/3-2→블록⑤(저장), 3-3→블록②,
4-1→블록③, 4-2→블록④.

### Next

- `POST /api/voices/{id}/analyze` 응답 스키마에 맞는 mock 샘플 3개 작성 (백엔드가 실제 분석 로직 없이
  CRUD/프론트 연동 먼저 끝낼 수 있도록).
- AI-Hub 경상북도 방언 데이터가 시군(포항/안동/대구권 등) 단위로 지역 라벨을 갖고 있는지 확인 —
  Similar Voices/숲 단위 시각화가 이 세분화 여부에 달려 있음.
- 라벨 임계값(Rising Intonation 등)과 PCA 변환행렬을 AI-Hub 레퍼런스 코퍼스로 사전 피팅하는 전처리
  스크립트 작성.
- 충청도 관련 요소는 이 프로젝트 범위에 없음(이전 "경상도 vs 충청도 대결" 버전의 잔재였음, 삭제 확인됨) —
  경북 내부 시군 다양성에만 집중.

## 2026-08-22 — 서버 데이터 실사 + 스코프 조정

팀 GPU 서버에 이미 받아둔 AI-Hub "한국어 방언 발화 데이터(경상도, datasetKey 119)"를 실제로 확인한 결과,
지역 메타데이터가 **광역 단위(부산/대구/울산/경남/경북)까지만** 있고 시군(포항/안동/경주 등) 단위가 없음을
확인했다. 경북 출생 화자 발화량도 현재 다운로드분 기준 약 245시간으로 전체의 일부에 불과.

- **Similar Voices 기능 제거 (팀 결정)**: 기획서(`docs/spec.md`, 결과 예시 섹션)엔 "Similar Voices:
  Yeongdeok, Gyeongju"로 명시돼 있었으나, 시군 단위 데이터가 없어 구현 불가능함을 확인 후 팀 논의를 거쳐
  MVP에서 제외하기로 결정. `mocks/analyze-response-samples.json`,
  `mocks/analyze-response-with-syllables.json`에서 `similar_regions` 필드 삭제.
- **음절 타이밍 방식 재검토**: 에너지 피크 기반 음절 분할은 정합성이 약하다는 문제 제기 → ASR(Whisper)
  대신 **강제정렬(forced alignment)**로 전환 검토 중 (제시어 텍스트를 이미 아니까, 사전학습 한국어
  wav2vec2 CTC 모델 + `torchaudio` 강제정렬로 텍스트-오디오 시간 매핑만 수행, 전사/학습 불필요). 서버에
  이미 있는 MFA 정렬 결과물과 같은 계열의 접근.
- **온디바이스(CoreML) 검토 후 보류**: wav2vec2→CoreML 변환 자체는 반나절~하루면 되지만, CTC 강제정렬
  알고리즘을 Swift로 재구현하고 오디오 전처리를 동일하게 맞추는 작업까지 합치면 2~3일이 걸려 3일
  해커톤 스코프를 넘음. 서버(Docker, 모델 상시 로드) 방식으로 진행하기로 함.
- **Voice Experience용 syllables 필드 추가 확정**: `text`/`start`/`end`/`pitch_trend`/`haptic`(AHAP
  포맷) 구조로 프론트(iOS, Core Haptics)와 합의 완료. `haptic`은 `CHHapticPattern(dictionary:)`에 바로
  넣을 수 있는 AHAP 구조(Version/Pattern/Event/ParameterCurve) 그대로 사용.

### Next

- 강제정렬 파이프라인(wav2vec2 CTC + torchaudio forced_align) 프로토타입 작성, parselmouth 설치.
- 서버에 이미 있는 MFA 결과물(`mfa_work/`)을 레퍼런스 코퍼스 전처리에 재사용할 수 있는지 확인.
- Similar Voices를 완전히 뺄지, 광역 단위(경북 vs 타 시도)로 축소해서 부활시킬지는 추가 논의 여지 있음
  — 지금은 제거 상태로 진행.

## 2026-08-22 — AI 서비스 프로토타입 구현 + 실제 검증

`uv`로 `src/moracano_ai/` 패키지 스캐폴드 생성, 강제정렬 기반 분석 파이프라인을 실제로 구현하고
end-to-end로 검증했다.

- **모듈 구성**: `align.py`(wav2vec2 CTC 강제정렬), `prosody.py`(parselmouth 피치 추출),
  `features.py`(9개 피처 계산), `labels.py`(임계값 기반 라벨), `haptic.py`(AHAP 패턴 생성),
  `direction.py`(PCA 자리 채우는 임시 정규화 좌표), `service.py`(FastAPI `/analyze`), `schema.py`
  (pydantic 응답 모델).
- **강제정렬 구현 세부**: `kresnik/wav2vec2-large-xlsr-korean` 사용 — vocab을 직접 확인해보니
  **완성형 한글 음절 단위(1205 토큰)**로 토크나이징돼 있어서, 자모 분해 후 재그룹핑하는 추가 단계 없이
  CTC 출력이 곧바로 음절 단위 정렬이 됨(예상보다 단순해짐). `torchaudio.functional.forced_align` +
  `merge_tokens`로 프레임 경로를 음절별 (start, end)로 변환.
- **실제 검증**: macOS `say -v Yuna`로 "뭐라카노" 한국어 TTS 오디오를 합성해 실제 모델로 전체
  파이프라인을 돌려봄 — 강제정렬→피치추출→피처계산→라벨→AHAP 햅틱까지 전부 정상 동작 확인
  (`tests/fixtures/sample.wav`). 순수함수 20개 유닛테스트 전체 통과.
- **레이턴시 측정(CPU, 로컬 맥북 기준)**: 모델 로드(콜드) 최초 1회 ~500초(다운로드 포함, 이후 캐시로
  ~5초), 요청당 강제정렬 처리 시간 약 4.9초 — "녹음 후 몇 초 대기" 목표에 걸쳐 있음. 서버 GPU에서는
  더 빨라질 것으로 예상되나, 실측 필요.
- **의존성 이슈 해결**: `torchaudio.load`가 최신 버전에서 `torchcodec`을 요구해 의존성이 무거워져서,
  오디오 로딩은 `soundfile`로 대체(리샘플링만 `torchaudio.functional.resample` 사용).

### Next

- 서버 GPU에서 실제 레이턴시 재측정 — CPU 4.9초가 기준이면 GPU로 개선 여지 확인.
- 실제 AI-Hub 경북 방언 샘플(TTS 아님)로 정렬 품질 검증 — 지금은 합성 음성이라 실제 방언 발화에서도
  강제정렬이 잘 되는지 미확인.
- 라벨 임계값(`labels.py`의 `DEFAULT_THRESHOLDS`)과 PCA(`direction.py`의 placeholder)를 AI-Hub
  레퍼런스 코퍼스 통계로 교체.
- `POST /api/voices/{id}/analyze` 실제 엔드포인트로 배포(Docker) — 지금은 로컬 FastAPI 앱만 존재.

## 2026-08-22 — 실제 AI-Hub 방언 발화로 강제정렬 파이프라인 검증 (GPU 서버)

팀 GPU 서버(RTX A6000 x4, 48코어)에서 `feat/prosody-extraction`(3bbd3fd)을 받아 `uv sync` 후, AI-Hub 경상도
데이터의 실제 발화로 `forced_align_syllables` → 피처 → 라벨 → AHAP까지 end-to-end 검증했다. 입력은 서버에 이미
있던 MFA 작업물(`/data/aihub/mfa_work/corpus/{young,old}/`)의 발화 단위 wav(세션 wav를 JSON start/end로 잘라둔
것, 20,638개)이고, prompt는 같은 발화의 JSON `dialect_form`(문장부호·`~`·`-x-` 마커 제거). 검증 스크립트는
`scripts/validate_alignment.py`(`uv run python scripts/validate_alignment.py --n 300`).

- **환경**: `uv.lock`의 torch 2.13.0은 PyPI Linux 휠이라 그대로 CUDA 13.0 빌드(`2.13.0+cu130`)로 설치됨. 별도
  인덱스 재설치 불필요, `torch.cuda.is_available() == True`. 모델 캐시 1.2GB, 317M 파라미터, vocab 1,207
  (한글 완성형 1,202 + 특수 5).
- **실제 방언 오디오에서 동작**: 300발화(young 150 / old 150, 화자 연령 10대~60대 이상) 중 252개 정상, 48개(16%)는
  prompt에 vocab 밖 음절이 있어 `ValueError`. 정렬 구간 수 != 음절 수 예외는 0건(CTC 강제정렬 특성상 구조적으로
  발생하지 않음).
- **MFA 정합성(음절 onset, n=4,174 음절)**: 오차 중앙값 29ms, 평균 49ms, 50ms 이내 73%, 100ms 이내 92%. 발화 단위
  MAE 중앙값 39ms, 100ms 초과 발화 7%, 200ms 초과 1%. young/old, 방언 어절 유무에 따른 차이 없음(중앙값 28~32ms).
  MFA 사전에 없어 `spn`으로 처리된 어절(808음절)은 비교에서 제외. 크게 어긋난 케이스는 특정 화자/방언이 아니라
  짧은 발화 + 긴 휴지(`그래서 인제 그`, 1.1s) 또는 말더듬/반복(`어 더 여유로운 생 어 시`)처럼 전사와 실제 발화가
  느슨하게 대응하는 경우.
- **핵심 버그 발견·수정: CTC span은 음절 길이가 아님**. `merge_tokens`가 주는 span은 토큰이 발화되는 1~2프레임
  (20~40ms) 스파이크라, 수정 전 모든 발화에서 `avg_duration`이 0.020~0.026s, `duration_std` 0, `npvi` 0~30으로
  나왔고 Long Vowel / Strong Rhythm 라벨이 한 번도 안 켜졌다(햅틱 EventDuration도 전부 20ms). onset은 MFA와
  잘 맞으므로 각 음절 끝을 다음 음절 onset까지 늘리는 `extend_spans`를 `align.py`에 추가(마지막 음절은 앞
  음절들의 중앙값 길이, 오디오 끝에서 cap). 수정 후 음절 길이 평균 184ms(MFA 167ms), offset 오차 중앙값 33ms,
  100ms 이내 84%. 단, 마지막 음절 offset은 중앙값 132ms로 부정확(발화 끝 늘임은 반영 못 함).
  수정 후 피처: `avg_duration` 중앙값 0.177s(p10 0.136, p90 0.257), `npvi` 48(p10 29, p90 69), `speaking_rate`
  5.6음절/s. 라벨 분포(252발화): Strong Rhythm Variation 171, Rising Intonation 57, Long Vowel Usage 31 →
  `DEFAULT_THRESHOLDS`(npvi 40, duration 0.25)가 실제 분포 대비 낮아 캘리브레이션 필요.
- **음절 수 불일치 / OOV**: 학습 라벨 2,088,717발화 기준 마커(`#이름#`, `(())`, `{laughing}` 등) 포함 5.1%는
  그대로는 정렬 불가. 마커 없는 1,981,354발화 중 14.1%가 vocab 밖 음절 포함(1.5% 음절 토큰). 최다 OOV는 **`쫌`**
  (15만 회, 전체 방언 어절 태그의 32%)이고 `괜`·`깐`·`걔`·`툰`·`걍`·`쌤`·`땜`·`꽤` 등 표준어 음절도 빠져 있음.
  자모 분해 후 된소리→예사소리, ㅒ→ㅐ 등, 받침 제거 순으로 대체하면 OOV 토큰의 96%를 vocab 안 음절로 매핑
  가능(쫌→쪼, 괜→괘, 걔→개; `걍`·`놔`는 불가). 서비스의 제시어는 고정이므로 제시어 선정 시 vocab 사전 검사로
  회피 가능, 레퍼런스 코퍼스 통계용으로는 fallback 매핑 필요.
- **레이턴시(모델 로드 후, 발화 평균 4.3s)**: GPU 정렬 중앙값 25ms(최대 0.35s), parselmouth 피치+피처 5ms,
  합계 30ms. 같은 서버 CPU(48코어)는 0.27s. 맥북 CPU 4.9s → GPU 30ms로 실시간 서비스 충분. 모델 콜드 로드 33s.
- **피치 피처 의심점**: `pitch_range`가 250Hz 초과인 발화 45%, 300Hz 초과 35%. parselmouth 기본 설정(75~600Hz)
  에서 옥타브 점프/무성 잡음이 섞이는 것으로 보임. `pitch_slope_end`는 19%에서 0(끝 200ms에 유성음 없음), 5%는
  |500Hz/s| 초과. 성별별 `avg_pitch` 중앙값은 여 195Hz / 남 117Hz로 정상.

### Next

- wav2vec2 vs MFA 판단: onset 정합성은 충분(중앙값 29ms)하므로 wav2vec2 유지. MFA 전환은 불필요하되, 마지막
  음절 길이와 발화 끝 늘임이 중요해지면 parselmouth intensity/voicing으로 마지막 음절 끝을 보정하는 방안 검토.
- 피치 안정화: 성별/화자별 floor·ceiling, 옥타브 점프 제거(중앙값 필터), 반음(semitone) 단위로 slope 계산.
- `DEFAULT_THRESHOLDS`·PCA를 AI-Hub 코퍼스 통계로 교체(레퍼런스 피처 추출 시 `scripts/validate_alignment.py`의
  입력 경로·prompt 정제 로직 재사용).
- 제시어 후보는 vocab 검사 통과한 것만 사용; OOV fallback 매핑(`쫌→쪼` 등)을 `align.py`에 넣을지 결정.
- 서버 배포 시 `model.to("cuda")`는 `service.py` lifespan에서 호출해야 함(현재 `load_aligner`는 CPU에 올림).

## 2026-08-22 — 정렬 모델 축소(base 자모 모델) + 피치 2-pass + 임계값 캘리브레이션

앞 세션의 검증 스크립트로 후속 실험을 돌려 세 가지를 바꿨다. 모든 수치는 AI-Hub 경상도 실발화 300개(시드 0)
기준, MFA TextGrid 대비 음절 onset 오차.

- **정렬 모델을 `Kkonjeong/wav2vec2-base-korean`(94M, 자모 vocab 51)으로 교체**. HF의 한국어 CTC 모델을 훑은 결과
  vocab이 완성형 음절인 모델(kresnik large 1,202 / w11wo 300m 1,202 / kresnik 300m 1,074)은 전부 `쫌` 같은 음절이
  빠져 OOV 문제가 같고, 자모 vocab 모델(Kkonjeong base, fleek large)은 완성형을 전부 표현해 OOV가 0. `align.py`에
  자모 분해(`syllable_jamo`)·토큰→음절 재그룹(`group_spans`)을 넣어 두 vocab 유형을 자동 처리한다.

  | 모델 | 파라미터 | 성공 | onset 중앙값 | ≤50ms | ≤100ms | 최악 발화 | 정렬 지연(GPU) |
  |---|---|---|---|---|---|---|---|
  | kresnik large (기존) | 317M | 252/300 (OOV 48) | 29ms | 73% | 92% | 1,117ms | 26ms |
  | Kkonjeong base | 94M | 300/300 | 43ms | 58% | 90% | 272ms | 19ms |
  | Kkonjeong base + 20ms lag 보정 | 94M | 300/300 | **36ms** | 64% | 91% | 272ms | 19ms |

  시드 1로 다른 300개를 돌려도 37ms / 63% / 90%로 같음. 대가: 음절 경계가 large보다 거칠어 `npvi` 중앙값이
  48 → 63으로 올라감(리듬 피처의 절대값이 모델에 종속됨). 정밀도가 더 필요하면 `ALIGNER_MODEL`만 large로 되돌리면
  되고, 그 경우 제시어의 vocab 사전 검사가 필수.
- **CTC onset lag 보정**: 두 모델 모두 MFA 대비 onset이 늦게 찍힘(부호 있는 중앙값 large +15ms, base +21ms).
  `ONSET_LAG_SEC = 0.02`(1프레임)만큼 앞당기자 base 중앙값 43 → 36ms.
- **피치 2-pass(de Looze & Hirst)**: `pitch_contour`를 60~700Hz 1차 추출 → 화자 q25·q75로 floor/ceiling 재설정
  후 2차 추출로 변경. 252발화에서 `pitch_range` > 300Hz 비율 35% → 0%, 반음 범위 중앙값 21.4 → 12.7st, 유성
  구간 비율은 0.70 → 0.68로 유지. `to_pitch_ac`의 octave_jump_cost 조정은 20%까지만 줄어 채택하지 않음.
- **라벨 임계값 캘리브레이션**: 600발화(시드 0+1, young/old 300씩) 분포로 `DEFAULT_THRESHOLDS`를
  rising 30 → 120 Hz/s(p90), long vowel 0.25 → 0.224s(p75), npvi 40 → 75(p75)로 교체. 기존 값으로는
  Strong Rhythm이 94%에서 켜져 변별력이 없었음. 분포: `avg_duration` p50 0.183 / p75 0.224 / p90 0.269,
  `npvi` p50 63 / p75 75 / p90 87, `speaking_rate` p50 5.5, `pitch_slope_end`는 28%가 0(끝 200ms 무성).
- `load_aligner`가 CUDA 있으면 모델을 GPU로 올리도록 변경(`service.py` 수정 불필요). 레이턴시: 정렬 19ms +
  피치·피처 10ms = 발화당 28ms.

### Next

- 마지막 음절 offset(중앙값 130ms 오차)과 발화 끝 늘임: parselmouth intensity/voicing 끝점으로 보정 검토.
- `pitch_slope_end`를 Hz/s 대신 반음/s로 바꿀지 결정(화자 기본 피치에 덜 종속). 계약 스키마 변경이 필요.
- 실제 제시어(짧은 낭독)로 녹음한 샘플이 모이면 임계값·PCA 재캘리브레이션. 현재 값은 대화체 기준.
- 레퍼런스 코퍼스 피처 추출 스크립트(PCA 피팅용)는 `scripts/validate_alignment.py`의 입력 경로·prompt 정제를
  재사용해 작성.

## 2026-08-22 — large 재평가(공정 비교) + 음절 OOV 근사 대체, 기본 모델을 large로 복귀

앞 항목의 large vs base 비교는 large를 lag 보정 전에 잰 것이라 불공정했고, large의 실패 48건은 코드가 아니라
vocab에 `쫌` 등이 없어서였다. 둘 다 바로잡고 같은 코드로 다시 비교했다(300발화 x 시드 0·1, MFA 대비 onset).

- **음절 OOV 근사 대체(`nearest_syllable`)**: 음절 vocab 모델에서 prompt 음절이 vocab에 없으면 된소리→예사소리,
  이중모음 단순화, 받침 제거 순으로 가장 가까운 완성형으로 바꿔 정렬한다(쫌→좀, 괜→괘, 걔→개). 출력 `text`는
  원래 음절 유지. large 실패 48/23건 → 1/0건. 대체가 들어간 발화의 onset MAE 중앙값 46ms(시드 0) / 38ms(시드 1),
  대체 없는 발화 37 / 38ms로 큰 손실 없음.

  | 모델 (같은 코드: lag 보정 + OOV 대체) | 성공 | onset 중앙값 | ≤50ms | ≤100ms | 최악 | 정렬 지연 | npvi p50 |
  |---|---|---|---|---|---|---|---|
  | kresnik large 317M | 599/600 | **29ms** | **80%** | **94%** | 1,097ms | 26ms | 47 |
  | Kkonjeong base 94M | 600/600 | 36ms | 64% | 91% | 272ms | 19ms | 63 |

- **기본 모델을 large로 되돌림**. 지연 차이(7ms)는 서비스에 무의미하고 onset 정밀도 차이(50ms 이내 80% vs 64%)와
  리듬 피처 안정성(npvi 분포가 더 타이트)이 더 중요하다. base는 `ALIGNER_MODEL` 한 줄로 전환 가능(코드 변경 없음).
  large의 약점은 짧은 발화 + 긴 휴지에서 가끔 크게 틀어지는 것(최악 1.1s, 발화 단위 MAE > 200ms 1%).
- **임계값을 large 분포로 재캘리브레이션**(599발화): rising 150 Hz/s(p90 148), long vowel 0.22s(p75), npvi 57(p75).
  base 분포 기준 값(120 / 0.224 / 75)은 npvi가 모델 종속이라 그대로 쓰면 Strong Rhythm이 5%만 켜짐.
  분포: `avg_duration` p50 0.180 / p90 0.259, `npvi` p50 47 / p90 67, `speaking_rate` p50 5.6, 끝 기울기 0인 발화 18%.

### Next

- 앞 항목의 Next 그대로(마지막 음절 offset, 반음 기울기, 제시어 낭독 데이터로 재캘리브레이션, PCA 코퍼스 스크립트).
- 짧은 발화 + 긴 휴지 케이스: 정렬 전 앞뒤 무음 트리밍(VAD)으로 large의 최악 케이스가 줄어드는지 확인.
