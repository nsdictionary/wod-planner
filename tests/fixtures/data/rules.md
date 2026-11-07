# 테스트 전용 규칙

실제 박스 값이 아니다. `transition_sec_range`는 계산 검증용 가상 값이다.

```json
{
  "class_total_min": 60,
  "workout_max_min": 30,
  "workout_time_basis": {
    "AMRAP": "duration_min",
    "EMOM": "duration_min",
    "FOR_TIME": "time_cap_min"
  },
  "estimation": {
    "transition_sec_range": {"low": 5, "high": 10},
    "fatigue_slowdown_per_round": null
  },
  "recent_days": 7,
  "patterns": ["pull", "push", "legs", "cardio"],
  "supported_formats": ["AMRAP", "EMOM", "FOR_TIME"]
}
```
