"""WMO weather interpretation and route risk aggregation.

Conforms to docs/ARCHITECTURE.md §6.5.
Table-driven WMO weather codes and environmental metric severity rules.
"""

from apps.weather.types import WeatherSample

SEVERITY_RANKS = {"none": 0, "low": 1, "moderate": 2, "severe": 3}

# WMO Weather interpretation code (WW) mappings
WMO_CODE_INFO: dict[int, tuple[str, str]] = {
    0: ("Clear sky", "none"),
    1: ("Mainly clear", "none"),
    2: ("Partly cloudy", "none"),
    3: ("Overcast", "none"),
    45: ("Fog", "moderate"),
    48: ("Depositing rime fog", "moderate"),
    51: ("Light drizzle", "low"),
    53: ("Moderate drizzle", "low"),
    55: ("Dense drizzle", "low"),
    56: ("Light freezing drizzle", "severe"),
    57: ("Dense freezing drizzle", "severe"),
    61: ("Slight rain", "low"),
    63: ("Moderate rain", "low"),
    65: ("Heavy rain", "moderate"),
    66: ("Light freezing rain", "severe"),
    67: ("Heavy freezing rain", "severe"),
    71: ("Slight snow fall", "moderate"),
    73: ("Moderate snow fall", "moderate"),
    75: ("Heavy snow fall", "severe"),
    77: ("Snow grains", "severe"),
    80: ("Slight rain showers", "low"),
    81: ("Moderate rain showers", "low"),
    82: ("Violent rain showers", "moderate"),
    85: ("Slight snow showers", "moderate"),
    86: ("Heavy snow showers", "severe"),
    95: ("Thunderstorm", "severe"),
    96: ("Thunderstorm with slight hail", "severe"),
    99: ("Thunderstorm with heavy hail", "severe"),
}


def interpret_sample_severity(
    weather_code: int | None,
    temperature_f: float | None,
    precipitation_in: float | None,
    wind_mph: float | None,
    gust_mph: float | None,
    visibility_mi: float | None,
) -> tuple[str, str]:
    """Determine condition label and severity level for an individual sample.

    Returns (condition_label, severity_str).
    """
    if weather_code is not None and weather_code in WMO_CODE_INFO:
        condition, code_severity = WMO_CODE_INFO[weather_code]
    elif weather_code is not None:
        condition = f"WMO {weather_code}"
        code_severity = "low"
    else:
        condition = "Unknown"
        code_severity = "none"

    curr_rank = SEVERITY_RANKS[code_severity]

    # Rule: visibility < 1 mi -> moderate
    if visibility_mi is not None and visibility_mi < 1.0:
        curr_rank = max(curr_rank, SEVERITY_RANKS["moderate"])

    # Rule: precipitation >= 0.25 in/h -> moderate
    if precipitation_in is not None and precipitation_in >= 0.25:
        curr_rank = max(curr_rank, SEVERITY_RANKS["moderate"])

    # Rule: gusts >= 30 mph -> moderate; >= 45 mph -> severe
    if gust_mph is not None:
        if gust_mph >= 45.0:
            curr_rank = max(curr_rank, SEVERITY_RANKS["severe"])
        elif gust_mph >= 30.0:
            curr_rank = max(curr_rank, SEVERITY_RANKS["moderate"])

    # Rule: temp <= 28 F with precipitation > 0 -> severe
    if (
        temperature_f is not None
        and temperature_f <= 28.0
        and precipitation_in is not None
        and precipitation_in > 0.0
    ):
        curr_rank = max(curr_rank, SEVERITY_RANKS["severe"])

    # Inverse rank mapping
    rank_to_name = {v: k for k, v in SEVERITY_RANKS.items()}
    final_severity = rank_to_name[curr_rank]
    return condition, final_severity


def aggregate_route_risk(samples: list[WeatherSample]) -> tuple[str, str]:
    """Aggregate route risk level and human-readable summary from samples.

    Returns (risk_level, summary_text).
    """
    if not samples:
        return "none", "No significant weather expected."

    has_severe = any(s.severity == "severe" for s in samples)
    if has_severe:
        risk_level = "severe"
    else:
        moderate_samples = [s for s in samples if s.severity == "moderate"]
        any_moderate_heavy_precip = any(
            s.severity == "moderate"
            and s.precipitation_in is not None
            and s.precipitation_in >= 0.10
            for s in samples
        )
        if len(moderate_samples) >= 2 or any_moderate_heavy_precip:
            risk_level = "moderate"
        elif any(s.severity in ("low", "moderate") for s in samples):
            risk_level = "low"
        else:
            risk_level = "none"

    # Build summary from worst samples
    non_none_samples = [s for s in samples if s.severity != "none"]
    if not non_none_samples:
        return risk_level, "No significant weather expected."

    # Sort by severity rank descending, then precipitation descending
    sorted_samples = sorted(
        non_none_samples,
        key=lambda s: (
            SEVERITY_RANKS[s.severity],
            s.precipitation_in or 0.0,
            s.gust_mph or 0.0,
        ),
        reverse=True,
    )
    worst = sorted_samples[0]
    eta_time = worst.eta[11:16] if len(worst.eta) >= 16 else worst.eta
    summary = f"{worst.condition} near mile {int(round(worst.route_mile))} (ETA {eta_time} UTC)"

    if len(sorted_samples) > 1 and sorted_samples[1].condition != worst.condition:
        second = sorted_samples[1]
        second_eta = second.eta[11:16] if len(second.eta) >= 16 else second.eta
        cond_lower = second.condition.lower()
        mile_int = int(round(second.route_mile))
        summary += f"; also {cond_lower} near mile {mile_int} (ETA {second_eta} UTC)"
    else:
        summary += "; otherwise clear."

    return risk_level, summary
