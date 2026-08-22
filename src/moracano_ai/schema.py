from pydantic import BaseModel


class Syllable(BaseModel):
    text: str
    start: float
    end: float
    pitch_trend: str


class HapticEventParameter(BaseModel):
    ParameterID: str
    ParameterValue: float


class HapticEvent(BaseModel):
    EventType: str
    Time: float
    EventDuration: float
    EventParameters: list[HapticEventParameter]


class HapticCurvePoint(BaseModel):
    Time: float
    ParameterValue: float


class HapticParameterCurve(BaseModel):
    ParameterID: str
    Time: float
    ParameterCurveControlPoints: list[HapticCurvePoint]


class HapticPatternItem(BaseModel):
    Event: HapticEvent | None = None
    ParameterCurve: HapticParameterCurve | None = None


class HapticPattern(BaseModel):
    Version: int = 1
    Pattern: list[HapticPatternItem]


class AnalyzeInput(BaseModel):
    prompt: str


class AnalyzeOutput(BaseModel):
    avg_pitch: float
    pitch_std: float
    pitch_range: float
    pitch_slope_end: float
    syllable_count: int
    avg_duration: float
    duration_std: float
    npvi: float
    speaking_rate: float
    labels: list[str]
    pca_coord: list[float]
    syllables: list[Syllable]
    haptic_pattern: HapticPattern
